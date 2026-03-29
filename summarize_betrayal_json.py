"""Summarize `data/betrayal.json` into `data/betrayal_short.json` chapter by chapter."""

import argparse
import json
import os
from pathlib import Path

from ingest.logging_utils import configure_logging, get_logger
from ingest.pipeline_common import (
    read_json,
    read_text_file,
    validate_with_schema,
    write_json,
)
from ingest.pipeline_params import TIMEOUT_SECONDS_DEFAULT
from openai_structured_cache import call_openai_structured_cached
from project_paths import DATA_DIR, PROMPTS_DIR


logger = get_logger(__name__)

INPUT_FILE = DATA_DIR / "betrayal.json"
OUTPUT_FILE = DATA_DIR / "betrayal_short.json"
PROMPT_FILE = PROMPTS_DIR / "summarize.txt"
SUMMARY_MODEL_ENV_VAR = "SUMMARY_MODEL"
SUMMARY_TIMEOUT_SECONDS_ENV_VAR = "SUMMARY_TIMEOUT_SECONDS"
SUMMARY_MODEL_DEFAULT = "gpt-5.4"

SUMMARY_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary_paragraphs": {
            "type": "array",
            "minItems": 2,
            "items": {"type": "string", "minLength": 1},
            "description": "Multiple summary paragraphs preserving chronology and key facts.",
        }
    },
    "required": ["summary_paragraphs"],
}

REQUIRED_BOOK_METADATA_KEYS = ("title", "subtitle", "author_line", "cover")
REQUIRED_COVER_KEYS = ("source_file", "image_src", "image_alt")


def resolve_model_name() -> str:
    """Resolve the summarization model from environment or default constant."""
    model_name = os.environ.get(SUMMARY_MODEL_ENV_VAR, SUMMARY_MODEL_DEFAULT).strip()
    if not model_name:
        raise ValueError("Resolved summary model name is empty.")
    return model_name


def resolve_timeout_seconds() -> int:
    """Resolve timeout seconds from environment or default constant."""
    raw_timeout = os.environ.get(
        SUMMARY_TIMEOUT_SECONDS_ENV_VAR, str(TIMEOUT_SECONDS_DEFAULT)
    )
    try:
        timeout_seconds = int(raw_timeout)
    except ValueError as error:
        raise ValueError(
            f"{SUMMARY_TIMEOUT_SECONDS_ENV_VAR} must be an integer. Got '{raw_timeout}'."
        ) from error

    if timeout_seconds <= 0:
        raise ValueError(
            f"{SUMMARY_TIMEOUT_SECONDS_ENV_VAR} must be greater than zero."
        )
    return timeout_seconds


def build_chapter_source_text(chapter: dict) -> str:
    """Build chapter text payload used as source context for summarization."""
    paragraphs = chapter.get("paragraphs")
    if not isinstance(paragraphs, list):
        raise ValueError("Chapter paragraphs must be a list.")

    paragraph_texts: list[str] = []
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            raise ValueError("Each chapter paragraph must be an object.")
        text = paragraph.get("text")
        if not isinstance(text, str):
            raise ValueError("Each paragraph text must be a string.")
        clean_text = text.strip()
        if clean_text:
            paragraph_texts.append(clean_text)

    if not paragraph_texts:
        raise ValueError("Chapter has no non-empty paragraph text to summarize.")

    chapter_title = chapter.get("chapter_title")
    if isinstance(chapter_title, str) and chapter_title.strip():
        return f"{chapter_title.strip()}\n\n" + "\n\n".join(paragraph_texts)
    return "\n\n".join(paragraph_texts)


def validate_book_metadata(book_metadata: dict) -> None:
    """Validate minimal book metadata fields required for output propagation."""
    for key in REQUIRED_BOOK_METADATA_KEYS:
        if key not in book_metadata:
            raise ValueError(f"Input book_metadata missing required key '{key}'.")

    for key in ("title", "subtitle", "author_line"):
        value = book_metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"book_metadata.{key} must be a non-empty string.")

    cover_data = book_metadata.get("cover")
    if not isinstance(cover_data, dict):
        raise ValueError("book_metadata.cover must be an object.")

    for key in REQUIRED_COVER_KEYS:
        value = cover_data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"book_metadata.cover.{key} must be a non-empty string.")


def prepare_chapters_for_summarization(
    effective_examples: list[dict],
) -> list[tuple[dict, str]]:
    """Validate all chapters up front and return chapter/source-text pairs."""
    prepared_chapters: list[tuple[dict, str]] = []
    for chapter_index, chapter in enumerate(effective_examples, start=1):
        if not isinstance(chapter, dict):
            raise ValueError(f"Chapter at index {chapter_index} must be an object.")

        chapter_source_text = build_chapter_source_text(chapter)
        prepared_chapters.append((chapter, chapter_source_text))
    return prepared_chapters


