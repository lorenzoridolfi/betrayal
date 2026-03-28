"""Tests for OpenAI client and API-key loading utilities."""

import io
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import openai_utils


class OpenAIUtilsTests(unittest.TestCase):
    """Validate environment-only key loading and client guards."""

    def test_load_api_key_from_environment(self) -> None:
        """Environment key should be trimmed and returned."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "  sk-env  "}, clear=True):
            key = openai_utils._load_api_key_to_environ()

            self.assertEqual(key, "sk-env")
            self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-env")

    def test_returns_none_when_key_missing(self) -> None:
        """Missing key should return None without fallback loaders."""
        with patch.dict(os.environ, {}, clear=True):
            key = openai_utils._load_api_key_to_environ()
            self.assertIsNone(key)

    def test_get_openai_client_exits_when_key_missing(self) -> None:
        """Client factory should fail fast when key is absent."""
        with (
            patch.object(openai_utils, "_load_api_key_to_environ", return_value=None),
            patch.object(openai_utils.logger, "error"),
            redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as context:
                openai_utils.get_openai_client()
            self.assertEqual(context.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
