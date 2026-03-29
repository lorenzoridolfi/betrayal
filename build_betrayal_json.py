"""Build normalized `data/betrayal.json` from XHTML chapter files."""

import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from ingest.logging_utils import configure_logging, get_logger
from project_paths import DATA_DIR, ROOT_DIR


CONTENTS_FILE = ROOT_DIR / "contents.txt"
BOOK_COVER_FILE = ROOT_DIR / "contents" / "OPS" / "001-Cover.xhtml"
OUTPUT_FILE = DATA_DIR / "betrayal.json"
XHTML_NS = "{http://www.w3.org/1999/xhtml}"
P_TAG = f"{XHTML_NS}p"
SUP_TAG = f"{XHTML_NS}sup"
SPAN_TAG = f"{XHTML_NS}span"
IMG_TAG = f"{XHTML_NS}img"
SEPARATOR_PATTERN = re.compile(r"^\*\s*\*\s*\*$")
AUTHOR_LINE_PATTERN = re.compile(r"top line reads [‘']([^’']+)[’']", re.IGNORECASE)
TITLE_PATTERN = re.compile(
    r"followed by the title,\s*([^.,]+?)(?:\s+in\s+[^.]+)?\.",
    re.IGNORECASE,
)
SUBTITLE_PATTERN = re.compile(r"subtitle reads [‘']([^’']+)[’']", re.IGNORECASE)
logger = get_logger(__name__)


def clean_text(text: str) -> str:
    """Collapse repeated whitespace into single spaces."""
    return " ".join(text.split())


def remove_sup_nodes(element: ET.Element) -> None:
    """Remove `<sup>` nodes in place before text extraction."""
    for parent in element.iter():
        for child in list(parent):
            if child.tag == SUP_TAG:
                parent.remove(child)


def remove_empty_span_nodes(element: ET.Element) -> None:
    """Remove empty `<span>` nodes to avoid empty artifacts."""
    for parent in element.iter():
        for child in list(parent):
            if child.tag != SPAN_TAG:
                continue
            if clean_text("".join(child.itertext())) == "":
                parent.remove(child)


def paragraph_text_without_sup(paragraph: ET.Element) -> str:
    """Return normalized paragraph text without footnote markup."""
    paragraph_copy = ET.fromstring(ET.tostring(paragraph, encoding="unicode"))
    remove_sup_nodes(paragraph_copy)
    remove_empty_span_nodes(paragraph_copy)
    return clean_text("".join(paragraph_copy.itertext()))


def extract_paragraphs(section: ET.Element) -> list[dict]:
    """Extract numbered paragraph objects from one chapter section."""
    items = []
    for p in section.iter(P_TAG):
        if p.attrib.get("class") == "ct":
            continue

        text = paragraph_text_without_sup(p)
        if not text:
            continue
        if SEPARATOR_PATTERN.fullmatch(text):
            continue

        items.append(text)

    return [
        {"paragraph_index": idx, "text": text}
        for idx, text in enumerate(items, start=1)
    ]


def parse_file(chapter_path: Path) -> dict:
    """Parse one chapter XHTML file into normalized chapter payload."""
    tree = ET.parse(chapter_path)
    root = tree.getroot()
    section = root.find(f".//{XHTML_NS}section")
    if section is None:
        raise ValueError(f"No <section> found in {chapter_path}")

    source_file = chapter_path.name
    is_prologue = source_file.endswith("Prologue.xhtml")

    chapter_type = "prologue" if is_prologue else "chapter"
    chapter_number = None
    chapter_label = None
    chapter_title = None

    if not is_prologue:
        match = re.search(r"Chapter_(\d+)", source_file)
        if match is None:
            raise ValueError(f"Could not extract chapter number from {source_file}")
        chapter_number = int(match.group(1))

        h1 = section.find(f".//{XHTML_NS}h1")
        if h1 is not None:
            chapter_label = clean_text("".join(h1.itertext())) or None

        subtitle = None
        for p in section.iter(P_TAG):
            if p.attrib.get("class") == "ct":
                subtitle = p
                break
        if subtitle is not None:
            chapter_title = clean_text("".join(subtitle.itertext())) or None

    return {
        "source_file": source_file,
        "chapter_type": chapter_type,
        "chapter_number": chapter_number,
        "chapter_label": chapter_label,
        "chapter_title": chapter_title,
        "paragraphs": extract_paragraphs(section),
    }


def load_paths(contents_file: Path) -> list[Path]:
    """Load chapter-relative paths listed in `contents.txt`."""
    paths = []
    with contents_file.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line:
                continue
            paths.append(ROOT_DIR / line)
    return paths


def _extract_alt_fragment(pattern: re.Pattern[str], alt_text: str, label: str) -> str:
    """Extract one metadata fragment from cover alt text or fail fast."""
    match = pattern.search(alt_text)
    if match is None:
        raise ValueError(f"Could not extract {label} from cover alt text.")
    value = clean_text(match.group(1))
    if not value:
        raise ValueError(f"Extracted empty {label} from cover alt text.")
    return value


def parse_cover_metadata(cover_file: Path) -> dict:
    """Parse cover XHTML and return minimal book metadata."""
    tree = ET.parse(cover_file)
    root = tree.getroot()
    cover_image = root.find(f".//{IMG_TAG}")
    if cover_image is None:
        raise ValueError(f"No <img> found in cover file: {cover_file}")

    image_src = cover_image.attrib.get("src")
    image_alt = clean_text(cover_image.attrib.get("alt", ""))
    if not image_src:
        raise ValueError("Cover image 'src' is missing.")
    if not image_alt:
        raise ValueError("Cover image 'alt' is missing.")

    return {
        "title": _extract_alt_fragment(TITLE_PATTERN, image_alt, "title"),
        "subtitle": _extract_alt_fragment(SUBTITLE_PATTERN, image_alt, "subtitle"),
        "author_line": _extract_alt_fragment(
            AUTHOR_LINE_PATTERN, image_alt, "author_line"
        ),
        "cover": {
            "source_file": str(cover_file.relative_to(ROOT_DIR)),
            "image_src": image_src,
            "image_alt": image_alt,
        },
    }


def main() -> None:
    """Generate `data/betrayal.json` from source chapter files."""
    effective_log_level = configure_logging()
    logger.debug("Starting build_betrayal_json with LOG_LEVEL=%s", effective_log_level)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Reading chapter list from %s", CONTENTS_FILE)
    chapter_paths = load_paths(CONTENTS_FILE)
    logger.info("Found %d chapter source files", len(chapter_paths))
    logger.info("Parsing cover metadata from %s", BOOK_COVER_FILE)
    book_metadata = parse_cover_metadata(BOOK_COVER_FILE)
    examples = [parse_file(path) for path in chapter_paths]
    payload = {"book_metadata": book_metadata, "examples": examples}

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    logger.info("Generated %s with %d entries", OUTPUT_FILE.name, len(examples))


if __name__ == "__main__":
    main()
