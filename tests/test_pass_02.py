"""Tests for pass_02 extraction and bundle generation behavior."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from project_paths import DATA_DIR, INGEST_DIR, PROMPTS_DIR, SCHEMAS_DIR


if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import pass_02_extract_and_bundle as pass_02
from pipeline_params import (
    BOOK_FILE,
    PASS_01_OUTPUT_FULL,
    PASS_01_OUTPUT_PREVIEW,
    PASS_02_ITEM_SCHEMA_FILE,
    PASS_02_OUTPUT_FULL,
    PASS_02_OUTPUT_PREVIEW,
    PROFILE_DEFAULT,
    PROFILE_PREVIEW,
)


BOOK_FILENAME = BOOK_FILE.name
PASS_01_OUTPUT_FULL_FILENAME = PASS_01_OUTPUT_FULL.name
PASS_01_OUTPUT_PREVIEW_FILENAME = PASS_01_OUTPUT_PREVIEW.name
PASS_02_OUTPUT_FULL_FILENAME = PASS_02_OUTPUT_FULL.name
PASS_02_OUTPUT_PREVIEW_FILENAME = PASS_02_OUTPUT_PREVIEW.name
PASS_02_ITEM_SCHEMA_FILENAME = PASS_02_ITEM_SCHEMA_FILE.name
TEST_DATA_DIRNAME = DATA_DIR.name
TEST_PROMPTS_DIRNAME = PROMPTS_DIR.name
TEST_SCHEMAS_DIRNAME = SCHEMAS_DIR.name


def _write_json(path: Path, data: dict) -> None:
    """Write JSON test fixtures using UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _book_data(chapters: int) -> dict:
    """Create synthetic book data payload for pass_02 tests."""
    examples = []
    for index in range(chapters):
        examples.append(
            {
                "source_file": f"{index + 8:03d}-Chapter_{index + 1}.xhtml",
                "chapter_type": "chapter",
                "chapter_number": index + 1,
                "chapter_label": f"CHAPTER {index + 1}",
                "chapter_title": f"Title {index + 1}",
                "paragraphs": [
                    {"paragraph_index": 1, "text": f"Chapter {index + 1} text."}
                ],
            }
        )
    return {"examples": examples}


def _preliminary_data(chapters: int) -> dict:
    """Create schema-valid pass_01 preliminary data for pass_02 input."""
    return {
        "book_id": "betrayal",
        "chapters": [
            {
                "chapter_id": f"betrayal-{index + 1:03d}",
                "chapter_order": index + 1,
                "chapter_number": index + 1,
                "chapter_title": f"Title {index + 1}",
                "chapter_kind_preliminary": "narrative",
                "classification_confidence": "high",
                "classification_rationale": "Event-focused narrative.",
                "dominant_entities": ["Harry", "Meghan"],
                "dominant_timeframe": "2022",
                "possible_themes": ["media"],
                "chapter_summary_preliminary": "A factual chapter summary in one paragraph.",
            }
            for index in range(chapters)
        ],
    }


