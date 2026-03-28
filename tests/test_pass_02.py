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

import pass_02_extract_and_bundle as pass_02


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _book_data(chapters: int) -> dict:
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
    return {
        "chapter_id": chapter_id,
        "chapter_order": chapter_order,
        "source_file": f"{chapter_order + 7:03d}-Chapter_{chapter_order}.xhtml",
        "chapter_type": "chapter",
        "chapter_number": chapter_number,
        "chapter_title": f"Title {chapter_number}",
        "chapter_kind": "narrative",
        "summary_short": "A short factual summary.",
        "summary_detailed": "A longer factual summary with key developments.",
        "summary_confidence": "high",
        "themes": ["media"],
        "key_events": [
            {
                "sequence": 1,
                "event_summary": "A public event happens.",
                "importance": "high",
                "involved_entities": ["Harry"],
                "consequences": "It triggers press coverage.",
            }
        ],
        "entities": [
            {
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
                "chunk_id": f"{chapter_id}-chunk-001",
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
            }
        ],
    }


class Pass02Tests(unittest.TestCase):
    def _run_pass_02(
        self,
        *,
        book_file: Path,
        classification_file: Path,
        output_file: Path,
        profile: str = "full",
    ) -> None:
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
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / "data" / "betrayal.json"
            class_file = temp_path / "data" / "pass_01_chapter_classification.json"
            output_file = temp_path / "data" / "rag_ingest_bundle.json"
            _write_json(book_file, _book_data(1))
            _write_json(class_file, _preliminary_data(1))

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / "data"),
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
            self.assertEqual(llm_mock.call_count, 1)

    def test_fails_if_preliminary_record_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / "data" / "betrayal.json"
            class_file = temp_path / "data" / "pass_01_chapter_classification.json"
            output_file = temp_path / "data" / "rag_ingest_bundle.json"
            _write_json(book_file, _book_data(1))
            _write_json(class_file, {"book_id": "betrayal", "chapters": []})

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / "data"),
            ):
                with self.assertRaises(ValueError):
                    self._run_pass_02(
                        book_file=book_file,
                        classification_file=class_file,
                        output_file=output_file,
                    )

    def test_passes_preliminary_context_to_llm_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / "data" / "betrayal.json"
            class_file = temp_path / "data" / "pass_01_chapter_classification.json"
            output_file = temp_path / "data" / "rag_ingest_bundle.json"
            _write_json(book_file, _book_data(1))
            preliminary = _preliminary_data(1)
            _write_json(class_file, preliminary)

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / "data"),
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
            self.assertEqual(
                call_kwargs["input_payload"]["preliminary"]["chapter_id"],
                preliminary["chapters"][0]["chapter_id"],
            )

    def test_calls_llm_once_per_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / "data" / "betrayal.json"
            class_file = temp_path / "data" / "pass_01_chapter_classification.json"
            output_file = temp_path / "data" / "rag_ingest_bundle.json"
            _write_json(book_file, _book_data(2))
            _write_json(class_file, _preliminary_data(2))

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / "data"),
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
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / "data" / "betrayal.json"
            class_file = temp_path / "data" / "pass_01_chapter_classification.json"
            output_file = temp_path / "data" / "rag_ingest_bundle.json"
            _write_json(book_file, _book_data(1))
            _write_json(class_file, _preliminary_data(1))

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / "data"),
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
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / "data" / "betrayal.json"
            class_file = temp_path / "data" / "pass_01_chapter_classification.json"
            output_file = temp_path / "data" / "rag_ingest_bundle.json"
            _write_json(book_file, _book_data(1))
            _write_json(class_file, _preliminary_data(1))

            llm_item = _valid_pass_02_item("betrayal-001", 1, 1)
            llm_item["chapter_kind"] = "analysis"

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / "data"),
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
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_file = temp_path / "data" / "betrayal.json"
            class_file = (
                temp_path / "data" / "pass_01_chapter_classification_preview.json"
            )
            output_file = temp_path / "data" / "rag_ingest_bundle_preview.json"
            _write_json(book_file, _book_data(3))
            _write_json(class_file, _preliminary_data(3))

            with (
                patch.object(pass_02, "DATA_DIR", temp_path / "data"),
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
                    profile="preview",
                )

            self.assertEqual(llm_mock.call_count, 2)
            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data["chapters"]), 2)


if __name__ == "__main__":
    unittest.main()
