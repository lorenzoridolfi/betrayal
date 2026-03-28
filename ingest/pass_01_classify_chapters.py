import argparse
import json
from pathlib import Path

from pipeline_common import (
    chapter_id_from_order,
    call_openai_structured_cached,
    load_schema,
    read_json,
    validate_with_schema,
    write_json,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
INPUT_FILE = DATA_DIR / "betrayal.json"
OUTPUT_FILE = DATA_DIR / "pass_01_chapter_classification.json"
SCHEMA_FILE = ROOT_DIR / "schemas" / "pass_01_chapter_classification.schema.json"
MODEL_DEFAULT = "gpt-5-mini"


SYSTEM_PROMPT = (
    "You classify chapters from a factual biography. "
    "Use only evidence from the chapter text and respond with valid JSON."
)


def build_user_prompt(chapter_payload: dict) -> str:
    return (
        "Analyze this chapter and return the requested JSON object.\n\n"
        "Requirements:\n"
        "- Use US English only.\n"
        "- Do not invent facts.\n"
        "- The chapter summary must be one paragraph in plain US English.\n"
        "- Keep chapter_id, chapter_order, chapter_number, and chapter_title aligned with the input.\n\n"
        f"Chapter input:\n{json.dumps(chapter_payload, ensure_ascii=False)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    args = parser.parse_args()

    schema = load_schema(SCHEMA_FILE)
    chapter_item_schema = schema["properties"]["chapters"]["items"]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    input_data = read_json(INPUT_FILE)
    examples = input_data.get("examples", [])

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
            system_prompt=SYSTEM_PROMPT,
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
    write_json(OUTPUT_FILE, output_data)
    print(f"Wrote {OUTPUT_FILE.name} with {len(chapters_out)} chapters.")


if __name__ == "__main__":
    main()
