"""Build normalized `data/betrayal.json` from XHTML chapter files."""

import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from ingest.logging_utils import configure_logging, get_logger
from project_paths import DATA_DIR, ROOT_DIR


CONTENTS_FILE = ROOT_DIR / "contents.txt"
OUTPUT_FILE = DATA_DIR / "betrayal.json"
XHTML_NS = "{http://www.w3.org/1999/xhtml}"
P_TAG = f"{XHTML_NS}p"
SUP_TAG = f"{XHTML_NS}sup"
SPAN_TAG = f"{XHTML_NS}span"
SEPARATOR_PATTERN = re.compile(r"^\*\s*\*\s*\*$")
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


def main() -> None:
    """Generate `data/betrayal.json` from source chapter files."""
    effective_log_level = configure_logging()
    logger.debug("Starting build_betrayal_json with LOG_LEVEL=%s", effective_log_level)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Reading chapter list from %s", CONTENTS_FILE)
    chapter_paths = load_paths(CONTENTS_FILE)
    logger.info("Found %d chapter source files", len(chapter_paths))
    examples = [parse_file(path) for path in chapter_paths]
    payload = {"examples": examples}

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    logger.info("Generated %s with %d entries", OUTPUT_FILE.name, len(examples))


if __name__ == "__main__":
    main()
