"""Build an EPUB book from `data/betrayal_short.json` summarized chapters."""

import argparse
import html
import mimetypes
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
XHTML_NS = {"xhtml": "http://www.w3.org/1999/xhtml"}
COVER_BADGE_TEXT = "SHORT VERSION"
COVER_BADGE_INLINE_STYLE = (
    "position: absolute; top: 2vh; right: 2vw; margin: 0; "
    "padding: 0.35em 0.65em; font-family: sans-serif; "
    "font-size: 1.05em; font-weight: 700; letter-spacing: 0.06em; "
    "background: rgba(0, 0, 0, 0.70); color: #fff; z-index: 10000;"
)

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


def add_binary_item(
    book: epub.EpubBook, abs_path: Path, epub_file_name: str
) -> epub.EpubItem:
    """Add a binary asset item to EPUB using detected media type.

    Raises a fail-fast ValueError when media type cannot be inferred.
    """
    media_type, _ = mimetypes.guess_type(abs_path.name)
    if media_type is None:
        raise ValueError(f"Could not detect media type for: {abs_path}")

    item = epub.EpubItem(
        uid=f"asset_{epub_file_name.replace('/', '_')}",
        file_name=epub_file_name,
        media_type=media_type,
        content=abs_path.read_bytes(),
    )
    book.add_item(item)
    return item


def _resolve_cover_xhtml_paths(
    book_metadata: dict, ops_dir: Path
) -> tuple[Path, Path] | None:
    """Resolve absolute and root-relative paths for cover XHTML source file."""
    cover_data = book_metadata.get("cover")
    if not isinstance(cover_data, dict):
        return None

    source_file = cover_data.get("source_file")
    if not isinstance(source_file, str) or not source_file.strip():
        return None

    source_relpath = Path(source_file.strip())
    extracted_root = ROOT_DIR
    source_abspath = extracted_root / source_relpath
    if source_abspath.exists():
        return source_abspath, source_relpath

    # Support relative cover paths under OPS when metadata omits contents/OPS prefix.
    source_abspath = ops_dir / source_relpath
    if source_abspath.exists():
        inferred_relpath = Path("contents") / Path("OPS") / source_relpath
        return source_abspath, inferred_relpath

    raise FileNotFoundError(f"Configured cover source_file not found: {source_file}")


def _add_cover_stylesheets(
    book: epub.EpubBook,
    *,
    cover_xhtml_abs: Path,
    cover_xhtml_relpath: Path,
) -> None:
    """Add local stylesheet assets referenced by original cover XHTML."""
    root = ET.fromstring(cover_xhtml_abs.read_bytes())
    stylesheet_refs: set[Path] = set()
    for link in root.findall(".//xhtml:link", XHTML_NS):
        href = link.get("href")
        rel = (link.get("rel") or "").lower()
        if (
            href
            and "stylesheet" in rel
            and not href.startswith(("http://", "https://", "data:"))
        ):
            stylesheet_refs.add(Path(href))

    for stylesheet_ref in stylesheet_refs:
        stylesheet_abs = (cover_xhtml_abs.parent / stylesheet_ref).resolve()
        if not stylesheet_abs.exists():
            raise FileNotFoundError(
                f"Cover stylesheet referenced by {cover_xhtml_abs} not found: {stylesheet_abs}"
            )

        stylesheet_epub_path = (cover_xhtml_relpath.parent / stylesheet_ref).as_posix()
        add_binary_item(book, stylesheet_abs, stylesheet_epub_path)


def copy_cover_xhtml_from_extracted(
    book: epub.EpubBook,
    *,
    cover_xhtml_abs: Path,
    cover_xhtml_relpath: Path,
) -> epub.EpubHtml:
    """Copy original cover XHTML and inject a SHORT VERSION badge on top.

    The insertion is performed by targeted string replacement to preserve the
    original XHTML structure and avoid namespace/serialization side effects.
    """
    _add_cover_stylesheets(
        book,
        cover_xhtml_abs=cover_xhtml_abs,
        cover_xhtml_relpath=cover_xhtml_relpath,
    )

    cover_xhtml_text = cover_xhtml_abs.read_text(encoding="utf-8")
    cover_div_marker = '<div class="cover" id="cover">'
    if cover_div_marker not in cover_xhtml_text:
        raise ValueError(
            f"Cover XHTML does not contain expected cover div marker: {cover_xhtml_abs}"
        )

    cover_xhtml_text = cover_xhtml_text.replace(
        cover_div_marker,
        '<div class="cover" id="cover" style="position: relative;">',
        1,
    )
    if "</div>" not in cover_xhtml_text:
        raise ValueError(
            f"Cover XHTML does not contain expected closing cover div: {cover_xhtml_abs}"
        )

    badge_markup = (
        f'<p class="short-version-badge" style="{COVER_BADGE_INLINE_STYLE}">'
        f"{COVER_BADGE_TEXT}"
        "</p>"
    )
    cover_xhtml_text = cover_xhtml_text.replace("</div>", f"{badge_markup}</div>", 1)

    cover_page = epub.EpubHtml(
        title="Cover",
        file_name=cover_xhtml_relpath.as_posix(),
        lang="en",
    )
    cover_page.content = cover_xhtml_text.encode("utf-8")
    book.add_item(cover_page)
    return cover_page


def _resolve_cover_image(
    book_metadata: dict, ops_dir: Path
) -> tuple[bytes, str] | None:
    """Resolve cover image bytes and EPUB file name from metadata."""
    cover_data = book_metadata.get("cover")
    if not isinstance(cover_data, dict):
        return None

    image_src = cover_data.get("image_src")
    if not isinstance(image_src, str) or not image_src.strip():
        return None

    image_relpath = Path(image_src.strip())
    image_abs = ops_dir / image_relpath
    if not image_abs.exists():
        raise FileNotFoundError(f"Configured cover image not found: {image_abs}")

    image_epub_path = (Path("contents") / Path("OPS") / image_relpath).as_posix()
    return image_abs.read_bytes(), image_epub_path


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

    cover_image = _resolve_cover_image(book_metadata, ops_dir)
    if cover_image is not None:
        cover_bytes, cover_epub_path = cover_image
        book.set_cover(cover_epub_path, cover_bytes)

    cover_page: epub.EpubHtml | None = None
    cover_xhtml_paths = _resolve_cover_xhtml_paths(book_metadata, ops_dir)
    if cover_xhtml_paths is not None:
        cover_xhtml_abs, cover_xhtml_relpath = cover_xhtml_paths
        cover_page = copy_cover_xhtml_from_extracted(
            book,
            cover_xhtml_abs=cover_xhtml_abs,
            cover_xhtml_relpath=cover_xhtml_relpath,
        )

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
            if chapter_index == 1:
                chapter_title = "Prologue"
            else:
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
    if cover_page is None:
        book.spine = ["nav", *epub_chapters]
    else:
        book.spine = [cover_page, "nav", *epub_chapters]
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
