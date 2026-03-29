"""Tests for shared ingest helpers in pipeline_common."""

import sys
import tempfile
import unittest
from pathlib import Path

from jinja2 import UndefinedError
from jsonschema import ValidationError
from project_paths import INGEST_DIR


if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import pipeline_common


class PipelineCommonTests(unittest.TestCase):
    """Validate IO, template, schema, and id helper behavior."""

    def test_read_text_file_trims_trailing_whitespace(self) -> None:
        """read_text_file should strip outer whitespace."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "prompt.txt"
            path.write_text("Prompt text.\n\n", encoding="utf-8")
            self.assertEqual(pipeline_common.read_text_file(path), "Prompt text.")

    def test_render_prompt_template_inserts_context(self) -> None:
        """Template rendering should interpolate context values."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = Path(temp_dir) / "prompt.j2"
            template_path.write_text("Hello {{ name }}", encoding="utf-8")
            rendered = pipeline_common.render_prompt_template(
                template_path, {"name": "world"}
            )
            self.assertEqual(rendered, "Hello world")

    def test_render_prompt_template_fails_on_missing_variable(self) -> None:
        """StrictUndefined should fail when context is incomplete."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = Path(temp_dir) / "prompt.j2"
            template_path.write_text("Hello {{ name }}", encoding="utf-8")
            with self.assertRaises(UndefinedError):
                pipeline_common.render_prompt_template(template_path, {})

    def test_write_and_read_json_round_trip(self) -> None:
        """write_json and read_json should round-trip JSON payloads."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data.json"
            payload = {"a": 1, "b": ["x"]}
            pipeline_common.write_json(path, payload)
            self.assertEqual(pipeline_common.read_json(path), payload)

    def test_validate_with_schema_accepts_valid_payload(self) -> None:
        """validate_with_schema should accept valid payloads."""
        schema = {
            "type": "object",
            "properties": {"a": {"type": "integer"}},
            "required": ["a"],
            "additionalProperties": False,
        }
        pipeline_common.validate_with_schema({"a": 1}, schema)

    def test_validate_with_schema_rejects_invalid_payload(self) -> None:
        """validate_with_schema should raise on schema violations."""
        schema = {
            "type": "object",
            "properties": {"a": {"type": "integer"}},
            "required": ["a"],
            "additionalProperties": False,
        }
        with self.assertRaises(ValidationError):
            pipeline_common.validate_with_schema({"a": "bad"}, schema)

    def test_chapter_id_from_order_is_stable(self) -> None:
        """chapter_id_from_order should format IDs deterministically."""
        self.assertEqual(pipeline_common.chapter_id_from_order(7), "betrayal-007")

    def test_chunk_id_from_order_is_stable(self) -> None:
        """chunk_id_from_order should format chunk IDs deterministically."""
        self.assertEqual(
            pipeline_common.chunk_id_from_order("betrayal-007", 3),
            "betrayal-007-chunk-003",
        )


if __name__ == "__main__":
    unittest.main()
