"""Tests for pass_01_5 handoff preparation script behavior."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError
from project_paths import DATA_DIR, INGEST_DIR


if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import pass_01_5_prepare_for_pass_02 as pass_01_5
from pipeline_params import (
    PASS_01_OUTPUT_FULL,
    PASS_01_5_OUTPUT_FULL,
    PROFILE_DEFAULT,
)


TEST_DATA_DIRNAME = DATA_DIR.name
PASS_01_OUTPUT_FULL_FILENAME = PASS_01_OUTPUT_FULL.name
PASS_01_5_OUTPUT_FULL_FILENAME = PASS_01_5_OUTPUT_FULL.name


def _write_json(path: Path, data: dict) -> None:
    """Write a JSON fixture file with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _valid_pass_01_payload() -> dict:
    """Build a schema-valid pass-01 output payload."""
    return {
        "book_id": "betrayal",
        "chapters": [
            {
                "chapter_id": "betrayal-001",
                "chapter_order": 1,
                "chapter_number": 1,
                "chapter_title": "Title 1",
                "chapter_kind_preliminary": "narrative",
                "classification_confidence": "high",
                "classification_rationale": "Evidence points to narrative progression.",
                "dominant_entities": ["Harry"],
                "dominant_timeframe": "2022",
                "possible_themes": ["media"],
                "chapter_summary_preliminary": "A concise chapter summary.",
            }
        ],
    }


class Pass015Tests(unittest.TestCase):
    """Validate pass-1.5 copying and schema gate behavior."""

    def _run_pass_01_5(
        self,
        *,
        input_file: Path,
        output_file: Path,
        profile: str = PROFILE_DEFAULT,
    ) -> None:
        """Invoke pass_01_5.main with deterministic CLI arguments."""
        argv = [
            "pass_01_5_prepare_for_pass_02.py",
            "--profile",
            profile,
            "--input-file",
            str(input_file),
            "--output-file",
            str(output_file),
        ]
        with patch.object(sys, "argv", argv):
            pass_01_5.main()

    def test_copies_valid_pass_01_output(self) -> None:
        """Valid pass-01 data should be copied unchanged to pass-1.5 output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_5_OUTPUT_FULL_FILENAME
            payload = _valid_pass_01_payload()
            _write_json(input_file, payload)

            self._run_pass_01_5(input_file=input_file, output_file=output_file)

            self.assertTrue(output_file.exists())
            written = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(written, payload)

    def test_fails_on_invalid_input_schema(self) -> None:
        """Schema-invalid pass-01 input should fail fast."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / TEST_DATA_DIRNAME / PASS_01_OUTPUT_FULL_FILENAME
            output_file = temp_path / TEST_DATA_DIRNAME / PASS_01_5_OUTPUT_FULL_FILENAME
            _write_json(
                input_file, {"book_id": "betrayal", "chapters": [{"bad": "data"}]}
            )

            with self.assertRaises(ValidationError):
                self._run_pass_01_5(input_file=input_file, output_file=output_file)


if __name__ == "__main__":
    unittest.main()
