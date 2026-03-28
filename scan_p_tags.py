import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT_DIR = Path(__file__).resolve().parent
CONTENTS_FILE = ROOT_DIR / "contents.txt"
DATA_DIR = ROOT_DIR / "data"
REPORT_FILE = DATA_DIR / "p_inner_tags_report.json"
XHTML_NS = "{http://www.w3.org/1999/xhtml}"
P_TAG = f"{XHTML_NS}p"


def clean_text(text: str) -> str:
    return " ".join(text.split())


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def load_paths() -> list[Path]:
    paths = []
    with CONTENTS_FILE.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if line:
                paths.append(ROOT_DIR / line)
    return paths


def is_empty_span(node: ET.Element) -> bool:
    return clean_text("".join(node.itertext())) == ""


def scan_file(path: Path) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()

    raw_tag_counts: dict[str, int] = {}
    normalized_tag_counts = {
        "sup_removed": 0,
        "a_text_kept": 0,
        "em_text_kept": 0,
        "strong_text_kept": 0,
        "span_text_kept": 0,
        "span_empty_removed": 0,
        "other_tags": {},
    }
    paragraph_count = 0

    for paragraph in root.iter(P_TAG):
        paragraph_count += 1
        for node in paragraph.iter():
            if node is paragraph:
                continue
            name = local_name(node.tag)
            raw_tag_counts[name] = raw_tag_counts.get(name, 0) + 1

            if name == "sup":
                normalized_tag_counts["sup_removed"] += 1
            elif name == "a":
                normalized_tag_counts["a_text_kept"] += 1
            elif name == "em":
                normalized_tag_counts["em_text_kept"] += 1
            elif name == "strong":
                normalized_tag_counts["strong_text_kept"] += 1
            elif name == "span":
                if is_empty_span(node):
                    normalized_tag_counts["span_empty_removed"] += 1
                else:
                    normalized_tag_counts["span_text_kept"] += 1
            else:
                other = normalized_tag_counts["other_tags"]
                other[name] = other.get(name, 0) + 1

    return {
        "source_file": path.name,
        "paragraph_count": paragraph_count,
        "raw_inner_tags": dict(sorted(raw_tag_counts.items())),
        "normalized_tag_actions": {
            "sup_removed": normalized_tag_counts["sup_removed"],
            "a_text_kept": normalized_tag_counts["a_text_kept"],
            "em_text_kept": normalized_tag_counts["em_text_kept"],
            "strong_text_kept": normalized_tag_counts["strong_text_kept"],
            "span_text_kept": normalized_tag_counts["span_text_kept"],
            "span_empty_removed": normalized_tag_counts["span_empty_removed"],
            "other_tags": dict(sorted(normalized_tag_counts["other_tags"].items())),
        },
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    chapter_paths = load_paths()
    per_file = [scan_file(path) for path in chapter_paths]

    all_tags = set()
    totals = {
        "sup_removed": 0,
        "a_text_kept": 0,
        "em_text_kept": 0,
        "strong_text_kept": 0,
        "span_text_kept": 0,
        "span_empty_removed": 0,
        "other_tags": {},
    }

    for item in per_file:
        all_tags.update(item["raw_inner_tags"].keys())
        actions = item["normalized_tag_actions"]
        totals["sup_removed"] += actions["sup_removed"]
        totals["a_text_kept"] += actions["a_text_kept"]
        totals["em_text_kept"] += actions["em_text_kept"]
        totals["strong_text_kept"] += actions["strong_text_kept"]
        totals["span_text_kept"] += actions["span_text_kept"]
        totals["span_empty_removed"] += actions["span_empty_removed"]
        for tag_name, count in actions["other_tags"].items():
            totals["other_tags"][tag_name] = (
                totals["other_tags"].get(tag_name, 0) + count
            )

    report = {
        "total_files": len(per_file),
        "all_inner_tags": sorted(all_tags),
        "normalized_totals": {
            "sup_removed": totals["sup_removed"],
            "a_text_kept": totals["a_text_kept"],
            "em_text_kept": totals["em_text_kept"],
            "strong_text_kept": totals["strong_text_kept"],
            "span_text_kept": totals["span_text_kept"],
            "span_empty_removed": totals["span_empty_removed"],
            "other_tags": dict(sorted(totals["other_tags"].items())),
        },
        "files": per_file,
    }

    with REPORT_FILE.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print(f"Generated {REPORT_FILE.name} for {len(per_file)} files.")


if __name__ == "__main__":
    main()
