"""Build an EPUB book from `data/betrayal_short.json` summarized chapters."""

import argparse
import html
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from ebooklib import epub

from ingest.logging_utils import configure_logging, get_logger
from ingest.pipeline_common import read_json
from project_paths import DATA_DIR, ROOT_DIR


logger = get_logger(__name__)

INPUT_FILE_DEFAULT = DATA_DIR / "betrayal_short.json"
OUTPUT_FILE_DEFAULT = DATA_DIR / "betrayal_short.epub"
OPS_DIR_DEFAULT = ROOT_DIR / "contents" / "OPS"
OPF_FILE_NAME = "content.opf"
LANGUAGE_DEFAULT = "en-US"

EPUB_STYLE_CSS = """
body {
    font-family: serif;
    line-height: 1.45;
    margin: 5%;
}
h1 {
    text-align: left;
    margin-top: 1em;
    margin-bottom: 1em;
}
p {
    text-indent: 1.5em;
    margin-top: 0;
    margin-bottom: 0.9em;
}
"""


def chapter_to_xhtml(title: str, paragraphs: list[str], language: str) -> str:
    """Convert chapter title and paragraphs to XHTML body content string."""
    safe_title = html.escape(title)
    safe_language = html.escape(language)
    body_parts = [f"<h1>{safe_title}</h1>"]
    for paragraph in paragraphs:
        clean_paragraph = paragraph.strip()
        if clean_paragraph:
            body_parts.append(f"<p>{html.escape(clean_paragraph)}</p>")

    return (
        f'<section xml:lang="{safe_language}" lang="{safe_language}">\n'
        + "\n".join(body_parts)
        + "\n</section>"
    )


def _extract_author_from_author_line(author_line: str) -> str:
    """Extract best-effort author name from a cover author line string."""
    match = re.search(r"author\s+(.+)$", author_line, flags=re.IGNORECASE)
    if match is None:
        return author_line.strip()
    extracted_name = match.group(1).strip()
    return extracted_name or author_line.strip()


