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

    def test_build_user_prompt_includes_json_output_contract(self) -> None:
        """Prompt builder should append strict JSON output instructions."""
        prompt = summarize_betrayal_json.build_user_prompt("Base", "Source text")
        self.assertIn("summary_paragraphs", prompt)
        self.assertIn("Chapter source", prompt)

    def test_main_writes_summarized_output_with_cover_metadata(self) -> None:
        """Main should preserve book metadata and write multi-paragraph chapter summaries."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize_example.txt"

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
                ),
            ):
                summarize_betrayal_json.main()

            written = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(written["book_metadata"]["title"], "Betrayal")
            self.assertEqual(len(written["examples"]), 1)
            paragraphs = written["examples"][0]["paragraphs"]
            self.assertEqual(len(paragraphs), 2)
            self.assertEqual(paragraphs[0]["paragraph_index"], 1)
            self.assertEqual(paragraphs[1]["paragraph_index"], 2)

    def test_main_chapter_limit_summarizes_only_first_n_chapters(self) -> None:
        """Chapter limit should cap summarization to the first N chapters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "data" / "betrayal.json"
            output_file = temp_path / "data" / "betrayal_short.json"
            prompt_file = temp_path / "prompts" / "summarize_example.txt"

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
            prompt_file = temp_path / "prompts" / "summarize_example.txt"

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
            prompt_file = temp_path / "prompts" / "summarize_example.txt"

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
            prompt_file = temp_path / "prompts" / "summarize_example.txt"

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
