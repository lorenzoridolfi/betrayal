"""Tests for generic OpenAI structured-output cache helpers."""

import tempfile
import unittest
import os
import time
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

    def test_build_cache_key_changes_when_model_changes(self) -> None:
        """Different model names should produce different cache keys."""
        mini_key = openai_structured_cache.build_cache_key(
            model="gpt-5-mini",
            prompt="sys\n\nuser",
            schema_name="schema",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        full_key = openai_structured_cache.build_cache_key(
            model="gpt-5.4",
            prompt="sys\n\nuser",
            schema_name="schema",
            schema=SIMPLE_SCHEMA,
            input_payload={"x": 1},
        )
        self.assertNotEqual(mini_key, full_key)

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

    def test_uses_cache_dir_from_environment_variable(self) -> None:
        """Cache directory should resolve from OPENAI_STRUCTURED_CACHE_DIR env var."""
        with tempfile.TemporaryDirectory() as temp_dir:
            env_cache_dir = Path(temp_dir) / "env-cache"
            with (
                patch.dict(
                    os.environ,
                    {openai_structured_cache.CACHE_DIR_ENV_VAR: str(env_cache_dir)},
                    clear=False,
                ),
                patch.object(
                    openai_structured_cache, "_call_openai_once", return_value={"a": 11}
                ) as call_mock,
            ):
                result = openai_structured_cache.call_openai_structured_cached(
                    model="gpt-5-mini",
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="schema",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 8},
                )

            self.assertEqual(result, {"a": 11})
            self.assertEqual(call_mock.call_count, 1)
            self.assertEqual(len(list(env_cache_dir.glob("*.json"))), 1)

    def test_raises_after_max_attempts_on_retryable_error(self) -> None:
        """Retry loop should re-raise after max attempts is exhausted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            with patch.object(
                openai_structured_cache,
                "_call_openai_once",
                side_effect=TimeoutError("still failing"),
            ) as call_mock:
                with self.assertRaises(TimeoutError):
                    openai_structured_cache.call_openai_structured_cached(
                        model="gpt-5-mini",
                        system_prompt="sys",
                        user_prompt="user",
                        schema_name="schema",
                        schema=SIMPLE_SCHEMA,
                        input_payload={"x": 9},
                        cache_dir=cache_dir,
                        max_attempts=2,
                    )

            self.assertEqual(call_mock.call_count, 2)
            self.assertEqual(len(list(cache_dir.glob("*.json"))), 0)

    def test_cache_expiration_uses_ttl_days(self) -> None:
        """Expired cache file should be treated as miss and refreshed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            cache_key = openai_structured_cache.build_cache_key(
                model="gpt-5-mini",
                prompt="sys\n\nuser",
                schema_name="schema",
                schema=SIMPLE_SCHEMA,
                input_payload={"x": 10},
            )
            cache_path = openai_structured_cache.save_cached_response(
                cache_key, {"a": 99}, cache_dir=cache_dir
            )
            old_timestamp = time.time() - (31 * 24 * 60 * 60)
            os.utime(cache_path, (old_timestamp, old_timestamp))

            with (
                patch.dict(
                    os.environ,
                    {openai_structured_cache.CACHE_TTL_DAYS_ENV_VAR: "30"},
                    clear=False,
                ),
                patch.object(
                    openai_structured_cache, "_call_openai_once", return_value={"a": 5}
                ) as call_mock,
            ):
                result = openai_structured_cache.call_openai_structured_cached(
                    model="gpt-5-mini",
                    system_prompt="sys",
                    user_prompt="user",
                    schema_name="schema",
                    schema=SIMPLE_SCHEMA,
                    input_payload={"x": 10},
                    cache_dir=cache_dir,
                )

            self.assertEqual(result, {"a": 5})
            self.assertEqual(call_mock.call_count, 1)

    def test_invalid_cache_ttl_value_fails_fast(self) -> None:
        """Invalid cache TTL value should raise ValueError clearly."""
        with patch.dict(
            os.environ,
            {openai_structured_cache.CACHE_TTL_DAYS_ENV_VAR: "abc"},
            clear=False,
        ):
            with self.assertRaises(ValueError):
                openai_structured_cache.resolve_cache_ttl_days()

    def test_default_retry_attempts_is_six_when_not_overridden(self) -> None:
        """Default retry budget should be six attempts for all LLM calls."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            with patch.object(
                openai_structured_cache,
                "_call_openai_once",
                side_effect=TimeoutError("always failing"),
            ) as call_mock:
                with self.assertRaises(TimeoutError):
                    openai_structured_cache.call_openai_structured_cached(
                        model="gpt-5-mini",
                        system_prompt="sys",
                        user_prompt="user",
                        schema_name="schema",
                        schema=SIMPLE_SCHEMA,
                        input_payload={"x": 11},
                        cache_dir=cache_dir,
                    )

            self.assertGreater(openai_structured_cache.MAX_ATTEMPTS_DEFAULT, 0)
            self.assertEqual(
                call_mock.call_count, openai_structured_cache.MAX_ATTEMPTS_DEFAULT
            )


if __name__ == "__main__":
    unittest.main()