def _valid_pass_02_item(
    chapter_id: str, chapter_order: int, chapter_number: int
) -> dict:
    """Return a schema-valid pass_02 chapter item."""
    entity_id = f"{chapter_id}-entity-001"
    event_id = f"{chapter_id}-event-001"
    relationship_id = f"{chapter_id}-rel-001"
    chunk_id = f"{chapter_id}-chunk-001"
    return {
        "chapter_id": chapter_id,
        "chapter_order": chapter_order,
        "source_file": f"{chapter_order + 7:03d}-Chapter_{chapter_order}.xhtml",
        "chapter_type": "chapter",
        "chapter_number": chapter_number,
        "chapter_title": f"Title {chapter_number}",
        "chapter_kind": "narrative",
        "schema_version": "2.2.0",
        "pipeline_version": "pass_02_v1_2",
        "extraction_model": "gpt-5-mini",
        "summary_short": "A short factual summary.",
        "summary_detailed": "A longer factual summary with key developments.",
        "summary_confidence": "high",
        "themes": ["media"],
        "key_events": [
            {
                "event_id": event_id,
                "sequence": 1,
                "event_summary": "A public event happens.",
                "importance": "high",
                "involved_entities": ["Harry"],
                "consequences": "It triggers press coverage.",
            }
        ],
        "entities": [
            {
                "entity_id": entity_id,
                "canonical_name": "Harry",
                "entity_type": "person",
                "role_in_chapter": "Main subject",
                "salience": "major",
                "aliases": [],
            }
        ],
        "time_markers": [
            {
                "label": "September 2022",
                "normalized": "2022-09",
                "certainty": "explicit",
                "related_event": "A public event happens.",
                "date_precision": "month",
                "date_earliest": "2022-09-01",
                "date_latest": "2022-09-30",
                "confidence": "high",
            }
        ],
        "important_quotes": [
            {
                "speaker_or_source": "Harry",
                "text": "Sample quote.",
                "why_it_matters": "It reflects the conflict.",
            }
        ],
        "open_loops": [],
        "chapter_keywords": ["royal"],
        "ambiguities_or_gaps": [],
        "chunks": [
            {
                "chunk_id": chunk_id,
                "chunk_order": 1,
                "source_paragraph_start": 1,
                "source_paragraph_end": 1,
                "chunk_text_source": "Chapter source text.",
                "chunk_text_us_plain": "Chapter plain US text.",
                "chunk_kind": "narrative",
                "entities_mentioned": ["Harry"],
                "aliases": [],
                "time_markers": ["September 2022"],
                "rewrite_quality": "pass",
                "fidelity_notes": "Meaning preserved.",
                "token_count": 8,
                "previous_chunk_id": None,
                "next_chunk_id": None,
                "keywords": ["royal", "media"],
                "bm25_boost_text": "Title royal media chapter coverage",
            }
        ],
        "relationships": [
            {
                "relationship_id": relationship_id,
                "source_entity_id": entity_id,
                "target_entity_id": entity_id,
                "relationship_type": "ASSOCIATED_WITH",
                "description": "The chapter repeatedly links Harry to the central public event.",
                "evidence_chunk_ids": [chunk_id],
                "confidence": "high",
                "valid_from": "2022-09",
                "valid_to": "2022-09",
            }
        ],
    }


