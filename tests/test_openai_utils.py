import os
import unittest
from unittest.mock import patch

import openai_utils


class OpenAIUtilsTests(unittest.TestCase):
    def test_load_api_key_from_encrypted_env(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(openai_utils.DotenvVault, "load_to_environ") as load_encrypted,
            patch.object(openai_utils, "load_dotenv"),
        ):
            load_encrypted.side_effect = lambda _: os.environ.__setitem__(
                "OPENAI_API_KEY", "  sk-encrypted  "
            )

            key = openai_utils._load_api_key_to_environ()

            self.assertEqual(key, "sk-encrypted")
            self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-encrypted")

    def test_fallback_to_plain_env_when_encrypted_fails(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                openai_utils.DotenvVault,
                "load_to_environ",
                side_effect=RuntimeError("cannot decrypt"),
            ),
            patch.object(openai_utils, "load_dotenv") as load_dotenv,
        ):
            load_dotenv.side_effect = lambda **_: os.environ.__setitem__(
                "OPENAI_API_KEY", "sk-plain"
            )

            key = openai_utils._load_api_key_to_environ()

            self.assertEqual(key, "sk-plain")
            self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-plain")

    def test_get_openai_client_exits_when_key_missing(self) -> None:
        with patch.object(openai_utils, "_load_api_key_to_environ", return_value=None):
            with self.assertRaises(SystemExit) as context:
                openai_utils.get_openai_client()
            self.assertEqual(context.exception.code, 1)

    def test_uses_openai_key_path_from_env(self) -> None:
        with patch.dict(os.environ, {"OPENAI_KEY_PATH": "/tmp/custom.key"}, clear=True):
            with (
                patch.object(
                    openai_utils.DotenvVault, "__init__", return_value=None
                ) as init_mock,
                patch.object(openai_utils.DotenvVault, "load_to_environ"),
            ):
                openai_utils._load_api_key_to_environ()
            init_mock.assert_called_once_with("/tmp/custom.key")


if __name__ == "__main__":
    unittest.main()
