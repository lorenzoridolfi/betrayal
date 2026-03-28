import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
INGEST_DIR = ROOT_DIR / "ingest"
if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import pass_01_classify_chapters as pass_01


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _build_input(chapter_count: int) -> dict:
    examples = []
    for index in range(chapter_count):
        examples.append(
            {
                "source_file": f"{index + 8:03d}-Chapter_{index + 1}.xhtml",
                "chapter_type": "chapter",
                "chapter_number": index + 1,
                "chapter_label": f"CHAPTER {index + 1}",
                "chapter_title": f"Title {index + 1}",
                "paragraphs": [
                    {"paragraph_index": 1, "text": f"Sample text {index + 1}."}
                ],
            }
        )
    return {"examples": examples}


def _valid_pass_01_item(
    chapter_id: str, chapter_order: int, chapter_number: int
) -> dict:
    return {
        "chapter_id": chapter_id,
        "chapter_order": chapter_order,
        "chapter_number": chapter_number,
        "chapter_title": f"Title {chapter_number}",
        "chapter_kind_preliminary": "narrative",
        "classification_confidence": "high",
        "classification_rationale": "Most of the chapter is event-driven.",
        "dominant_entities": ["Harry", "Meghan"],
        "dominant_timeframe": "September 2022",
        "possible_themes": ["media", "royal conflict"],
        "chapter_summary_preliminary": "This chapter describes a sequence of public events and conflict with clear factual claims.",
    }


class Pass01Tests(unittest.TestCase):
    def test_writes_valid_output_for_one_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "pass_01_chapter_classification.json"
            _write_json(input_file, _build_input(1))

            with (
                patch.object(pass_01, "INPUT_FILE", input_file),
                patch.object(pass_01, "OUTPUT_FILE", output_file),
                patch.object(pass_01, "DATA_DIR", temp_path / "data"),
                patch.object(
                    pass_01,
                    "SCHEMA_FILE",
                    ROOT_DIR / "schemas" / "pass_01_chapter_classification.schema.json",
                ),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_01_item("betrayal-001", 1, 1),
                ) as llm_mock,
                patch.object(sys, "argv", ["pass_01_classify_chapters.py"]),
            ):
                pass_01.main()

            self.assertTrue(output_file.exists())
            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(data["book_id"], "betrayal")
            self.assertEqual(len(data["chapters"]), 1)
            self.assertEqual(data["chapters"][0]["chapter_id"], "betrayal-001")
            self.assertEqual(llm_mock.call_count, 1)

    def test_calls_llm_once_per_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "pass_01_chapter_classification.json"
            _write_json(input_file, _build_input(2))

            side_effect = [
                _valid_pass_01_item("betrayal-001", 1, 1),
                _valid_pass_01_item("betrayal-002", 2, 2),
            ]

            with (
                patch.object(pass_01, "INPUT_FILE", input_file),
                patch.object(pass_01, "OUTPUT_FILE", output_file),
                patch.object(pass_01, "DATA_DIR", temp_path / "data"),
                patch.object(
                    pass_01,
                    "SCHEMA_FILE",
                    ROOT_DIR / "schemas" / "pass_01_chapter_classification.schema.json",
                ),
                patch.object(
                    pass_01, "call_openai_structured_cached", side_effect=side_effect
                ) as llm_mock,
                patch.object(sys, "argv", ["pass_01_classify_chapters.py"]),
            ):
                pass_01.main()

            self.assertEqual(llm_mock.call_count, 2)

    def test_fails_when_llm_payload_is_schema_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "pass_01_chapter_classification.json"
            _write_json(input_file, _build_input(1))

            with (
                patch.object(pass_01, "INPUT_FILE", input_file),
                patch.object(pass_01, "OUTPUT_FILE", output_file),
                patch.object(pass_01, "DATA_DIR", temp_path / "data"),
                patch.object(
                    pass_01,
                    "SCHEMA_FILE",
                    ROOT_DIR / "schemas" / "pass_01_chapter_classification.schema.json",
                ),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value={"bad": "payload"},
                ),
                patch.object(sys, "argv", ["pass_01_classify_chapters.py"]),
            ):
                with self.assertRaises(Exception):
                    pass_01.main()

    def test_handles_empty_examples_without_llm_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "pass_01_chapter_classification.json"
            _write_json(input_file, {"examples": []})

            with (
                patch.object(pass_01, "INPUT_FILE", input_file),
                patch.object(pass_01, "OUTPUT_FILE", output_file),
                patch.object(pass_01, "DATA_DIR", temp_path / "data"),
                patch.object(
                    pass_01,
                    "SCHEMA_FILE",
                    ROOT_DIR / "schemas" / "pass_01_chapter_classification.schema.json",
                ),
                patch.object(pass_01, "call_openai_structured_cached") as llm_mock,
                patch.object(sys, "argv", ["pass_01_classify_chapters.py"]),
            ):
                pass_01.main()

            self.assertEqual(llm_mock.call_count, 0)
            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(data, {"book_id": "betrayal", "chapters": []})

    def test_passes_expected_generated_chapter_id_to_llm_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "pass_01_chapter_classification.json"
            _write_json(input_file, _build_input(1))

            with (
                patch.object(pass_01, "INPUT_FILE", input_file),
                patch.object(pass_01, "OUTPUT_FILE", output_file),
                patch.object(pass_01, "DATA_DIR", temp_path / "data"),
                patch.object(
                    pass_01,
                    "SCHEMA_FILE",
                    ROOT_DIR / "schemas" / "pass_01_chapter_classification.schema.json",
                ),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_01_item("betrayal-001", 1, 1),
                ) as llm_mock,
                patch.object(sys, "argv", ["pass_01_classify_chapters.py"]),
            ):
                pass_01.main()

            payload = llm_mock.call_args.kwargs["input_payload"]
            self.assertEqual(payload["chapter_id"], "betrayal-001")
            self.assertEqual(payload["chapter_order"], 1)

    def test_output_preserves_llm_identity_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "pass_01_chapter_classification.json"
            _write_json(input_file, _build_input(1))

            llm_item = _valid_pass_01_item("betrayal-001", 1, 1)
            llm_item["chapter_kind_preliminary"] = "analysis"
            llm_item["classification_confidence"] = "medium"

            with (
                patch.object(pass_01, "INPUT_FILE", input_file),
                patch.object(pass_01, "OUTPUT_FILE", output_file),
                patch.object(pass_01, "DATA_DIR", temp_path / "data"),
                patch.object(
                    pass_01,
                    "SCHEMA_FILE",
                    ROOT_DIR / "schemas" / "pass_01_chapter_classification.schema.json",
                ),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value=llm_item,
                ),
                patch.object(sys, "argv", ["pass_01_classify_chapters.py"]),
            ):
                pass_01.main()

            data = json.loads(output_file.read_text(encoding="utf-8"))
            out_item = data["chapters"][0]
            self.assertEqual(out_item["chapter_kind_preliminary"], "analysis")
            self.assertEqual(out_item["classification_confidence"], "medium")


if __name__ == "__main__":
    unittest.main()
