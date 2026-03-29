"""Tests for summarize_betrayal_json program behavior."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import summarize_betrayal_json


def _write_json(path: Path, data: dict) -> None:
    """Write JSON fixture data using UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


class SummarizeBetrayalJsonTests(unittest.TestCase):
    """Validate summary output shape and metadata propagation."""

    def test_resolve_model_name_uses_environment_when_not_draft(self) -> None:
        """Model resolver should honor SUMMARY_MODEL when draft mode is disabled."""
        with patch.dict(os.environ, {"SUMMARY_MODEL": "gpt-5-custom"}, clear=False):
            model_name = summarize_betrayal_json.resolve_model_name(draft_mode=False)

        self.assertEqual(model_name, "gpt-5-custom")

    def test_resolve_model_name_forces_draft_model_even_with_env_override(self) -> None:
        """Draft mode should force the configured low-cost draft model."""
        with patch.dict(os.environ, {"SUMMARY_MODEL": "gpt-5-expensive"}, clear=False):
            model_name = summarize_betrayal_json.resolve_model_name(draft_mode=True)

        self.assertEqual(model_name, summarize_betrayal_json.SUMMARY_MODEL_DRAFT)

    def test_format_duration_hms_always_includes_hours_minutes_seconds(self) -> None:
        """Duration formatter should produce a stable H/M/S output shape."""
        self.assertEqual(summarize_betrayal_json.format_duration_hms(5), "0h 00m 05s")
        self.assertEqual(
            summarize_betrayal_json.format_duration_hms(3_661), "1h 01m 01s"
        )

    def test_build_user_prompt_includes_json_output_contract(self) -> None:
        """Prompt builder should append strict JSON output instructions."""
        prompt = summarize_betrayal_json.build_user_prompt("Base", "Source text")
        self.assertIn("summary_paragraphs", prompt)
        self.assertIn("Chapter source", prompt)

    def test_prepare_chapters_rejects_non_object_chapter(self) -> None:
        """Chapter validation should fail when an item is not an object."""
        with self.assertRaises(ValueError):
            summarize_betrayal_json.prepare_chapters_for_summarization(["bad chapter"])  # type: ignore[list-item]

    def test_build_chapter_source_text_rejects_non_string_paragraph_text(self) -> None:
        """Chapter source builder should fail fast on non-string paragraph text."""
        with self.assertRaises(ValueError):
            summarize_betrayal_json.build_chapter_source_text(
                {
                    "chapter_title": "T",
                    "paragraphs": [{"paragraph_index": 1, "text": 123}],
                }
            )

    def test_main_writes_summarized_output_with_cover_metadata(self) -> None:
        """Main should preserve book metadata and write multi-paragraph chapter summaries."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [
                        {
                            "source_file": "009-Chapter_1.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 1,
                            "chapter_label": "CHAPTER 1",
                            "chapter_title": "Manchester",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph one."},
                                {"paragraph_index": 2, "text": "Paragraph two."},
                            ],
                        }
                    ],
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json,
                    "call_openai_structured_cached",
                    return_value={
                        "summary_paragraphs": [
                            "Summary paragraph one.",
                            "Summary paragraph two.",
                        ]
                    },
                ) as llm_mock,
            ):
                summarize_betrayal_json.main()

            written = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(written["book_metadata"]["title"], "Betrayal")
            self.assertEqual(len(written["examples"]), 1)
            paragraphs = written["examples"][0]["paragraphs"]
            self.assertEqual(len(paragraphs), 2)
            self.assertEqual(paragraphs[0]["paragraph_index"], 1)
            self.assertEqual(paragraphs[1]["paragraph_index"], 2)
            self.assertEqual(
                llm_mock.call_args.kwargs["max_attempts"],
                summarize_betrayal_json.MAX_ATTEMPTS_DEFAULT,
            )

    def test_main_chapter_limit_summarizes_only_first_n_chapters(self) -> None:
        """Chapter limit should cap summarization to the first N chapters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [
                        {
                            "source_file": "009-Chapter_1.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 1,
                            "chapter_label": "CHAPTER 1",
                            "chapter_title": "Manchester",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph one."}
                            ],
                        },
                        {
                            "source_file": "010-Chapter_2.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 2,
                            "chapter_label": "CHAPTER 2",
                            "chapter_title": "Global Celebrity",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph alpha."}
                            ],
                        },
                    ],
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(
                    sys,
                    "argv",
                    ["summarize_betrayal_json.py", "--chapter-limit", "1"],
                ),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json,
                    "call_openai_structured_cached",
                    return_value={
                        "summary_paragraphs": [
                            "Summary paragraph one.",
                            "Summary paragraph two.",
                        ]
                    },
                ) as summary_mock,
            ):
                summarize_betrayal_json.main()

            written = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(len(written["examples"]), 1)
            self.assertEqual(
                written["examples"][0]["source_file"], "009-Chapter_1.xhtml"
            )
            self.assertEqual(summary_mock.call_count, 1)

    def test_main_logs_eta_progress_after_each_processed_chapter(self) -> None:
        """Main should log chapter ETA metrics in H/M/S after each chapter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [
                        {
                            "source_file": "009-Chapter_1.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 1,
                            "chapter_label": "CHAPTER 1",
                            "chapter_title": "Manchester",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph one."}
                            ],
                        },
                        {
                            "source_file": "010-Chapter_2.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 2,
                            "chapter_label": "CHAPTER 2",
                            "chapter_title": "Global Celebrity",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph alpha."}
                            ],
                        },
                    ],
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json,
                    "call_openai_structured_cached",
                    return_value={
                        "summary_paragraphs": [
                            "Summary paragraph one.",
                            "Summary paragraph two.",
                        ]
                    },
                ),
                patch.object(
                    summarize_betrayal_json.time,
                    "perf_counter",
                    side_effect=[10.0, 70.0, 70.0, 130.0],
                ),
                patch.object(summarize_betrayal_json, "logger") as logger_mock,
            ):
                summarize_betrayal_json.main()

            done_calls = [
                call
                for call in logger_mock.info.call_args_list
                if call.args
                and call.args[0]
                == "[%d/%d] Done source_file=%s chapter_duration=%s elapsed=%s eta_remaining=%s eta_total=%s"
            ]
            self.assertEqual(len(done_calls), 2)

            first_done_args = done_calls[0].args
            self.assertEqual(first_done_args[1], 1)
            self.assertEqual(first_done_args[2], 2)
            self.assertEqual(first_done_args[3], "009-Chapter_1.xhtml")
            self.assertEqual(first_done_args[4], "0h 01m 00s")
            self.assertEqual(first_done_args[5], "0h 01m 00s")
            self.assertEqual(first_done_args[6], "0h 01m 00s")
            self.assertEqual(first_done_args[7], "0h 02m 00s")

            second_done_args = done_calls[1].args
            self.assertEqual(second_done_args[1], 2)
            self.assertEqual(second_done_args[2], 2)
            self.assertEqual(second_done_args[3], "010-Chapter_2.xhtml")
            self.assertEqual(second_done_args[4], "0h 01m 00s")
            self.assertEqual(second_done_args[5], "0h 02m 00s")
            self.assertEqual(second_done_args[6], "0h 00m 00s")
            self.assertEqual(second_done_args[7], "0h 02m 00s")

    def test_main_with_no_chapters_writes_empty_output_without_llm_calls(self) -> None:
        """Main should write empty examples and skip LLM calls when input has no chapters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [],
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json, "call_openai_structured_cached"
                ) as llm_mock,
                patch.object(summarize_betrayal_json, "logger") as logger_mock,
            ):
                summarize_betrayal_json.main()

            written = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(written["examples"], [])
            llm_mock.assert_not_called()

            done_calls = [
                call
                for call in logger_mock.info.call_args_list
                if call.args
                and call.args[0]
                == "[%d/%d] Done source_file=%s chapter_duration=%s elapsed=%s eta_remaining=%s eta_total=%s"
            ]
            self.assertEqual(done_calls, [])

    def test_main_fails_when_examples_is_not_a_list_before_llm_call(self) -> None:
        """Input JSON should fail fast when `examples` is not a list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": {},
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json, "call_openai_structured_cached"
                ) as llm_mock,
                self.assertRaises(ValueError),
            ):
                summarize_betrayal_json.main()

            llm_mock.assert_not_called()

    def test_main_stops_on_second_chapter_llm_failure(self) -> None:
        """Main should stop processing immediately when an LLM call fails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [
                        {
                            "source_file": "009-Chapter_1.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 1,
                            "chapter_label": "CHAPTER 1",
                            "chapter_title": "Manchester",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph one."}
                            ],
                        },
                        {
                            "source_file": "010-Chapter_2.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 2,
                            "chapter_label": "CHAPTER 2",
                            "chapter_title": "Global Celebrity",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph alpha."}
                            ],
                        },
                    ],
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json,
                    "call_openai_structured_cached",
                    side_effect=[
                        {
                            "summary_paragraphs": [
                                "Summary paragraph one.",
                                "Summary paragraph two.",
                            ]
                        },
                        RuntimeError("llm exploded"),
                    ],
                ) as llm_mock,
                self.assertRaises(RuntimeError),
            ):
                summarize_betrayal_json.main()

            self.assertEqual(llm_mock.call_count, 2)
            self.assertFalse(output_file.exists())

    def test_main_chapter_limit_rejects_non_positive_value(self) -> None:
        """Non-positive chapter limit should fail fast with ValueError."""
        with (
            patch.object(
                sys, "argv", ["summarize_betrayal_json.py", "--chapter-limit", "0"]
            ),
            self.assertRaises(ValueError),
        ):
            summarize_betrayal_json.main()

    def test_main_validates_all_chapters_before_first_llm_call(self) -> None:
        """Invalid later chapter should fail before any LLM request is made."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [
                        {
                            "source_file": "009-Chapter_1.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 1,
                            "chapter_label": "CHAPTER 1",
                            "chapter_title": "Manchester",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph one."}
                            ],
                        },
                        {
                            "source_file": "010-Chapter_2.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 2,
                            "chapter_label": "CHAPTER 2",
                            "chapter_title": "Global Celebrity",
                            "paragraphs": [{"paragraph_index": 1, "text": "   "}],
                        },
                    ],
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json, "call_openai_structured_cached"
                ) as llm_mock,
                self.assertRaises(ValueError),
            ):
                summarize_betrayal_json.main()

            llm_mock.assert_not_called()

    def test_main_fails_on_missing_cover_image_src_before_llm_call(self) -> None:
        """Missing required metadata should fail before any LLM call."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [],
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json, "call_openai_structured_cached"
                ) as llm_mock,
                self.assertRaises(ValueError),
            ):
                summarize_betrayal_json.main()

            llm_mock.assert_not_called()

    def test_main_fails_on_empty_book_title_before_llm_call(self) -> None:
        """Empty metadata title should fail before any LLM call."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "   ",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [],
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json, "call_openai_structured_cached"
                ) as llm_mock,
                self.assertRaises(ValueError),
            ):
                summarize_betrayal_json.main()

            llm_mock.assert_not_called()

    def test_main_fails_on_missing_prompt_file_before_llm_call(self) -> None:
        """Missing prompt file should fail before any LLM request."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            missing_prompt_file = temp_path / "prompts" / "missing_prompt.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [
                        {
                            "source_file": "009-Chapter_1.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 1,
                            "chapter_label": "CHAPTER 1",
                            "chapter_title": "Manchester",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph one."}
                            ],
                        }
                    ],
                },
            )

            with (
                patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(
                    summarize_betrayal_json, "PROMPT_FILE", missing_prompt_file
                ),
                patch.object(
                    summarize_betrayal_json, "call_openai_structured_cached"
                ) as llm_mock,
                self.assertRaises(FileNotFoundError),
            ):
                summarize_betrayal_json.main()

            llm_mock.assert_not_called()

    def test_main_fails_on_empty_model_env_before_llm_call(self) -> None:
        """Empty summary model environment value should fail fast."""
        with (
            patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
            patch.dict(os.environ, {"SUMMARY_MODEL": ""}, clear=False),
            patch.object(
                summarize_betrayal_json, "call_openai_structured_cached"
            ) as llm_mock,
            self.assertRaises(ValueError),
        ):
            summarize_betrayal_json.main()

        llm_mock.assert_not_called()

    def test_main_draft_forces_gpt_5_mini_model(self) -> None:
        """Draft CLI flag should force low-cost model for LLM calls."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize.txt"

            _write_json(
                input_file,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [
                        {
                            "source_file": "009-Chapter_1.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 1,
                            "chapter_label": "CHAPTER 1",
                            "chapter_title": "Manchester",
                            "paragraphs": [
                                {"paragraph_index": 1, "text": "Paragraph one."},
                                {"paragraph_index": 2, "text": "Paragraph two."},
                            ],
                        }
                    ],
                },
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("Base summarize prompt", encoding="utf-8")

            with (
                patch.object(
                    sys,
                    "argv",
                    ["summarize_betrayal_json.py", "--draft"],
                ),
                patch.dict(os.environ, {"SUMMARY_MODEL": "gpt-5.4"}, clear=False),
                patch.object(summarize_betrayal_json, "INPUT_FILE", input_file),
                patch.object(summarize_betrayal_json, "OUTPUT_FILE", output_file),
                patch.object(summarize_betrayal_json, "PROMPT_FILE", prompt_file),
                patch.object(
                    summarize_betrayal_json,
                    "call_openai_structured_cached",
                    return_value={
                        "summary_paragraphs": [
                            "Summary paragraph one.",
                            "Summary paragraph two.",
                        ]
                    },
                ) as llm_mock,
            ):
                summarize_betrayal_json.main()

            self.assertEqual(
                llm_mock.call_args.kwargs["model"],
                summarize_betrayal_json.SUMMARY_MODEL_DRAFT,
            )

    def test_main_fails_on_invalid_timeout_env_before_llm_call(self) -> None:
        """Non-integer timeout environment value should fail fast."""
        with (
            patch.object(sys, "argv", ["summarize_betrayal_json.py"]),
            patch.dict(os.environ, {"SUMMARY_TIMEOUT_SECONDS": "abc"}, clear=False),
            patch.object(
                summarize_betrayal_json, "call_openai_structured_cached"
            ) as llm_mock,
            self.assertRaises(ValueError),
        ):
            summarize_betrayal_json.main()

        llm_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
