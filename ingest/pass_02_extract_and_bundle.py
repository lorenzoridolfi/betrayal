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
BOOK_FILE = DATA_DIR / "betrayal.json"
CLASSIFICATION_FILE = DATA_DIR / "pass_01_chapter_classification.json"
OUTPUT_FILE = DATA_DIR / "rag_ingest_bundle.json"
SCHEMA_FILE = ROOT_DIR / "schemas" / "pass_02_rag_bundle.schema.json"
MODEL_DEFAULT = "gpt-5-mini"


SYSTEM_PROMPT = (
    "You extract structured chapter data from a factual biography. "
    "Use only evidence from the chapter text and return valid JSON."
)


def build_user_prompt(chapter_payload: dict) -> str:
    return (
        "Analyze this chapter and return the requested JSON object.\n\n"
        "Requirements:\n"
        "- Use US English only.\n"
        "- Do not invent facts.\n"
        "- Confirm or correct the preliminary chapter kind.\n"
        "- Rewrite chunk text to plain, accessible US English.\n"
        "- Keep chapter metadata aligned with the input.\n"
        "- Keep chunk order consistent with the narrative order.\n\n"
        f"Chapter input:\n{json.dumps(chapter_payload, ensure_ascii=False)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_schema = load_schema(SCHEMA_FILE)
    chapter_item_schema = output_schema["properties"]["chapters"]["items"]
    chapter_item_schema_with_defs = {
        "$defs": output_schema.get("$defs", {}),
        **chapter_item_schema,
    }

    book_data = read_json(BOOK_FILE)
    classification_data = read_json(CLASSIFICATION_FILE)

    examples = book_data.get("examples", [])
    preliminary = {
        item["chapter_id"]: item for item in classification_data.get("chapters", [])
    }

    chapters_out = []
    for index, chapter in enumerate(examples, start=1):
        chapter_id = chapter_id_from_order(index)
        prelim_item = preliminary.get(chapter_id)
        if prelim_item is None:
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
        }

        chapter_result = call_openai_structured_cached(
            model=args.model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(chapter_payload),
            schema_name="pass_02_rag_bundle_chapter_item",
            schema=chapter_item_schema_with_defs,
            input_payload=chapter_payload,
            timeout_seconds=args.timeout_seconds,
        )

        validate_with_schema(chapter_result, chapter_item_schema_with_defs)
        chapters_out.append(chapter_result)

    output_data = {
        "book_id": "betrayal",
        "chapters": chapters_out,
    }
    validate_with_schema(output_data, output_schema)
    write_json(OUTPUT_FILE, output_data)
    print(f"Wrote {OUTPUT_FILE.name} with {len(chapters_out)} chapters.")


if __name__ == "__main__":
    main()
