import argparse
import copy
import json
from pathlib import Path

from pipeline_params import (
    DATA_DIR,
    MODEL_DEFAULT,
    PASS_02_SCHEMA_FILE,
    TIMEOUT_SECONDS_DEFAULT,
    get_profile,
    list_profiles,
)
from pipeline_common import (
    chapter_id_from_order,
    call_openai_structured_cached,
    load_schema,
    read_json,
    validate_with_schema,
    write_json,
)


ROOT_DIR = Path(__file__).resolve().parents[1]


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
        "- If you change the chapter kind, explain why in chapter_kind_change_rationale.\n"
        "- If you keep the same kind, state that no change was needed.\n"
        "- Rewrite chunk text to plain, accessible US English.\n"
        "- Keep chapter metadata aligned with the input.\n"
        "- Keep chunk order consistent with the narrative order.\n\n"
        f"Chapter input:\n{json.dumps(chapter_payload, ensure_ascii=False)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--timeout-seconds", type=int, default=TIMEOUT_SECONDS_DEFAULT)
    parser.add_argument("--profile", choices=list_profiles(), default="full")
    parser.add_argument("--book-file", default=None)
    parser.add_argument("--classification-file", default=None)
    parser.add_argument("--output-file", default=None)
    args = parser.parse_args()

    profile = get_profile(args.profile)
    book_file = Path(args.book_file) if args.book_file else profile["book_file"]
    default_classification = profile["pass_01_output"]
    classification_file = (
        Path(args.classification_file)
        if args.classification_file
        else default_classification
    )
    output_file = (
        Path(args.output_file) if args.output_file else profile["pass_02_output"]
    )
    chapter_limit = profile["chapter_limit"]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_schema = load_schema(PASS_02_SCHEMA_FILE)
    chapter_item_schema = output_schema["properties"]["chapters"]["items"]
    chapter_item_schema_with_defs = {
        "$defs": output_schema.get("$defs", {}),
        **chapter_item_schema,
    }
    llm_chapter_schema = copy.deepcopy(chapter_item_schema_with_defs)
    llm_chapter_schema["properties"].pop("chapter_kind_preliminary", None)
    llm_chapter_schema["properties"].pop("chapter_kind_changed", None)
    llm_chapter_schema["properties"].pop("chapter_kind_change_rationale", None)
    llm_chapter_schema["required"] = [
        field
        for field in llm_chapter_schema["required"]
        if field
        not in {
            "chapter_kind_preliminary",
            "chapter_kind_changed",
            "chapter_kind_change_rationale",
        }
    ]

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
            schema=llm_chapter_schema,
            input_payload=chapter_payload,
            timeout_seconds=args.timeout_seconds,
        )

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

        validate_with_schema(chapter_result, chapter_item_schema_with_defs)
        chapters_out.append(chapter_result)

    output_data = {
        "book_id": "betrayal",
        "chapters": chapters_out,
    }
    validate_with_schema(output_data, output_schema)
    write_json(output_file, output_data)
    print(f"Wrote {output_file.name} with {len(chapters_out)} chapters.")


if __name__ == "__main__":
    main()
