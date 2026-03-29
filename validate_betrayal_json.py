"""Validate `data/betrayal.json` structure and compute token totals."""

import json

import tiktoken
from ingest.logging_utils import configure_logging, get_logger
from project_paths import DATA_DIR


INPUT_FILE = DATA_DIR / "betrayal.json"
REPORT_FILE = DATA_DIR / "betrayal_validation_report.json"
EXPECTED_KEYS = {
    "source_file",
    "chapter_type",
    "chapter_number",
    "chapter_label",
    "chapter_title",
    "paragraphs",
}
REQUIRED_BOOK_METADATA_KEYS = {"title", "subtitle", "author_line", "cover"}
REQUIRED_COVER_KEYS = {"source_file", "image_src", "image_alt"}
logger = get_logger(__name__)


def count_tokens(text: str, encoder: tiktoken.Encoding) -> int:
    """Count tokens using the provided tokenizer encoder."""
    if not text:
        return 0
    return len(encoder.encode(text))


def validate_and_count(data: dict) -> dict:
    """Validate chapter payload shape and return per-chapter diagnostics."""
    encoder = tiktoken.get_encoding("cl100k_base")

    global_errors: list[str] = []
    chapters_report: list[dict] = []
    total_token_count = 0

    book_metadata = data.get("book_metadata")
    if not isinstance(book_metadata, dict):
        global_errors.append("Root key 'book_metadata' must be an object.")
    else:
        metadata_keys = set(book_metadata.keys())
        missing_metadata_keys = sorted(REQUIRED_BOOK_METADATA_KEYS - metadata_keys)
        if missing_metadata_keys:
            global_errors.append(f"book_metadata missing keys: {missing_metadata_keys}")

        for key in ("title", "subtitle", "author_line"):
            value = book_metadata.get(key)
            if not isinstance(value, str) or not value.strip():
                global_errors.append(f"book_metadata.{key} must be a non-empty string.")

        cover_data = book_metadata.get("cover")
        if not isinstance(cover_data, dict):
            global_errors.append("book_metadata.cover must be an object.")
        else:
            cover_keys = set(cover_data.keys())
            missing_cover_keys = sorted(REQUIRED_COVER_KEYS - cover_keys)
            if missing_cover_keys:
                global_errors.append(
                    f"book_metadata.cover missing keys: {missing_cover_keys}"
                )
            for key in REQUIRED_COVER_KEYS:
                value = cover_data.get(key)
                if not isinstance(value, str) or not value.strip():
                    global_errors.append(
                        f"book_metadata.cover.{key} must be a non-empty string."
                    )

    examples = data.get("examples")
    if not isinstance(examples, list):
        return {
            "is_valid": False,
            "chapter_count": 0,
            "total_token_count": 0,
            "errors": ["Root key 'examples' must be a list."],
            "chapters": [],
        }

    for chapter_index, chapter in enumerate(examples, start=1):
        chapter_errors: list[str] = []

        if not isinstance(chapter, dict):
            chapters_report.append(
                {
                    "chapter_index": chapter_index,
                    "source_file": None,
                    "chapter_type": None,
                    "paragraph_count": 0,
                    "chapter_token_count": 0,
                    "chapter_errors": ["Chapter entry must be an object."],
                }
            )
            continue

        chapter_keys = set(chapter.keys())
        missing_keys = sorted(EXPECTED_KEYS - chapter_keys)
        extra_keys = sorted(chapter_keys - EXPECTED_KEYS)
        if missing_keys:
            chapter_errors.append(f"Missing keys: {missing_keys}")
        if extra_keys:
            chapter_errors.append(f"Unexpected keys: {extra_keys}")

        source_file = chapter.get("source_file")
        chapter_type = chapter.get("chapter_type")
        chapter_title = chapter.get("chapter_title")
        paragraphs = chapter.get("paragraphs")

        if chapter_type not in {"prologue", "chapter"}:
            chapter_errors.append("'chapter_type' must be 'prologue' or 'chapter'.")

        if chapter_type == "prologue":
            if chapter.get("chapter_number") is not None:
                chapter_errors.append("Prologue must have null 'chapter_number'.")
            if chapter.get("chapter_label") is not None:
                chapter_errors.append("Prologue must have null 'chapter_label'.")
            if chapter_title is not None:
                chapter_errors.append("Prologue must have null 'chapter_title'.")

        if chapter_type == "chapter":
            if not isinstance(chapter.get("chapter_number"), int):
                chapter_errors.append("Chapter must have integer 'chapter_number'.")
            if (
                not isinstance(chapter.get("chapter_label"), str)
                or not chapter.get("chapter_label", "").strip()
            ):
                chapter_errors.append(
                    "Chapter must have non-empty string 'chapter_label'."
                )
            if not isinstance(chapter_title, str) or not chapter_title.strip():
                chapter_errors.append(
                    "Chapter must have non-empty string 'chapter_title'."
                )

        chapter_token_count = 0
        if isinstance(chapter_title, str):
            chapter_token_count += count_tokens(chapter_title, encoder)

        paragraph_count = 0
        if not isinstance(paragraphs, list):
            chapter_errors.append("'paragraphs' must be a list.")
        else:
            paragraph_count = len(paragraphs)
            for paragraph_pos, paragraph in enumerate(paragraphs, start=1):
                if not isinstance(paragraph, dict):
                    chapter_errors.append(
                        f"Paragraph #{paragraph_pos} must be an object."
                    )
                    continue

                paragraph_index = paragraph.get("paragraph_index")
                text = paragraph.get("text")

                if paragraph_index != paragraph_pos:
                    chapter_errors.append(
                        f"Paragraph index mismatch at position {paragraph_pos}: "
                        f"expected {paragraph_pos}, got {paragraph_index}."
                    )

                if not isinstance(text, str):
                    chapter_errors.append(
                        f"Paragraph #{paragraph_pos} has invalid 'text' type."
                    )
                    continue
                if not text.strip():
                    chapter_errors.append(f"Paragraph #{paragraph_pos} has empty text.")
                    continue

                chapter_token_count += count_tokens(text, encoder)

        total_token_count += chapter_token_count

        chapters_report.append(
            {
                "chapter_index": chapter_index,
                "source_file": source_file,
                "chapter_type": chapter_type,
                "paragraph_count": paragraph_count,
                "chapter_token_count": chapter_token_count,
                "chapter_errors": chapter_errors,
            }
        )

    for chapter_result in chapters_report:
        for error in chapter_result["chapter_errors"]:
            global_errors.append(
                f"{chapter_result['source_file'] or 'unknown'}: {error}"
            )

    return {
        "is_valid": len(global_errors) == 0,
        "chapter_count": len(examples),
        "total_token_count": total_token_count,
        "errors": global_errors,
        "chapters": chapters_report,
    }


def main() -> None:
    """Run validation and write report to `data/betrayal_validation_report.json`."""
    effective_log_level = configure_logging()
    logger.debug(
        "Starting validate_betrayal_json with LOG_LEVEL=%s", effective_log_level
    )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Reading input JSON from %s", INPUT_FILE)
    with INPUT_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    report = validate_and_count(data)

    with REPORT_FILE.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    status = "valid" if report["is_valid"] else "invalid"
    logger.info(
        "Validation %s. Chapters=%d total_tokens=%d",
        status,
        report["chapter_count"],
        report["total_token_count"],
    )
    if report["errors"]:
        logger.error(
            "Validation errors=%d. See %s", len(report["errors"]), REPORT_FILE.name
        )
    else:
        logger.info("Detailed chapter report written to %s", REPORT_FILE.name)


if __name__ == "__main__":
    main()
