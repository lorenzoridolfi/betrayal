"""Build `data/betrayal.json` directly from an EPUB source file.

This script reads `Betrayal.epub`, parses OPF metadata and spine order, and
emits the same JSON structure produced by `build_betrayal_json.py`:
`book_metadata` and `examples`.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional
import xml.etree.ElementTree as ET

from ingest.logging_utils import configure_logging, get_logger
from project_paths import DATA_DIR, ROOT_DIR


CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
OPF_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}
XHTML_NS = {"xhtml": "http://www.w3.org/1999/xhtml"}

AUTHOR_LINE_PATTERN = re.compile(r"top line reads [‘']([^’']+)[’']", re.IGNORECASE)
TITLE_PATTERN = re.compile(
    r"followed by the title,\s*([^.,]+?)(?:\s+in\s+[^.]+)?\.",
    re.IGNORECASE,
)
SUBTITLE_PATTERN = re.compile(r"subtitle reads [‘']([^’']+)[’']", re.IGNORECASE)
SEPARATOR_PATTERN = re.compile(r"^\*\s*\*\s*\*$")
PROLOGUE_FILE_PATTERN = re.compile(r"^\d+-prologue\.xhtml$", re.IGNORECASE)
CHAPTER_FILE_PATTERN = re.compile(r"^\d+-chapter_(\d+)\.xhtml$", re.IGNORECASE)
FIRST_EXTRACT_SOURCE_FILE = "008-Prologue.xhtml"
LAST_EXTRACT_SOURCE_FILE = "051-Chapter_43.xhtml"
LAST_EXTRACT_CHAPTER_TITLE = "Make or Break"

EPUB_FILE_DEFAULT = ROOT_DIR / "Betrayal.epub"
OUTPUT_FILE_DEFAULT = DATA_DIR / "betrayal.json"

logger = get_logger(__name__)


def clean_text(text: str) -> str:
    """Normalize whitespace to keep extracted prose stable and compact."""
    return " ".join(text.split())


def resolve_href(opf_path: str, href: str) -> str:
    """Resolve one OPF-relative href to an archive-normalized path."""
    base_dir = posixpath.dirname(opf_path)
    return posixpath.normpath(posixpath.join(base_dir, href))


def get_opf_path(archive: zipfile.ZipFile) -> str:
    """Resolve OPF path using `META-INF/container.xml`.

    Fail-fast behavior is intentional: missing `container.xml` or `full-path`
    means the EPUB is structurally invalid for this extractor.
    """
    try:
        container_xml = archive.read("META-INF/container.xml")
    except KeyError as error:
        raise FileNotFoundError("META-INF/container.xml not found in EPUB.") from error

    root = ET.fromstring(container_xml)
    rootfile = root.find(".//c:rootfile", CONTAINER_NS)
    if rootfile is None:
        raise ValueError("No <rootfile> found in META-INF/container.xml.")

    opf_path = rootfile.attrib.get("full-path")
    if not opf_path:
        raise ValueError("Rootfile is missing required `full-path` attribute.")
    return opf_path


def parse_manifest_and_spine(
    archive: zipfile.ZipFile,
    opf_path: str,
) -> tuple[dict[str, dict[str, str]], list[str], Optional[str], Optional[str]]:
    """Parse OPF and return manifest/spine plus cover references.

    Returns `(manifest_by_id, spine_ids, cover_image_href, guide_cover_href)`.
    """
    opf_xml = archive.read(opf_path)
    root = ET.fromstring(opf_xml)

    manifest_by_id: dict[str, dict[str, str]] = {}
    for item in root.findall(".//opf:manifest/opf:item", OPF_NS):
        item_id = item.attrib.get("id")
        href = item.attrib.get("href")
        media_type = item.attrib.get("media-type")
        if not item_id or not href or not media_type:
            raise ValueError("Manifest item is missing id, href, or media-type.")

        manifest_by_id[item_id] = {
            "href": href,
            "media_type": media_type,
            "properties": item.attrib.get("properties", ""),
        }

    spine_ids: list[str] = []
    for itemref in root.findall(".//opf:spine/opf:itemref", OPF_NS):
        idref = itemref.attrib.get("idref")
        if idref:
            spine_ids.append(idref)

    if not spine_ids:
        raise ValueError("OPF spine has no itemref entries.")

    cover_image_href: Optional[str] = None
    for manifest_item in manifest_by_id.values():
        properties = manifest_item["properties"]
        if "cover-image" in properties.split():
            cover_image_href = manifest_item["href"]
            break

    if cover_image_href is None:
        meta_cover = root.find('.//opf:metadata/opf:meta[@name="cover"]', OPF_NS)
        if meta_cover is not None:
            cover_id = meta_cover.attrib.get("content")
            if cover_id and cover_id in manifest_by_id:
                cover_image_href = manifest_by_id[cover_id]["href"]

    guide_cover_href: Optional[str] = None
    guide_cover = root.find('.//opf:guide/opf:reference[@type="cover"]', OPF_NS)
    if guide_cover is not None:
        guide_cover_href = guide_cover.attrib.get("href")

    return manifest_by_id, spine_ids, cover_image_href, guide_cover_href


def _append_tail(
    parent: ET.Element,
    previous_sibling: Optional[ET.Element],
    tail_text: str,
) -> None:
    """Append removed-node tail text to preserve paragraph continuity."""
    if previous_sibling is not None:
        previous_sibling.tail = (previous_sibling.tail or "") + tail_text
    else:
        parent.text = (parent.text or "") + tail_text


def remove_nodes_preserving_tail(
    root: ET.Element,
    *,
    should_remove: callable,
) -> None:
    """Remove matching descendants while preserving their trailing text.

    Preserving `tail` is mandatory to avoid silent truncation after inline tags.
    """
    for parent in root.iter():
        children = list(parent)
        for index, child in enumerate(children):
            if not should_remove(child):
                continue

            if child.tail:
                previous_sibling = children[index - 1] if index > 0 else None
                _append_tail(parent, previous_sibling, child.tail)
            parent.remove(child)


def paragraph_text_without_inline_markers(paragraph: ET.Element) -> str:
    """Extract paragraph text after removing footnote markers and empty spans."""
    paragraph_copy = ET.fromstring(ET.tostring(paragraph, encoding="unicode"))

    remove_nodes_preserving_tail(
        paragraph_copy,
        should_remove=lambda node: node.tag == "{http://www.w3.org/1999/xhtml}sup",
    )
    remove_nodes_preserving_tail(
        paragraph_copy,
        should_remove=lambda node: (
            node.tag == "{http://www.w3.org/1999/xhtml}span"
            and clean_text("".join(node.itertext())) == ""
        ),
    )
    return clean_text("".join(paragraph_copy.itertext()))


def extract_chapter_payload(
    xhtml_bytes: bytes,
    *,
    source_file: str,
) -> dict[str, object]:
    """Parse one chapter XHTML into the legacy output payload shape."""
    root = ET.fromstring(xhtml_bytes)
    section = root.find(".//xhtml:section", XHTML_NS)
    if section is None:
        raise ValueError(f"No <section> found in chapter file: {source_file}")

    is_prologue = PROLOGUE_FILE_PATTERN.match(source_file) is not None
    chapter_type = "prologue" if is_prologue else "chapter"
    chapter_number: Optional[int] = None
    chapter_label: Optional[str] = None
    chapter_title: Optional[str] = None

    if not is_prologue:
        match = CHAPTER_FILE_PATTERN.match(source_file)
        if match is None:
            raise ValueError(f"Unsupported chapter filename format: {source_file}")
        chapter_number = int(match.group(1))

        heading = section.find(".//xhtml:h1", XHTML_NS)
        if heading is not None:
            chapter_label = clean_text("".join(heading.itertext())) or None

        subtitle = None
        for paragraph in section.findall(".//xhtml:p", XHTML_NS):
            if paragraph.attrib.get("class") == "ct":
                subtitle = paragraph
                break
        if subtitle is not None:
            chapter_title = clean_text("".join(subtitle.itertext())) or None

    paragraph_texts: list[str] = []
    for paragraph in section.findall(".//xhtml:p", XHTML_NS):
        if paragraph.attrib.get("class") == "ct":
            continue

        text = paragraph_text_without_inline_markers(paragraph)
        if not text:
            continue
        if SEPARATOR_PATTERN.fullmatch(text):
            continue
        paragraph_texts.append(text)

    paragraphs = [
        {"paragraph_index": index, "text": text}
        for index, text in enumerate(paragraph_texts, start=1)
    ]

    return {
        "source_file": source_file,
        "chapter_type": chapter_type,
        "chapter_number": chapter_number,
        "chapter_label": chapter_label,
        "chapter_title": chapter_title,
        "paragraphs": paragraphs,
    }


def extract_alt_fragment(
    pattern: re.Pattern[str], alt_text: str, field_name: str
) -> str:
    """Extract one required field from cover alt text with strict validation."""
    match = pattern.search(alt_text)
    if match is None:
        raise ValueError(f"Could not extract {field_name} from cover alt text.")
    value = clean_text(match.group(1))
    if not value:
        raise ValueError(f"Extracted empty {field_name} from cover alt text.")
    return value


def normalize_cover_source_file(cover_xhtml_path: str) -> str:
    """Normalize cover source path to match legacy output convention."""
    path_without_fragment = cover_xhtml_path.split("#", 1)[0]
    path_obj = PurePosixPath(path_without_fragment)
    if path_obj.parts and path_obj.parts[0] == "EPUB":
        path_obj = PurePosixPath(*path_obj.parts[1:])
    if path_obj.parts and path_obj.parts[0] == "OPS":
        path_obj = PurePosixPath("contents") / path_obj
    return str(path_obj)


def extract_book_metadata(
    archive: zipfile.ZipFile,
    *,
    opf_path: str,
    manifest_by_id: dict[str, dict[str, str]],
    spine_ids: list[str],
    cover_image_href: Optional[str],
    guide_cover_href: Optional[str],
) -> dict[str, object]:
    """Extract `book_metadata` in the same schema used by legacy builder."""
    cover_xhtml_href = guide_cover_href
    if cover_xhtml_href is None:
        first_spine_id = spine_ids[0]
        if first_spine_id not in manifest_by_id:
            raise ValueError(f"First spine id '{first_spine_id}' missing in manifest.")
        cover_xhtml_href = manifest_by_id[first_spine_id]["href"]

    if not cover_xhtml_href:
        raise ValueError("Could not determine cover XHTML href from guide/spine.")

    cover_xhtml_path = resolve_href(opf_path, cover_xhtml_href.split("#", 1)[0])
    try:
        cover_xhtml_bytes = archive.read(cover_xhtml_path)
    except KeyError as error:
        raise FileNotFoundError(
            f"Cover XHTML file not found in EPUB: {cover_xhtml_path}"
        ) from error

    cover_root = ET.fromstring(cover_xhtml_bytes)
    cover_image = cover_root.find(".//xhtml:img", XHTML_NS)
    if cover_image is None:
        raise ValueError(f"No <img> found in cover XHTML: {cover_xhtml_path}")

    image_src = cover_image.attrib.get("src")
    image_alt = clean_text(cover_image.attrib.get("alt", ""))
    if not image_src:
        raise ValueError("Cover image src is missing in cover XHTML.")
    if not image_alt:
        raise ValueError("Cover image alt text is missing in cover XHTML.")

    if cover_image_href is None:
        logger.warning(
            "Cover image href not declared in OPF metadata; using cover XHTML image src."
        )

    return {
        "title": extract_alt_fragment(TITLE_PATTERN, image_alt, "title"),
        "subtitle": extract_alt_fragment(SUBTITLE_PATTERN, image_alt, "subtitle"),
        "author_line": extract_alt_fragment(
            AUTHOR_LINE_PATTERN,
            image_alt,
            "author_line",
        ),
        "cover": {
            "source_file": normalize_cover_source_file(cover_xhtml_path),
            "image_src": image_src,
            "image_alt": image_alt,
        },
    }


def build_betrayal_json_from_epub(*, epub_file: Path, output_file: Path) -> None:
    """Build `betrayal.json` from EPUB spine content in legacy output format."""
    if not epub_file.exists():
        raise FileNotFoundError(f"EPUB file not found: {epub_file}")

    with zipfile.ZipFile(epub_file, "r") as archive:
        opf_path = get_opf_path(archive)
        manifest_by_id, spine_ids, cover_image_href, guide_cover_href = (
            parse_manifest_and_spine(
                archive,
                opf_path,
            )
        )

        book_metadata = extract_book_metadata(
            archive,
            opf_path=opf_path,
            manifest_by_id=manifest_by_id,
            spine_ids=spine_ids,
            cover_image_href=cover_image_href,
            guide_cover_href=guide_cover_href,
        )

        extracted_examples: list[dict[str, object]] = []
        for idref in spine_ids:
            manifest_item = manifest_by_id.get(idref)
            if manifest_item is None:
                raise ValueError(f"Spine idref '{idref}' not found in manifest.")
            if manifest_item["media_type"] != "application/xhtml+xml":
                continue

            href = manifest_item["href"]
            full_path = resolve_href(opf_path, href)
            source_file = PurePosixPath(full_path).name
            if not (
                PROLOGUE_FILE_PATTERN.match(source_file)
                or CHAPTER_FILE_PATTERN.match(source_file)
            ):
                continue

            try:
                xhtml_bytes = archive.read(full_path)
            except KeyError as error:
                raise FileNotFoundError(
                    f"Chapter file missing in EPUB: {full_path}"
                ) from error

            chapter_payload = extract_chapter_payload(
                xhtml_bytes,
                source_file=source_file,
            )
            extracted_examples.append(chapter_payload)

    if not extracted_examples:
        raise ValueError("No chapter entries were extracted from EPUB spine.")

    first_index = next(
        (
            index
            for index, chapter in enumerate(extracted_examples)
            if chapter.get("source_file") == FIRST_EXTRACT_SOURCE_FILE
        ),
        None,
    )
    if first_index is None:
        raise ValueError(
            f"First chapter for extraction not found: {FIRST_EXTRACT_SOURCE_FILE}"
        )

    last_index = next(
        (
            index
            for index, chapter in enumerate(extracted_examples)
            if chapter.get("source_file") == LAST_EXTRACT_SOURCE_FILE
        ),
        None,
    )
    if last_index is None:
        raise ValueError(
            f"Last chapter for extraction not found: {LAST_EXTRACT_SOURCE_FILE}"
        )

    if last_index < first_index:
        raise ValueError(
            "Invalid chapter extraction window: last chapter appears before first chapter."
        )

    examples = extracted_examples[first_index : last_index + 1]
    first_source_file = examples[0].get("source_file")
    last_source_file = examples[-1].get("source_file")
    if first_source_file != FIRST_EXTRACT_SOURCE_FILE:
        raise ValueError(
            f"Extracted first chapter mismatch: expected {FIRST_EXTRACT_SOURCE_FILE}, got {first_source_file}"
        )
    if last_source_file != LAST_EXTRACT_SOURCE_FILE:
        raise ValueError(
            f"Extracted last chapter mismatch: expected {LAST_EXTRACT_SOURCE_FILE}, got {last_source_file}"
        )

    last_chapter_title = examples[-1].get("chapter_title")
    if not isinstance(last_chapter_title, str):
        raise ValueError("Last extracted chapter title is missing or invalid.")
    if (
        clean_text(last_chapter_title).casefold()
        != LAST_EXTRACT_CHAPTER_TITLE.casefold()
    ):
        raise ValueError(
            "Last extracted chapter title mismatch: "
            f"expected '{LAST_EXTRACT_CHAPTER_TITLE}', got '{last_chapter_title}'"
        )

    logger.info(
        "Chapter extraction window first=%s last=%s total=%d",
        FIRST_EXTRACT_SOURCE_FILE,
        LAST_EXTRACT_SOURCE_FILE,
        len(examples),
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"book_metadata": book_metadata, "examples": examples}
    with output_file.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    logger.info("Generated %s with %d chapters", output_file, len(examples))


def main() -> None:
    """Parse CLI arguments and build betrayal JSON from EPUB."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--epub-file", default=str(EPUB_FILE_DEFAULT))
    parser.add_argument("--output-file", default=str(OUTPUT_FILE_DEFAULT))
    args = parser.parse_args()

    effective_log_level = configure_logging()
    logger.debug(
        "Starting build_betrayal_json_from_epub with LOG_LEVEL=%s",
        effective_log_level,
    )

    build_betrayal_json_from_epub(
        epub_file=Path(args.epub_file),
        output_file=Path(args.output_file),
    )


if __name__ == "__main__":
    main()