def build_user_prompt(base_prompt: str, chapter_source_text: str) -> str:
    """Build chapter prompt from reference guidance plus minimal JSON contract."""
    return (
        f"{base_prompt}\n\n"
        "For this API response, return a JSON object with a single key 'summary_paragraphs' "
        "containing multiple prose paragraphs in order.\n\n"
        "Chapter source:\n"
        f"{chapter_source_text}"
    )


def summarize_chapter(
    chapter: dict,
    *,
    chapter_source_text: str,
    base_prompt: str,
    model_name: str,
    timeout_seconds: int,
) -> list[dict[str, object]]:
    """Summarize one chapter into multiple indexed paragraph objects."""
    user_prompt = build_user_prompt(base_prompt, chapter_source_text)
    summary_data = call_openai_structured_cached(
        model=model_name,
        system_prompt="",
        user_prompt=user_prompt,
        schema_name="chapter_summary_paragraphs",
        schema=SUMMARY_RESPONSE_SCHEMA,
        input_payload={
            "source_file": chapter.get("source_file"),
            "chapter_title": chapter.get("chapter_title"),
            "chapter_source_text": chapter_source_text,
        },
        timeout_seconds=timeout_seconds,
    )
    validate_with_schema(summary_data, SUMMARY_RESPONSE_SCHEMA)

    summary_paragraphs = summary_data["summary_paragraphs"]
    return [
        {"paragraph_index": index, "text": text.strip()}
        for index, text in enumerate(summary_paragraphs, start=1)
    ]


def resolve_effective_examples(
    examples: list[dict], chapter_limit: int | None
) -> list[dict]:
    """Return chapter list truncated to requested limit when provided."""
    if chapter_limit is None:
        return examples
    if chapter_limit <= 0:
        raise ValueError("--chapter-limit must be greater than zero.")
    return examples[:chapter_limit]


def main() -> None:
    """Generate summarized chapter JSON and preserve book metadata."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chapter-limit",
        type=int,
        default=None,
        help="Summarize only the first N chapters.",
    )
    args = parser.parse_args()

    effective_log_level = configure_logging()
    logger.debug(
        "Starting summarize_betrayal_json with LOG_LEVEL=%s", effective_log_level
    )

    model_name = resolve_model_name()
    timeout_seconds = resolve_timeout_seconds()
    logger.info(
        "Summarizing input=%s output=%s model=%s timeout_seconds=%d",
        INPUT_FILE,
        OUTPUT_FILE,
        model_name,
        timeout_seconds,
    )

    data = read_json(INPUT_FILE)
    book_metadata = data.get("book_metadata")
    examples = data.get("examples")
    if not isinstance(book_metadata, dict):
        raise ValueError("Input JSON must contain object key 'book_metadata'.")
    validate_book_metadata(book_metadata)
    if not isinstance(examples, list):
        raise ValueError("Input JSON must contain list key 'examples'.")

    effective_examples = resolve_effective_examples(examples, args.chapter_limit)
    logger.info(
        "Summarization chapter_limit=%s total_chapters=%d processing_chapters=%d",
        args.chapter_limit,
        len(examples),
        len(effective_examples),
    )

    base_prompt = read_text_file(PROMPT_FILE)
    prepared_chapters = prepare_chapters_for_summarization(effective_examples)
    logger.info(
        "Validated all chapters before LLM calls processing_chapters=%d",
        len(prepared_chapters),
    )

    summarized_examples: list[dict[str, object]] = []
    total_chapters_to_process = len(prepared_chapters)
    for chapter_index, (chapter, chapter_source_text) in enumerate(
        prepared_chapters, start=1
    ):
        source_file = chapter.get("source_file")
        logger.info(
            "[%d/%d] Summarizing source_file=%s",
            chapter_index,
            total_chapters_to_process,
            source_file,
        )
        summarized_paragraphs = summarize_chapter(
            chapter,
            chapter_source_text=chapter_source_text,
            base_prompt=base_prompt,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
        )
        summarized_examples.append(
            {
                "source_file": chapter.get("source_file"),
                "chapter_type": chapter.get("chapter_type"),
                "chapter_number": chapter.get("chapter_number"),
                "chapter_label": chapter.get("chapter_label"),
                "chapter_title": chapter.get("chapter_title"),
                "paragraphs": summarized_paragraphs,
            }
        )

    output_payload = {
        "book_metadata": book_metadata,
        "examples": summarized_examples,
    }
    write_json(OUTPUT_FILE, output_payload)
    logger.info(
        "Generated %s with %d summarized chapters",
        OUTPUT_FILE.name,
        len(summarized_examples),
    )


if __name__ == "__main__":
    main()