def _extract_book_identifier_from_opf(ops_dir: Path) -> str | None:
    """Extract unique identifier from content.opf when available."""
    opf_path = ops_dir / OPF_FILE_NAME
    if not opf_path.exists():
        return None

    tree = ET.parse(opf_path)
    root = tree.getroot()
    package_unique_identifier = root.attrib.get("unique-identifier")
    if not package_unique_identifier:
        return None

    namespace = {
        "opf": "http://www.idpf.org/2007/opf",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    identifier_element = root.find(
        f".//dc:identifier[@id='{package_unique_identifier}']", namespace
    )
    if identifier_element is None:
        return None

    identifier_text = (identifier_element.text or "").strip()
    return identifier_text or None


def _extract_cover_bytes_and_name(
    book_metadata: dict, ops_dir: Path
) -> tuple[bytes, str] | None:
    """Read cover image bytes and filename from metadata when available."""
    cover_data = book_metadata.get("cover")
    if not isinstance(cover_data, dict):
        return None

    image_src = cover_data.get("image_src")
    if not isinstance(image_src, str) or not image_src.strip():
        return None

    cover_path = ops_dir / image_src
    if not cover_path.exists():
        raise FileNotFoundError(f"Cover image not found at {cover_path}")

    return cover_path.read_bytes(), cover_path.name


def _validate_chapter_and_get_paragraphs(
    chapter: dict, chapter_index: int
) -> list[str]:
    """Validate chapter structure and return paragraph text list."""
    paragraphs = chapter.get("paragraphs")
    if not isinstance(paragraphs, list):
        raise ValueError(f"Chapter {chapter_index} field 'paragraphs' must be a list.")

    paragraph_texts: list[str] = []
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            raise ValueError(
                f"Chapter {chapter_index} paragraph entries must be objects."
            )
        text = paragraph.get("text")
        if not isinstance(text, str):
            raise ValueError(f"Chapter {chapter_index} paragraph text must be string.")
        cleaned_text = text.strip()
        if cleaned_text:
            paragraph_texts.append(cleaned_text)

    if not paragraph_texts:
        raise ValueError(
            f"Chapter {chapter_index} has no non-empty summary paragraphs."
        )

    return paragraph_texts


def build_epub_from_betrayal_short_json(
    *,
    json_path: Path,
    output_path: Path,
    ops_dir: Path,
    language: str = LANGUAGE_DEFAULT,
) -> None:
    """Build summarized EPUB from `betrayal_short.json` data file."""
    data = read_json(json_path)
    book_metadata = data.get("book_metadata")
    examples = data.get("examples")

    if not isinstance(book_metadata, dict):
        raise ValueError("Input JSON must contain object key 'book_metadata'.")
    if not isinstance(examples, list):
        raise ValueError("Input JSON must contain list key 'examples'.")

    book_title = book_metadata.get("title")
    author_line = book_metadata.get("author_line")
    if not isinstance(book_title, str) or not book_title.strip():
        raise ValueError("book_metadata.title must be a non-empty string.")
    if not isinstance(author_line, str) or not author_line.strip():
        raise ValueError("book_metadata.author_line must be a non-empty string.")

    author_name = _extract_author_from_author_line(author_line)
    book_identifier = _extract_book_identifier_from_opf(ops_dir)
    if book_identifier is None:
        book_identifier = (
            f"betrayal-short-{book_title.strip().lower().replace(' ', '-')}"
        )

    logger.info(
        "Building EPUB input=%s output=%s chapters=%d",
        json_path,
        output_path,
        len(examples),
    )

    book = epub.EpubBook()
    book.set_identifier(book_identifier)
    book.set_title(book_title.strip())
    book.set_language(language)
    book.add_author(author_name)

    cover_data = _extract_cover_bytes_and_name(book_metadata, ops_dir)
    if cover_data is not None:
        cover_bytes, cover_file_name = cover_data
        book.set_cover(cover_file_name, cover_bytes)

    nav_css = epub.EpubItem(
        uid="style_nav",
        file_name="style/nav.css",
        media_type="text/css",
        content=EPUB_STYLE_CSS,
    )
    book.add_item(nav_css)

    epub_chapters: list[epub.EpubHtml] = []
    for chapter_index, chapter in enumerate(examples, start=1):
        if not isinstance(chapter, dict):
            raise ValueError(
                f"Chapter entry at index {chapter_index} must be an object."
            )

        chapter_title = chapter.get("chapter_title")
        if not isinstance(chapter_title, str) or not chapter_title.strip():
            chapter_title = f"Chapter {chapter_index}"

        paragraph_texts = _validate_chapter_and_get_paragraphs(chapter, chapter_index)
        chapter_content = chapter_to_xhtml(chapter_title, paragraph_texts, language)

        chapter_file_name = f"chap_{chapter_index:03d}.xhtml"
        epub_chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=chapter_file_name,
            lang=language,
        )
        epub_chapter.content = chapter_content
        epub_chapter.add_item(nav_css)

        book.add_item(epub_chapter)
        epub_chapters.append(epub_chapter)
        logger.info(
            "[%d/%d] Added chapter %s", chapter_index, len(examples), chapter_file_name
        )

    book.toc = tuple(epub_chapters)
    book.spine = ["nav", *epub_chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book, {})
    logger.info("EPUB generated at %s", output_path)


def main() -> None:
    """CLI entry point for summarized EPUB generation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", default=str(INPUT_FILE_DEFAULT))
    parser.add_argument("--output-file", default=str(OUTPUT_FILE_DEFAULT))
    parser.add_argument("--ops-dir", default=str(OPS_DIR_DEFAULT))
    args = parser.parse_args()

    effective_log_level = configure_logging()
    logger.debug(
        "Starting build_betrayal_short_epub with LOG_LEVEL=%s", effective_log_level
    )

    build_epub_from_betrayal_short_json(
        json_path=Path(args.input_file),
        output_path=Path(args.output_file),
        ops_dir=Path(args.ops_dir),
    )


if __name__ == "__main__":
    main()
