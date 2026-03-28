"""Pass 01: classify each chapter into a preliminary chapter kind."""

import argparse
import json
from pathlib import Path

from pipeline_params import (
    DATA_DIR,
    PASS_01_ITEM_SCHEMA_FILE,
    MODEL_DEFAULT,
    PASS_01_SCHEMA_FILE,
    PASS_01_SYSTEM_PROMPT_FILE,
    PASS_01_USER_PROMPT_TEMPLATE_FILE,
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


def build_user_prompt(chapter_payload: dict) -> str:
    """Render the pass-01 user prompt from the chapter payload."""
    return render_prompt_template(
        PASS_01_USER_PROMPT_TEMPLATE_FILE,
        {"chapter_payload_json": json.dumps(chapter_payload, ensure_ascii=False)},
    )


def main() -> None:
    """Run pass 01 for the selected profile and write validated output."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--timeout-seconds", type=int, default=TIMEOUT_SECONDS_DEFAULT)
    parser.add_argument("--profile", choices=list_profiles(), default=PROFILE_DEFAULT)
    parser.add_argument("--input-file", default=None)
    parser.add_argument("--output-file", default=None)
    args = parser.parse_args()

    profile = get_profile(args.profile)
    input_file = Path(args.input_file) if args.input_file else profile["book_file"]
    output_file = (
        Path(args.output_file) if args.output_file else profile["pass_01_output"]
    )
    chapter_limit = profile["chapter_limit"]
    system_prompt = read_text_file(PASS_01_SYSTEM_PROMPT_FILE)

    schema = load_schema(PASS_01_SCHEMA_FILE)
    chapter_item_schema = load_schema(PASS_01_ITEM_SCHEMA_FILE)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    input_data = read_json(input_file)
    examples = input_data.get("examples", [])
    if chapter_limit is not None:
        examples = examples[:chapter_limit]

    chapters_out = []
    for index, chapter in enumerate(examples, start=1):
        chapter_id = chapter_id_from_order(index)
        paragraph_texts = [p.get("text", "") for p in chapter.get("paragraphs", [])]
        chapter_text = "\n\n".join(text for text in paragraph_texts if text)

        chapter_payload = {
            "chapter_id": chapter_id,
            "chapter_order": index,
            "chapter_number": chapter.get("chapter_number"),
            "chapter_title": chapter.get("chapter_title"),
            "source_file": chapter.get("source_file"),
            "chapter_type": chapter.get("chapter_type"),
            "chapter_text": chapter_text,
        }

        chapter_result = call_openai_structured_cached(
            model=args.model,
            system_prompt=system_prompt,
            user_prompt=build_user_prompt(chapter_payload),
            schema_name="pass_01_chapter_classification_item",
            schema=chapter_item_schema,
            input_payload=chapter_payload,
            timeout_seconds=args.timeout_seconds,
        )

        validate_with_schema(chapter_result, chapter_item_schema)
        chapters_out.append(chapter_result)

    output_data = {
        "book_id": "betrayal",
        "chapters": chapters_out,
    }
    validate_with_schema(output_data, schema)
    write_json(output_file, output_data)
    print(f"Wrote {output_file.name} with {len(chapters_out)} chapters.")


if __name__ == "__main__":
    main()
