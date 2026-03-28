"""Pass 02: extract structured chapter data and build the ingest bundle."""

import argparse
import json
from pathlib import Path

from logging_utils import configure_logging, get_logger
from pipeline_params import (
    BOOK_ID,
    DATA_DIR,
    MODEL_DEFAULT,
    PASS_02_ITEM_SCHEMA_FILE,
    PASS_02_PIPELINE_VERSION,
    PASS_02_SCHEMA_FILE,
    PASS_02_SCHEMA_VERSION,
    PASS_02_SYSTEM_PROMPT_FILE,
    PASS_02_USER_PROMPT_TEMPLATE_FILE,
    PROFILE_DEFAULT,
    TIMEOUT_SECONDS_DEFAULT,
    get_profile,
    list_profiles,
)
from pipeline_common import (
    chapter_id_from_order,
    call_openai_structured_cached,
    load_schema,
    read_json,
    read_text_file,
    render_prompt_template,
    validate_with_schema,
    write_json,
)


logger = get_logger(__name__)


def build_user_prompt(chapter_payload: dict) -> str:
    """Render the pass-02 user prompt from the chapter payload."""
    return render_prompt_template(
        PASS_02_USER_PROMPT_TEMPLATE_FILE,
        {"chapter_payload_json": json.dumps(chapter_payload, ensure_ascii=False)},
    )


def build_extraction_context(model_name: str) -> dict[str, str]:
    """Build deterministic extraction metadata required in each chapter output."""
    return {
        "schema_version": PASS_02_SCHEMA_VERSION,
        "pipeline_version": PASS_02_PIPELINE_VERSION,
        "extraction_model": model_name,
    }


def main() -> None:
    """Run pass 02 for the selected profile and write validated output."""
    effective_log_level = configure_logging()
    logger.debug("Starting pass_02 with LOG_LEVEL=%s", effective_log_level)

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--timeout-seconds", type=int, default=TIMEOUT_SECONDS_DEFAULT)
    parser.add_argument("--profile", choices=list_profiles(), default=PROFILE_DEFAULT)
    parser.add_argument("--book-file", default=None)
    parser.add_argument("--classification-file", default=None)
    parser.add_argument("--output-file", default=None)
    args = parser.parse_args()

    profile = get_profile(args.profile)
    book_file = Path(args.book_file) if args.book_file else profile["book_file"]
    default_classification = profile["pass_01_5_output"]
    classification_file = (
        Path(args.classification_file)
        if args.classification_file
        else default_classification
    )
    output_file = (
        Path(args.output_file) if args.output_file else profile["pass_02_output"]
    )
    chapter_limit = profile["chapter_limit"]
    system_prompt = read_text_file(PASS_02_SYSTEM_PROMPT_FILE)
    extraction_context = build_extraction_context(args.model)
    logger.info(
        "pass_02 profile=%s book_input=%s classification_input=%s output=%s",
        args.profile,
        book_file,
        classification_file,
        output_file,
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_schema = load_schema(PASS_02_SCHEMA_FILE)
    llm_chapter_schema = load_schema(PASS_02_ITEM_SCHEMA_FILE)

    book_data = read_json(book_file)
    classification_data = read_json(classification_file)

    examples = book_data.get("examples", [])
    if chapter_limit is not None:
        examples = examples[:chapter_limit]
    preliminary = {
        item["chapter_id"]: item for item in classification_data.get("chapters", [])
    }

    chapters_out = []
    for index, chapter in enumerate(examples, start=1):
        chapter_id = chapter_id_from_order(index)
        logger.debug(
            "pass_02 extracting chapter_id=%s chapter_order=%d", chapter_id, index
        )
        prelim_item = preliminary.get(chapter_id)
        if prelim_item is None:
            logger.error("Missing preliminary chapter for chapter_id=%s", chapter_id)
            raise ValueError(f"Missing preliminary chapter for {chapter_id}")

        paragraph_texts = [p.get("text", "") for p in chapter.get("paragraphs", [])]
        chapter_text = "\n\n".join(text for text in paragraph_texts if text)

        chapter_payload = {
            "chapter_id": chapter_id,
            "chapter_order": index,
            "source_file": chapter.get("source_file"),
            "chapter_type": chapter.get("chapter_type"),
            "chapter_number": chapter.get("chapter_number"),
            "chapter_title": chapter.get("chapter_title"),
            "chapter_text": chapter_text,
            "paragraphs": chapter.get("paragraphs", []),
            "preliminary": prelim_item,
            "extraction_context": extraction_context,
        }

        chapter_result = call_openai_structured_cached(
            model=args.model,
            system_prompt=system_prompt,
            user_prompt=build_user_prompt(chapter_payload),
            schema_name="pass_02_rag_bundle_chapter_item",
            schema=llm_chapter_schema,
            input_payload=chapter_payload,
            timeout_seconds=args.timeout_seconds,
        )
        validate_with_schema(chapter_result, llm_chapter_schema)

        chapter_result["schema_version"] = extraction_context["schema_version"]
        chapter_result["pipeline_version"] = extraction_context["pipeline_version"]
        chapter_result["extraction_model"] = extraction_context["extraction_model"]

        chapter_result["chapter_kind_preliminary"] = prelim_item[
            "chapter_kind_preliminary"
        ]
        chapter_result["chapter_kind_changed"] = (
            chapter_result["chapter_kind"] != prelim_item["chapter_kind_preliminary"]
        )
        rationale = chapter_result.get("chapter_kind_change_rationale", "").strip()
        if not rationale:
            if chapter_result["chapter_kind_changed"]:
                chapter_result["chapter_kind_change_rationale"] = (
                    "The chapter evidence supports a different dominant mode than the preliminary label."
                )
            else:
                chapter_result["chapter_kind_change_rationale"] = (
                    "No change was needed because the preliminary and final chapter kinds match."
                )

        validate_with_schema(
            {"book_id": BOOK_ID, "chapters": [chapter_result]},
            output_schema,
        )
        chapters_out.append(chapter_result)

    output_data = {
        "book_id": BOOK_ID,
        "chapters": chapters_out,
    }
    validate_with_schema(output_data, output_schema)
    write_json(output_file, output_data)
    logger.info(
        "pass_02 wrote %s with %d chapters", output_file.name, len(chapters_out)
    )


if __name__ == "__main__":
    main()
