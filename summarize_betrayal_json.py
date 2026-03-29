"""Summarize `data/betrayal.json` chapter by chapter into a JSON output file."""

import argparse
import time
from pathlib import Path

from jinja2 import TemplateNotFound

from eta_estimator import EtaEstimator
from ingest.logging_utils import configure_logging, get_logger
from ingest.pipeline_common import (
    call_openai_structured_with_retry,
    read_json,
    render_prompt_template,
    validate_with_schema,
    write_json,
)
from ingest.pipeline_params import (
    MAX_ATTEMPTS_DEFAULT,
    MODEL_DEFAULT,
    TIMEOUT_SECONDS_DEFAULT,
)
from project_paths import DATA_DIR, PROMPTS_DIR


logger = get_logger(__name__)

INPUT_FILE = DATA_DIR / "betrayal.json"
OUTPUT_FILE = DATA_DIR / "betrayal_short.json"
PROMPT_FILE = PROMPTS_DIR / "summarize.xml"
SUMMARY_MODEL_DEFAULT = MODEL_DEFAULT
SUMMARY_MAX_ATTEMPTS_DEFAULT = MAX_ATTEMPTS_DEFAULT

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
    """Resolve summarization model from project defaults.

    The summarizer intentionally does not read runtime env overrides for model
    selection to keep execution deterministic and explicit.
    """
    model_name = SUMMARY_MODEL_DEFAULT.strip()
    if not model_name:
        raise ValueError("Resolved summary model name is empty.")
    return model_name


def resolve_timeout_seconds() -> int:
    """Resolve timeout seconds from project defaults.

    The summarizer intentionally ignores environment overrides for timeout to
    avoid hidden runtime variability.
    """
    timeout_seconds = TIMEOUT_SECONDS_DEFAULT

    if timeout_seconds <= 0:
        raise ValueError("TIMEOUT_SECONDS_DEFAULT must be greater than zero.")
    return timeout_seconds


def resolve_max_attempts() -> int:
    """Resolve retry-attempt budget from project defaults.

    The summarizer intentionally ignores environment overrides for retry budget
    to keep retries consistent across runs.
    """
    max_attempts = SUMMARY_MAX_ATTEMPTS_DEFAULT

    if max_attempts <= 0:
        raise ValueError("SUMMARY_MAX_ATTEMPTS_DEFAULT must be greater than zero.")
    return max_attempts


def build_chapter_source_text(chapter: dict) -> str:
    """Build chapter body text payload used as source context for summarization.

    The chapter title is intentionally excluded from this body text. Title context
    is passed separately to reduce title-echo artifacts in generated paragraphs.
    """
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


def build_user_prompt(
    *,
    prompt_template_path: Path,
    chapter_source_text: str,
    chapter_title: str | None,
) -> str:
    """Render XML prompt template with explicit chapter context values.

    Missing template files fail fast with FileNotFoundError so callers receive a
    filesystem-oriented error instead of a template-loader implementation detail.
    """
    normalized_title = chapter_title.strip() if isinstance(chapter_title, str) else ""
    try:
        return render_prompt_template(
            prompt_template_path,
            {
                "chapter_title_context": normalized_title,
                "chapter_source": chapter_source_text,
            },
        )
    except TemplateNotFound as error:
        raise FileNotFoundError(
            f"Prompt template file not found: {prompt_template_path}"
        ) from error


def validate_summary_paragraphs(
    summary_paragraphs: list[str], chapter_title: str | None
) -> list[str]:
    """Validate and normalize model summary paragraphs.

    This validation intentionally stays minimal: enforce non-empty paragraphs and
    block title echo at paragraph start.
    """
    normalized_title = (
        chapter_title.strip().lower() if isinstance(chapter_title, str) else ""
    )
    cleaned_paragraphs: list[str] = []

    for paragraph_index, paragraph_text in enumerate(summary_paragraphs, start=1):
        normalized_paragraph = paragraph_text.strip()
        if not normalized_paragraph:
            raise ValueError(
                f"Summarizer returned empty paragraph at index {paragraph_index}."
            )

        if normalized_title:
            first_line = normalized_paragraph.splitlines()[0].strip().lower()
            if first_line == normalized_title:
                raise ValueError(
                    "Summarizer output repeats chapter title at paragraph index "
                    f"{paragraph_index}."
                )

        cleaned_paragraphs.append(normalized_paragraph)

    return cleaned_paragraphs