class Pass02Tests(unittest.TestCase):
    """End-to-end unit tests for pass_02 script flow."""

    def _run_pass_02(
        self,
        *,
        book_file: Path,
        classification_file: Path,
        output_file: Path,
        profile: str = PROFILE_DEFAULT,
    ) -> None:
        """Invoke pass_02.main with deterministic CLI args."""
        argv = [
            "pass_02_extract_and_bundle.py",
            "--profile",
            profile,
            "--book-file",
            str(book_file),
            "--classification-file",
            str(classification_file),
            "--output-file",
            str(output_file),
        ]
        with patch.object(sys, "argv", argv):
            pass_02.main()

    def test_writes_bundle_for_one_chapter(self) -> None:
        """One chapter input should produce one bundled chapter output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            class_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_02_OUTPUT_FULL_FILENAME
            _write_json(book_file, _book_data(1))
            _write_json(class_file, _preliminary_data(1))

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_02,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_02_item("betrayal-001", 1, 1),
                ) as llm_mock,
            ):
                self._run_pass_02(
                    book_file=book_file,
                    classification_file=class_file,
                    output_file=output_file,
                )

            self.assertTrue(output_file.exists())
            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(data["book_id"], "betrayal")
            self.assertEqual(len(data["chapters"]), 1)
            self.assertEqual(
                data["chapters"][0]["chapter_kind_preliminary"], "narrative"
            )
            self.assertFalse(data["chapters"][0]["chapter_kind_changed"])
            self.assertEqual(data["chapters"][0]["schema_version"], "2.2.0")
            self.assertEqual(data["chapters"][0]["pipeline_version"], "pass_02_v1_2")
            self.assertEqual(data["chapters"][0]["extraction_model"], "gpt-5-mini")
            self.assertEqual(llm_mock.call_count, 1)

    def test_fails_if_preliminary_record_is_missing(self) -> None:
        """Missing pass_01 chapter should fail fast with ValueError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            class_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_02_OUTPUT_FULL_FILENAME
            _write_json(book_file, _book_data(1))
            _write_json(class_file, {"book_id": "betrayal", "chapters": []})

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
            ):
                with self.assertRaises(ValueError):
                    self._run_pass_02(
                        book_file=book_file,
                        classification_file=class_file,
                        output_file=output_file,
                    )

    def test_passes_preliminary_context_to_llm_payload(self) -> None:
        """LLM payload should include matching preliminary chapter context."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            class_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_02_OUTPUT_FULL_FILENAME
            _write_json(book_file, _book_data(1))
            preliminary = _preliminary_data(1)
            _write_json(class_file, preliminary)

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_02,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_02_item("betrayal-001", 1, 1),
                ) as llm_mock,
            ):
                self._run_pass_02(
                    book_file=book_file,
                    classification_file=class_file,
                    output_file=output_file,
                )

            call_kwargs = llm_mock.call_args.kwargs
            self.assertIn("preliminary", call_kwargs["input_payload"])
            self.assertIn("extraction_context", call_kwargs["input_payload"])
            self.assertEqual(
                call_kwargs["input_payload"]["preliminary"]["chapter_id"],
                preliminary["chapters"][0]["chapter_id"],
            )
            self.assertEqual(
                call_kwargs["input_payload"]["extraction_context"]["schema_version"],
                "2.2.0",
            )

    def test_calls_llm_once_per_chapter(self) -> None:
        """LLM call count should equal processed chapter count."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            class_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_02_OUTPUT_FULL_FILENAME
            _write_json(book_file, _book_data(2))
            _write_json(class_file, _preliminary_data(2))

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_02,
                    "call_openai_structured_cached",
                    side_effect=[
                        _valid_pass_02_item("betrayal-001", 1, 1),
                        _valid_pass_02_item("betrayal-002", 2, 2),
                    ],
                ) as llm_mock,
            ):
                self._run_pass_02(
                    book_file=book_file,
                    classification_file=class_file,
                    output_file=output_file,
                )

            self.assertEqual(llm_mock.call_count, 2)

    def test_fails_when_llm_payload_is_schema_invalid(self) -> None:
        """Schema-invalid LLM output should fail pass_02 execution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            class_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_02_OUTPUT_FULL_FILENAME
            _write_json(book_file, _book_data(1))
            _write_json(class_file, _preliminary_data(1))

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_02,
                    "call_openai_structured_cached",
                    return_value={"bad": "payload"},
                ),
            ):
                with self.assertRaises(Exception):
                    self._run_pass_02(
                        book_file=book_file,
                        classification_file=class_file,
                        output_file=output_file,
                    )

    def test_marks_chapter_kind_changed_when_final_differs(self) -> None:
        """Different final chapter kind should mark `chapter_kind_changed`."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            class_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_02_OUTPUT_FULL_FILENAME
            _write_json(book_file, _book_data(1))
            _write_json(class_file, _preliminary_data(1))

            llm_item = _valid_pass_02_item("betrayal-001", 1, 1)
            llm_item["chapter_kind"] = "analysis"

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_02,
                    "call_openai_structured_cached",
                    return_value=llm_item,
                ),
            ):
                self._run_pass_02(
                    book_file=book_file,
                    classification_file=class_file,
                    output_file=output_file,
                )

            data = json.loads(output_file.read_text(encoding="utf-8"))
            out_item = data["chapters"][0]
            self.assertEqual(out_item["chapter_kind_preliminary"], "narrative")
            self.assertEqual(out_item["chapter_kind"], "analysis")
            self.assertTrue(out_item["chapter_kind_changed"])
            self.assertTrue(out_item["chapter_kind_change_rationale"])

    def test_preview_profile_limits_to_two_chapters(self) -> None:
        """Preview profile should process exactly two chapters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            class_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_PREVIEW_FILENAME
            output_file = (
                temp_path / TEST_DATA_DIRNAME / PASS_02_OUTPUT_PREVIEW_FILENAME
            )
            _write_json(book_file, _book_data(3))
            _write_json(class_file, _preliminary_data(3))

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(
                    pass_02,
                    "call_openai_structured_cached",
                    side_effect=[
                        _valid_pass_02_item("betrayal-001", 1, 1),
                        _valid_pass_02_item("betrayal-002", 2, 2),
                    ],
                ) as llm_mock,
            ):
                self._run_pass_02(
                    book_file=book_file,
                    classification_file=class_file,
                    output_file=output_file,
                    profile=PROFILE_PREVIEW,
                )

            self.assertEqual(llm_mock.call_count, 2)
            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data["chapters"]), 2)

    def test_loads_system_prompt_from_prompts_file(self) -> None:
        """System prompt should be loaded from configured prompt file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            class_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_02_OUTPUT_FULL_FILENAME
            prompt_file = temp_path / TEST_PROMPTS_DIRNAME / "pass_02.txt"
            _write_json(book_file, _book_data(1))
            _write_json(class_file, _preliminary_data(1))
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Extraction prompt from file.", encoding="utf-8")

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(pass_02, "PASS_02_SYSTEM_PROMPT_FILE", prompt_file),
                patch.object(
                    pass_02,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_02_item("betrayal-001", 1, 1),
                ) as llm_mock,
            ):
                self._run_pass_02(
                    book_file=book_file,
                    classification_file=class_file,
                    output_file=output_file,
                )

            self.assertEqual(
                llm_mock.call_args.kwargs["system_prompt"],
                "Extraction prompt from file.",
            )

    def test_build_user_prompt_uses_jinja_template(self) -> None:
        """User prompt builder should render chapter JSON in template."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_file = Path(temp_dir) / "user_prompt.j2"
            template_file.write_text(
                "Payload: {{ chapter_payload_json }}", encoding="utf-8"
            )
            with patch.object(
                pass_02, "PASS_02_USER_PROMPT_TEMPLATE_FILE", template_file
            ):
                prompt = pass_02.build_user_prompt({"chapter_id": "betrayal-001"})

            self.assertIn('"chapter_id": "betrayal-001"', prompt)

    def test_uses_pass_02_item_schema_for_chapter_validation(self) -> None:
        """Pass 02 should validate each chapter against item schema file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / TEST_DATA_DIRNAME / BOOK_FILENAME
            class_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_02_OUTPUT_FULL_FILENAME
            item_schema_file = (
                temp_path / TEST_SCHEMAS_DIRNAME / PASS_02_ITEM_SCHEMA_FILENAME
            )
            _write_json(book_file, _book_data(1))
            _write_json(class_file, _preliminary_data(1))
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
                patch.object(pass_02, "DATA_DIR", temp_path / TEST_DATA_DIRNAME),
                patch.object(pass_02, "PASS_02_ITEM_SCHEMA_FILE", item_schema_file),
                patch.object(
                    pass_02,
                    "call_openai_structured_cached",
                    return_value=_valid_pass_02_item("betrayal-001", 1, 1),
                ),
            ):
                with self.assertRaises(Exception):
                    self._run_pass_02(
                        book_file=book_file,
                        classification_file=class_file,
                        output_file=output_file,
                    )


if __name__ == "__main__":
    unittest.main()
