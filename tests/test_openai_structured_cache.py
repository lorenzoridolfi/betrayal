"""Tests for generic OpenAI structured-output cache helpers."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import openai_structured_cache


SIMPLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"a": {"type": "integer"}},
    "required": ["a"],
}


class OpenAIStructuredCacheTests(unittest.TestCase):
    """Validate cache hit/miss, retry, and strict schema behavior."""

    def test_cache_hit_skips_openai_call(self) -> None:
        """Cache hit should return cached value without OpenAI call."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            cache_key = openai_structured_cache.build_cache_key(
                model="gpt-5-mini",
                prompt="sys\n\nuser",
                schema_name="schema",
                schema=SIMPLE_SCHEMA,
                input_payload={"x": 1},
            )
            openai_structured_cache.save_cached_response(
                cache_key, {"a": 7}, cache_dir=cache_dir
            )

            with patch.object(
                openai_structured_cache,
                "_call_openai_once",
                side_effect=AssertionError("must not call OpenAI on cache hit"),
            ):
                result = openai_structured_cache.call_openai_structured_cached(
                    model="gpt-5-mini",
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="schema",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 1},
                    cache_dir=cache_dir,
                )

        self.assertEqual(result, {"a": 7})

    def test_cache_miss_calls_openai_and_saves(self) -> None:
        """Cache miss should call OpenAI once and persist output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            with patch.object(
                openai_structured_cache, "_call_openai_once", return_value={"a": 1}
            ) as call_mock:
                result = openai_structured_cache.call_openai_structured_cached(
                    model="gpt-5-mini",
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="schema",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 2},
                    cache_dir=cache_dir,
                )

            self.assertEqual(result, {"a": 1})
            self.assertEqual(call_mock.call_count, 1)
            self.assertEqual(len(list(cache_dir.glob("*.json"))), 1)

    def test_retries_on_timeout_then_succeeds(self) -> None:
        """Retry loop should recover from transient timeout errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            with patch.object(
                openai_structured_cache,
                "_call_openai_once",
                side_effect=[TimeoutError("timeout"), {"a": 3}],
            ) as call_mock:
                result = openai_structured_cache.call_openai_structured_cached(
                    model="gpt-5-mini",
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="schema",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 3},
                    cache_dir=cache_dir,
                )

            self.assertEqual(result, {"a": 3})
            self.assertEqual(call_mock.call_count, 2)

    def test_build_cache_key_is_deterministic(self) -> None:
        """Equivalent requests should produce equal cache keys."""
        key_1 = openai_structured_cache.build_cache_key(
            model="gpt-5-mini",
            prompt="sys\n\nuser",
            schema_name="schema",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        key_2 = openai_structured_cache.build_cache_key(
            model="gpt-5-mini",
            prompt="sys\n\nuser",
            schema_name="schema",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        self.assertEqual(key_1, key_2)

    def test_call_openai_once_enforces_structured_contract(self) -> None:
        """Single call should use strict json_schema and validate response."""
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"a": 1}'))]
        )
        create_mock = unittest.mock.Mock(return_value=fake_response)
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )

        with patch.object(
            openai_structured_cache, "get_openai_client", return_value=fake_client
        ):
            result = openai_structured_cache._call_openai_once(
                model="gpt-5-mini",
                system_prompt="system",
                user_prompt="user",
                schema_name="simple_schema",
                schema=SIMPLE_SCHEMA,
                timeout_seconds=240,
            )

        self.assertEqual(result, {"a": 1})
        call_kwargs = create_mock.call_args.kwargs
        self.assertEqual(call_kwargs["response_format"]["type"], "json_schema")
        self.assertTrue(call_kwargs["response_format"]["json_schema"]["strict"])


if __name__ == "__main__":
    unittest.main()