def format_duration_hms(total_seconds: float) -> str:
    """Format seconds as `Hh MMm SSs` for stable progress logging."""
    rounded_seconds = int(round(max(0.0, total_seconds)))
    hours, remainder = divmod(rounded_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes:02d}m {seconds:02d}s"


def summarize_chapter(
    chapter: dict,
    *,
    prompt_template_path: Path,
    chapter_source_text: str,
    model_name: str,
    timeout_seconds: int,
    max_attempts: int,
) -> list[dict[str, object]]:
    """Summarize one chapter into multiple indexed paragraph objects."""
    user_prompt = build_user_prompt(
        prompt_template_path=prompt_template_path,
        chapter_source_text=chapter_source_text,
        chapter_title=chapter.get("chapter_title"),
    )
    summary_data = call_openai_structured_with_retry(
        model=model_name,
        system_prompt="",
        user_prompt=user_prompt,
        schema_name="chapter_summary_paragraphs",
        schema=SUMMARY_RESPONSE_SCHEMA,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        result_validator=lambda payload: validate_summary_paragraphs(
            payload["summary_paragraphs"],
            chapter.get("chapter_title"),
        ),
    )
    validate_with_schema(summary_data, SUMMARY_RESPONSE_SCHEMA)

    summary_paragraphs = validate_summary_paragraphs(
        summary_data["summary_paragraphs"],
        chapter.get("chapter_title"),
    )
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


def resolve_output_file_path(*, chapter_limit: int | None) -> Path:
    """Resolve output file path and encode active CLI options in filename."""
    suffix_parts: list[str] = []
    if chapter_limit is not None:
        suffix_parts.append(f"limit_{chapter_limit}")

    if not suffix_parts:
        return OUTPUT_FILE

    suffix_token = "_".join(suffix_parts)
    resolved_file_name = f"{OUTPUT_FILE.stem}_{suffix_token}{OUTPUT_FILE.suffix}"
    return OUTPUT_FILE.with_name(resolved_file_name)


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
    max_attempts = resolve_max_attempts()
    output_file = resolve_output_file_path(chapter_limit=args.chapter_limit)
    logger.info(
        "Summarizing input=%s output=%s model=%s timeout_seconds=%d max_attempts=%d",
        INPUT_FILE,
        output_file,
        model_name,
        timeout_seconds,
        max_attempts,
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

    prepared_chapters = prepare_chapters_for_summarization(effective_examples)
    logger.info(
        "Validated all chapters before LLM calls processing_chapters=%d",
        len(prepared_chapters),
    )

    summarized_examples: list[dict[str, object]] = []
    total_chapters_to_process = len(prepared_chapters)
    eta_estimator: EtaEstimator | None = None
    if total_chapters_to_process > 0:
        eta_estimator = EtaEstimator(total_steps=total_chapters_to_process)

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
        chapter_started_at = time.perf_counter()
        summarized_paragraphs = summarize_chapter(
            chapter,
            prompt_template_path=PROMPT_FILE,
            chapter_source_text=chapter_source_text,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
        )
        chapter_elapsed_seconds = time.perf_counter() - chapter_started_at
        if eta_estimator is None:
            raise RuntimeError(
                "ETA estimator must be initialized for chapter processing."
            )
        eta_estimator.update(chapter_elapsed_seconds)

        chapter_duration_hms = format_duration_hms(chapter_elapsed_seconds)
        elapsed_hms = format_duration_hms(eta_estimator.elapsed_seconds)
        eta_remaining_hms = format_duration_hms(eta_estimator.eta_seconds)
        total_estimated_hms = format_duration_hms(eta_estimator.estimated_total_seconds)
        logger.info(
            "[%d/%d] Done source_file=%s chapter_duration=%s elapsed=%s eta_remaining=%s eta_total=%s",
            chapter_index,
            total_chapters_to_process,
            source_file,
            chapter_duration_hms,
            elapsed_hms,
            eta_remaining_hms,
            total_estimated_hms,
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
    write_json(output_file, output_payload)
    logger.info(
        "Generated %s with %d summarized chapters",
        output_file.name,
        len(summarized_examples),
    )


if __name__ == "__main__":
    main()
