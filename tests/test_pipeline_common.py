import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
INGEST_DIR = ROOT_DIR / "ingest"
if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import pipeline_common


SIMPLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"a": {"type": "integer"}},
    "required": ["a"],
}


class PipelineCommonTests(unittest.TestCase):
    def test_cache_hit_skips_llm_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(pipeline_common, "CACHE_DIR", Path(temp_dir) / "cache"):
                cached_value = {"a": 7}
                key = pipeline_common.build_cache_key(
                    model="gpt-5-mini",
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
                        model="gpt-5-mini",
                        system_prompt="sys",
                        user_prompt="user",
                        schema_name="s",
                        schema=SIMPLE_SCHEMA,
                        input_payload={"x": 1},
                        timeout_seconds=240,
                    )

                self.assertEqual(result, cached_value)

    def test_cache_miss_calls_llm_and_saves_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            with (
                patch.object(pipeline_common, "CACHE_DIR", cache_dir),
                patch.object(
                    pipeline_common, "_call_openai_once", return_value={"a": 1}
                ) as llm_mock,
            ):
                result = pipeline_common.call_openai_structured_cached(
                    model="gpt-5-mini",
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="s",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 2},
                    timeout_seconds=240,
                )

                self.assertEqual(result, {"a": 1})
                self.assertEqual(llm_mock.call_count, 1)
                self.assertEqual(len(list(cache_dir.glob("*.json"))), 1)

    def test_retries_on_timeout_and_succeeds(self) -> None:
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
                    model="gpt-5-mini",
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="s",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 3},
                    timeout_seconds=240,
                )

                self.assertEqual(result, {"a": 3})
                self.assertEqual(llm_mock.call_count, 2)

    def test_retries_on_schema_error_and_succeeds(self) -> None:
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
                    model="gpt-5-mini",
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="s",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 5},
                    timeout_seconds=240,
                )

                self.assertEqual(result, {"a": 5})
                self.assertEqual(llm_mock.call_count, 2)

    def test_raises_after_max_attempts(self) -> None:
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
                        model="gpt-5-mini",
                        system_prompt="sys",
                        user_prompt="user",
                        schema_name="s",
                        schema=SIMPLE_SCHEMA,
                        input_payload={"x": 6},
                        timeout_seconds=240,
                        max_attempts=2,
                    )

    def test_cache_key_is_deterministic(self) -> None:
        key_1 = pipeline_common.build_cache_key(
            model="gpt-5-mini",
            prompt="sys\n\nuser",
            schema_name="schema_a",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        key_2 = pipeline_common.build_cache_key(
            model="gpt-5-mini",
            prompt="sys\n\nuser",
            schema_name="schema_a",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        self.assertEqual(key_1, key_2)

    def test_cache_key_changes_with_prompt_or_schema(self) -> None:
        base_key = pipeline_common.build_cache_key(
            model="gpt-5-mini",
            prompt="sys\n\nuser",
            schema_name="schema_a",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        changed_prompt_key = pipeline_common.build_cache_key(
            model="gpt-5-mini",
            prompt="sys\n\nuser changed",
            schema_name="schema_a",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        changed_schema_key = pipeline_common.build_cache_key(
            model="gpt-5-mini",
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
        sentinel_client = object()
        with patch.object(
            pipeline_common, "get_openai_client", return_value=sentinel_client
        ) as get_client_mock:
            client = pipeline_common._get_openai_client()
        self.assertIs(client, sentinel_client)
        get_client_mock.assert_called_once()

    def test_call_openai_once_uses_structured_output_contract(self) -> None:
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
                model="gpt-5-mini",
                system_prompt="system",
                user_prompt="user",
                schema_name="simple_schema",
                schema=SIMPLE_SCHEMA,
                timeout_seconds=240,
            )

        self.assertEqual(result, {"a": 1})
        create_kwargs = create_mock.call_args.kwargs
        self.assertEqual(create_kwargs["model"], "gpt-5-mini")
        self.assertEqual(create_kwargs["timeout"], 240)
        self.assertEqual(create_kwargs["response_format"]["type"], "json_schema")
        self.assertTrue(create_kwargs["response_format"]["json_schema"]["strict"])


if __name__ == "__main__":
    unittest.main()
