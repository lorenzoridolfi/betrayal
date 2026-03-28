"""Tests for shared pipeline utilities in ingest/pipeline_common.py."""

import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from jinja2 import UndefinedError
from project_paths import INGEST_DIR


if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import pipeline_common
from pipeline_params import MODEL_DEFAULT, TIMEOUT_SECONDS_DEFAULT


SIMPLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"a": {"type": "integer"}},
    "required": ["a"],
}


class PipelineCommonTests(unittest.TestCase):
    """Validate cache, template rendering, and OpenAI contract helpers."""

    def test_read_text_file_trims_trailing_whitespace(self) -> None:
        """`read_text_file` should strip trailing blank lines."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "prompt.txt"
            path.write_text("Prompt text.\n\n", encoding="utf-8")
            self.assertEqual(pipeline_common.read_text_file(path), "Prompt text.")

    def test_render_prompt_template_inserts_context(self) -> None:
        """Template rendering should interpolate provided context values."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = Path(temp_dir) / "prompt.j2"
            template_path.write_text("Hello {{ name }}", encoding="utf-8")
            rendered = pipeline_common.render_prompt_template(
                template_path, {"name": "world"}
            )
            self.assertEqual(rendered, "Hello world")

    def test_render_prompt_template_fails_on_missing_variable(self) -> None:
        """StrictUndefined should fail fast on missing template variables."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = Path(temp_dir) / "prompt.j2"
            template_path.write_text("Hello {{ name }}", encoding="utf-8")
            with self.assertRaises(UndefinedError):
                pipeline_common.render_prompt_template(template_path, {})

    def test_cache_hit_skips_llm_call(self) -> None:
        """Cache hit should return value without calling OpenAI."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(pipeline_common, "CACHE_DIR", Path(temp_dir) / "cache"):
                cached_value = {"a": 7}
                key = pipeline_common.build_cache_key(
                    model=MODEL_DEFAULT,
                    prompt="sys\n\nuser",
                    schema_name="s",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 1},
                )
                pipeline_common.save_cached_response(key, cached_value)

                with patch.object(
                    pipeline_common, "_call_openai_once", side_effect=AssertionError
                ):
                    result = pipeline_common.call_openai_structured_cached(
                        model=MODEL_DEFAULT,
                        system_prompt="sys",
                        user_prompt="user",
                        schema_name="s",
                        schema=SIMPLE_SCHEMA,
                        input_payload={"x": 1},
                        timeout_seconds=TIMEOUT_SECONDS_DEFAULT,
                    )

                self.assertEqual(result, cached_value)

    def test_cache_miss_calls_llm_and_saves_cache(self) -> None:
        """Cache miss should call OpenAI once and persist response."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            with (
                patch.object(pipeline_common, "CACHE_DIR", cache_dir),
                patch.object(
                    pipeline_common, "_call_openai_once", return_value={"a": 1}
                ) as llm_mock,
            ):
                result = pipeline_common.call_openai_structured_cached(
                    model=MODEL_DEFAULT,
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="s",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 2},
                    timeout_seconds=TIMEOUT_SECONDS_DEFAULT,
                )

                self.assertEqual(result, {"a": 1})
                self.assertEqual(llm_mock.call_count, 1)
                self.assertEqual(len(list(cache_dir.glob("*.json"))), 1)

    def test_retries_on_timeout_and_succeeds(self) -> None:
        """Timeout errors should be retried until success."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(pipeline_common, "CACHE_DIR", Path(temp_dir) / "cache"),
                patch.object(
                    pipeline_common,
                    "_call_openai_once",
                    side_effect=[TimeoutError("timeout"), {"a": 3}],
                ) as llm_mock,
            ):
                result = pipeline_common.call_openai_structured_cached(
                    model=MODEL_DEFAULT,
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="s",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 3},
                    timeout_seconds=TIMEOUT_SECONDS_DEFAULT,
                )

                self.assertEqual(result, {"a": 3})
                self.assertEqual(llm_mock.call_count, 2)

    def test_retries_on_schema_error_and_succeeds(self) -> None:
        """Schema validation errors should trigger retry and recover."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(pipeline_common, "CACHE_DIR", Path(temp_dir) / "cache"),
                patch.object(
                    pipeline_common,
                    "_call_openai_once",
                    side_effect=[
                        pipeline_common.SchemaValidationError("bad"),
                        {"a": 5},
                    ],
                ) as llm_mock,
            ):
                result = pipeline_common.call_openai_structured_cached(
                    model=MODEL_DEFAULT,
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="s",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 5},
                    timeout_seconds=TIMEOUT_SECONDS_DEFAULT,
                )

                self.assertEqual(result, {"a": 5})
                self.assertEqual(llm_mock.call_count, 2)

    def test_raises_after_max_attempts(self) -> None:
        """Retry loop should re-raise after max attempts is reached."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(pipeline_common, "CACHE_DIR", Path(temp_dir) / "cache"),
                patch.object(
                    pipeline_common,
                    "_call_openai_once",
                    side_effect=TimeoutError("still timing out"),
                ),
            ):
                with self.assertRaises(TimeoutError):
                    pipeline_common.call_openai_structured_cached(
                        model=MODEL_DEFAULT,
                        system_prompt="sys",
                        user_prompt="user",
                        schema_name="s",
                        schema=SIMPLE_SCHEMA,
                        input_payload={"x": 6},
                        timeout_seconds=TIMEOUT_SECONDS_DEFAULT,
                        max_attempts=2,
                    )

    def test_cache_key_is_deterministic(self) -> None:
        """Equivalent inputs should produce identical cache keys."""
        key_1 = pipeline_common.build_cache_key(
            model=MODEL_DEFAULT,
            prompt="sys\n\nuser",
            schema_name="schema_a",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        key_2 = pipeline_common.build_cache_key(
            model=MODEL_DEFAULT,
            prompt="sys\n\nuser",
            schema_name="schema_a",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        self.assertEqual(key_1, key_2)

    def test_cache_key_changes_with_prompt_or_schema(self) -> None:
        """Prompt/schema changes should alter the cache key."""
        base_key = pipeline_common.build_cache_key(
            model=MODEL_DEFAULT,
            prompt="sys\n\nuser",
            schema_name="schema_a",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        changed_prompt_key = pipeline_common.build_cache_key(
            model=MODEL_DEFAULT,
            prompt="sys\n\nuser changed",
            schema_name="schema_a",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        changed_schema_key = pipeline_common.build_cache_key(
            model=MODEL_DEFAULT,
            prompt="sys\n\nuser",
            schema_name="schema_a",
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"a": {"type": "string"}},
                "required": ["a"],
            },
            input_payload={"x": 1},
        )

        self.assertNotEqual(base_key, changed_prompt_key)
        self.assertNotEqual(base_key, changed_schema_key)

    def test_get_openai_client_delegates_to_openai_utils(self) -> None:
        """Internal helper should delegate to openai_utils client factory."""
        sentinel_client = object()
        with patch.object(
            pipeline_common, "get_openai_client", return_value=sentinel_client
        ) as get_client_mock:
            client = pipeline_common._get_openai_client()
        self.assertIs(client, sentinel_client)
        get_client_mock.assert_called_once()

    def test_call_openai_once_uses_structured_output_contract(self) -> None:
        """Single call should send strict json_schema response format."""
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"a": 1}'))]
        )
        create_mock = unittest.mock.Mock(return_value=fake_response)
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )

        with patch.object(
            pipeline_common, "_get_openai_client", return_value=fake_client
        ):
            result = pipeline_common._call_openai_once(
                model=MODEL_DEFAULT,
                system_prompt="system",
                user_prompt="user",
                schema_name="simple_schema",
                schema=SIMPLE_SCHEMA,
                timeout_seconds=TIMEOUT_SECONDS_DEFAULT,
            )

        self.assertEqual(result, {"a": 1})
        create_kwargs = create_mock.call_args.kwargs
        self.assertEqual(create_kwargs["model"], MODEL_DEFAULT)
        self.assertEqual(create_kwargs["timeout"], TIMEOUT_SECONDS_DEFAULT)
        self.assertEqual(create_kwargs["response_format"]["type"], "json_schema")
        self.assertTrue(create_kwargs["response_format"]["json_schema"]["strict"])


if __name__ == "__main__":
    unittest.main()
