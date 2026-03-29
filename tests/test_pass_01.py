"""Tests for pass_01 chapter classification behavior."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError
from project_paths import DATA_DIR, INGEST_DIR, PROMPTS_DIR, SCHEMAS_DIR


if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import pass_01_classify_chapters as pass_01
from pipeline_params import (
    BOOK_FILE,
    PASS_01_OUTPUT_FULL,
    PASS_01_OUTPUT_PREVIEW,
    PASS_01_ITEM_SCHEMA_FILE,
    PROFILE_DEFAULT,
    PROFILE_PREVIEW,
)


BOOK_FILENAME = BOOK_FILE.name
PASS_01_OUTPUT_FULL_FILENAME = PASS_01_OUTPUT_FULL.name
PASS_01_OUTPUT_PREVIEW_FILENAME = PASS_01_OUTPUT_PREVIEW.name
PASS_01_ITEM_SCHEMA_FILENAME = PASS_01_ITEM_SCHEMA_FILE.name
TEST_DATA_DIRNAME = DATA_DIR.name
TEST_PROMPTS_DIRNAME = PROMPTS_DIR.name
TEST_SCHEMAS_DIRNAME = SCHEMAS_DIR.name


def _write_json(path: Path, data: dict) -> None:
    """Write JSON test fixtures using UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _build_input(chapter_count: int) -> dict:
    """Create synthetic chapter input payload for tests."""
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
    """Return a schema-valid pass_01 chapter item."""
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
    """End-to-end unit tests for pass_01 script flow."""

    def _run_pass_01(
        self,
        *,
        input_file: Path,
        output_file: Path,
        profile: str = PROFILE_DEFAULT,
    ) -> None:
        """Invoke pass_01.main with deterministic CLI args."""
        argv = [
            "pass_01_classify_chapters.py",
            "--profile",
            profile,
            "--input-file",
            str(input_file),
            "--output-file",
            str(output_file),
        ]
        with patch.object(sys, "argv", argv):
            pass_01.main()

    def test_writes_valid_output_for_one_chapter(self) -> None:
        """One valid chapter should produce one output chapter item."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            _write_json(input_file, _build_input(1))

            with (
                patch.object(pass_01, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_01_item("betrayal-001", 1, 1),
                ) as llm_mock,
            ):
                self._run_pass_01(input_file=input_file, output_file=output_file)

            self.assertTrue(output_file.exists())
            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(data["book_id"], "betrayal")
            self.assertEqual(len(data["chapters"]), 1)
            self.assertEqual(data["chapters"][0]["chapter_id"], "betrayal-001")
            self.assertEqual(llm_mock.call_count, 1)

    def test_calls_llm_once_per_chapter(self) -> None:
        """LLM call count should match processed chapter count."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            _write_json(input_file, _build_input(2))

            side_effect = [
                _valid_pass_01_item("betrayal-001", 1, 1),
                _valid_pass_01_item("betrayal-002", 2, 2),
            ]

            with (
                patch.object(pass_01, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_01, "call_openai_structured_cached", side_effect=side_effect
                ) as llm_mock,
            ):
                self._run_pass_01(input_file=input_file, output_file=output_file)

            self.assertEqual(llm_mock.call_count, 2)

    def test_fails_when_llm_payload_is_schema_invalid(self) -> None:
        """Schema-invalid LLM payload should fail pass_01 execution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            _write_json(input_file, _build_input(1))

            with (
                patch.object(pass_01, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value={"bad": "payload"},
                ),
            ):
                with self.assertRaises(ValidationError):
                    self._run_pass_01(input_file=input_file, output_file=output_file)

    def test_handles_empty_examples_without_llm_calls(self) -> None:
        """Empty input should skip LLM and write empty chapters list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            _write_json(input_file, {"examples": []})

            with (
                patch.object(pass_01, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(pass_01, "call_openai_structured_cached") as llm_mock,
            ):
                self._run_pass_01(input_file=input_file, output_file=output_file)

            self.assertEqual(llm_mock.call_count, 0)
            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(data, {"book_id": "betrayal", "chapters": []})

    def test_passes_expected_generated_chapter_id_to_llm_payload(self) -> None:
        """Generated chapter_id/order should be forwarded into LLM payload."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            _write_json(input_file, _build_input(1))

            with (
                patch.object(pass_01, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_01_item("betrayal-001", 1, 1),
                ) as llm_mock,
            ):
                self._run_pass_01(input_file=input_file, output_file=output_file)

            payload = llm_mock.call_args.kwargs["input_payload"]
            self.assertEqual(payload["chapter_id"], "betrayal-001")
            self.assertEqual(payload["chapter_order"], 1)

    def test_output_preserves_llm_identity_fields(self) -> None:
        """Output should preserve identity/classification fields from LLM."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            _write_json(input_file, _build_input(1))

            llm_item = _valid_pass_01_item("betrayal-001", 1, 1)
            llm_item["chapter_kind_preliminary"] = "analysis"
            llm_item["classification_confidence"] = "medium"

            with (
                patch.object(pass_01, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value=llm_item,
                ),
            ):
                self._run_pass_01(input_file=input_file, output_file=output_file)

            data = json.loads(output_file.read_text(encoding="utf-8"))
            out_item = data["chapters"][0]
            self.assertEqual(out_item["chapter_kind_preliminary"], "analysis")
            self.assertEqual(out_item["classification_confidence"], "medium")

    def test_preview_profile_limits_to_two_chapters(self) -> None:
        """Preview profile should cap processing at exactly two chapters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            output_file = (
                temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_PREVIEW_FILENAME
            )
            _write_json(input_file, _build_input(3))

            with (
                patch.object(pass_01, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    side_effect=[
                        _valid_pass_01_item("betrayal-001", 1, 1),
                        _valid_pass_01_item("betrayal-002", 2, 2),
                    ],
                ) as llm_mock,
            ):
                self._run_pass_01(
                    input_file=input_file,
                    output_file=output_file,
                    profile=PROFILE_PREVIEW,
                )

            self.assertEqual(llm_mock.call_count, 2)
            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data["chapters"]), 2)

    def test_loads_system_prompt_from_prompts_file(self) -> None:
        """System prompt should be read from configured prompt file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            prompt_file = temp_path / TEST_PROMPTS_DIRNAME / "pass_01.txt"
            _write_json(input_file, _build_input(1))
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Prompt from file.", encoding="utf-8")

            with (
                patch.object(pass_01, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(pass_01, "PASS_01_SYSTEM_PROMPT_FILE", prompt_file),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_01_item("betrayal-001", 1, 1),
                ) as llm_mock,
            ):
                self._run_pass_01(input_file=input_file, output_file=output_file)

            self.assertEqual(
                llm_mock.call_args.kwargs["system_prompt"], "Prompt from file."
            )

    def test_build_user_prompt_uses_jinja_template(self) -> None:
        """User prompt builder should render chapter JSON in template."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_file = Path(temp_dir) / "user_prompt.j2"
            template_file.write_text(
                "Payload: {{ chapter_payload_json }}", encoding="utf-8"
            )
            with patch.object(
                pass_01, "PASS_01_USER_PROMPT_TEMPLATE_FILE", template_file
            ):
                prompt = pass_01.build_user_prompt({"chapter_id": "betrayal-001"})

            self.assertIn('"chapter_id": "betrayal-001"', prompt)

    def test_uses_pass_01_item_schema_for_chapter_validation(self) -> None:
        """Pass 01 should validate each chapter against item schema file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            item_schema_file = (
                temp_path / TEST_SCHEMAS_DIRNAME / PASS_01_ITEM_SCHEMA_FILENAME
            )
            _write_json(input_file, _build_input(1))
            _write_json(
                item_schema_file,
                {
                    "type": "object",
                    "properties": {"must_exist": {"type": "string"}},
                    "required": ["must_exist"],
                    "additionalProperties": True,
                },
            )

            with (
                patch.object(pass_01, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(pass_01, "PASS_01_ITEM_SCHEMA_FILE", item_schema_file),
                patch.object(
                    pass_01,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_01_item("betrayal-001", 1, 1),
                ),
            ):
                with self.assertRaises(ValidationError):
                    self._run_pass_01(input_file=input_file, output_file=output_file)


if __name__ == "__main__":
    unittest.main()
