"""Tests for OpenAI client and API-key loading utilities."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import InvalidToken

import openai_utils


class OpenAIUtilsTests(unittest.TestCase):
    """Validate encrypted-dotenv key loading and strict fallback behavior."""

    def test_load_api_key_from_encrypted_dotenv_sets_environment(self) -> None:
        """Encrypted dotenv should be the primary source and set env key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            key_file = temp_path / "vault.key"
            enc_file = temp_path / "settings.env.enc"
            key_file.write_bytes(
                b"key",
            )
            enc_file.write_bytes(
                b"enc",
            )

            config_values = {
                openai_utils.DOTENV_MASTER_KEY_PATH_ENV_VAR: str(key_file),
                openai_utils.DOTENV_ENC_PATH_ENV_VAR: str(enc_file),
            }

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(
                    openai_utils,
                    "_load_dotenv_config_values",
                    return_value=config_values,
                ),
                patch.object(openai_utils, "DotenvVault") as vault_mock,
            ):
                vault_mock.return_value.load_to_environ.side_effect = lambda _: (
                    os.environ.__setitem__("OPENAI_API_KEY", "  sk-encrypted  ")
                )
                key = openai_utils._load_api_key_to_environ()
                self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-encrypted")

            self.assertEqual(key, "sk-encrypted")

    def test_encrypted_source_overwrites_existing_environment_key(self) -> None:
        """Encrypted source should replace pre-existing process key values."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            key_file = temp_path / "vault.key"
            enc_file = temp_path / "settings.env.enc"
            key_file.write_bytes(
                b"key",
            )
            enc_file.write_bytes(
                b"enc",
            )

            config_values = {
                openai_utils.DOTENV_MASTER_KEY_PATH_ENV_VAR: str(key_file),
                openai_utils.DOTENV_ENC_PATH_ENV_VAR: str(enc_file),
            }

            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "sk-old"}, clear=True),
                patch.object(
                    openai_utils,
                    "_load_dotenv_config_values",
                    return_value=config_values,
                ),
                patch.object(openai_utils, "DotenvVault") as vault_mock,
            ):
                vault_mock.return_value.load_to_environ.side_effect = lambda _: (
                    os.environ.__setitem__("OPENAI_API_KEY", "sk-new")
                )
                key = openai_utils._load_api_key_to_environ()
                self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-new")

            self.assertEqual(key, "sk-new")

    def test_plaintext_fallback_works_only_when_enabled(self) -> None:
        """Plain dotenv fallback should be used only with explicit config flag."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dotenv_path = temp_path / ".env"
            dotenv_path.write_text(
                "OPENAI_API_KEY=  sk-plain  \n",
                encoding="utf-8",
            )

            config_values = {
                openai_utils.OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK_ENV_VAR: "1",
                openai_utils.DOTENV_PATH_ENV_VAR: str(dotenv_path),
            }

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(
                    openai_utils,
                    "_load_dotenv_config_values",
                    return_value=config_values,
                ),
                patch.object(
                    openai_utils,
                    "_load_api_key_from_encrypted_dotenv",
                    side_effect=ValueError("encrypted failed"),
                ),
            ):
                key = openai_utils._load_api_key_to_environ()
                self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-plain")

            self.assertEqual(key, "sk-plain")

    def test_encrypted_load_failure_raises_when_fallback_disabled(self) -> None:
        """Missing encrypted credentials should raise when plaintext fallback is off."""
        with patch.dict(os.environ, {}, clear=True):
            with (
                patch.object(
                    openai_utils,
                    "_load_dotenv_config_values",
                    return_value={},
                ),
                patch.object(
                    openai_utils,
                    "_load_api_key_from_encrypted_dotenv",
                    side_effect=ValueError("missing key path"),
                ),
                self.assertRaises(ValueError),
            ):
                openai_utils._load_api_key_to_environ()

    def test_plaintext_loader_is_not_called_when_fallback_disabled(self) -> None:
        """Disabled fallback should never attempt plain dotenv loading."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                openai_utils,
                "_load_dotenv_config_values",
                return_value={
                    openai_utils.OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK_ENV_VAR: "0"
                },
            ),
            patch.object(
                openai_utils,
                "_load_api_key_from_encrypted_dotenv",
                side_effect=ValueError("encrypted failed"),
            ),
            patch.object(openai_utils, "_load_api_key_from_plain_dotenv") as plain_mock,
            self.assertRaises(ValueError),
        ):
            openai_utils._load_api_key_to_environ()

        plain_mock.assert_not_called()

    def test_invalid_fallback_flag_fails_fast(self) -> None:
        """Invalid fallback flag value should raise explicit ValueError."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                openai_utils,
                "_load_dotenv_config_values",
                return_value={
                    openai_utils.OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK_ENV_VAR: "maybe"
                },
            ),
            self.assertRaises(ValueError),
        ):
            openai_utils._load_api_key_to_environ()

    def test_encrypted_loader_uses_pipeline_default_key_path(self) -> None:
        """Encrypted loader should use default key path from pipeline config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            key_file = temp_path / "default.key"
            enc_file = temp_path / "default.env.enc"
            key_file.write_bytes(b"k")
            enc_file.write_bytes(b"e")

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(
                    openai_utils, "DOTENV_MASTER_KEY_PATH_DEFAULT_PATH", key_file
                ),
                patch.object(openai_utils, "DOTENV_ENC_PATH_DEFAULT_PATH", enc_file),
                patch.object(openai_utils, "DotenvVault") as vault_mock,
            ):
                vault_mock.return_value.load_to_environ.side_effect = lambda _: (
                    os.environ.__setitem__("OPENAI_API_KEY", "sk-from-defaults")
                )
                key = openai_utils._load_api_key_from_encrypted_dotenv({})

            self.assertEqual(key, "sk-from-defaults")

    def test_encrypted_loader_raises_when_master_key_file_missing(self) -> None:
        """Encrypted loader should fail fast when configured key file is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            encrypted_file = temp_path / "settings.env.enc"
            encrypted_file.write_bytes(b"enc")

            with self.assertRaises(FileNotFoundError):
                openai_utils._load_api_key_from_encrypted_dotenv(
                    {
                        openai_utils.DOTENV_MASTER_KEY_PATH_ENV_VAR: str(
                            temp_path / "missing.key"
                        ),
                        openai_utils.DOTENV_ENC_PATH_ENV_VAR: str(encrypted_file),
                    }
                )

    def test_encrypted_loader_raises_when_encrypted_file_missing(self) -> None:
        """Encrypted loader should fail fast when encrypted dotenv file is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            key_file = temp_path / "vault.key"
            key_file.write_bytes(b"key")

            with self.assertRaises(FileNotFoundError):
                openai_utils._load_api_key_from_encrypted_dotenv(
                    {
                        openai_utils.DOTENV_MASTER_KEY_PATH_ENV_VAR: str(key_file),
                        openai_utils.DOTENV_ENC_PATH_ENV_VAR: str(
                            temp_path / "missing.env.enc"
                        ),
                    }
                )

    def test_encrypted_loader_raises_on_invalid_token(self) -> None:
        """Encrypted loader should propagate invalid-token decrypt failures."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            key_file = temp_path / "vault.key"
            encrypted_file = temp_path / "settings.env.enc"
            key_file.write_bytes(b"key")
            encrypted_file.write_bytes(b"enc")

            with (
                patch.object(openai_utils, "DotenvVault") as vault_mock,
                self.assertRaises(InvalidToken),
            ):
                vault_mock.return_value.load_to_environ.side_effect = InvalidToken()
                openai_utils._load_api_key_from_encrypted_dotenv(
                    {
                        openai_utils.DOTENV_MASTER_KEY_PATH_ENV_VAR: str(key_file),
                        openai_utils.DOTENV_ENC_PATH_ENV_VAR: str(encrypted_file),
                    }
                )

    def test_encrypted_loader_raises_when_openai_key_missing_after_decrypt(
        self,
    ) -> None:
        """Encrypted loader should fail if decrypt succeeds but no API key is present."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            key_file = temp_path / "vault.key"
            encrypted_file = temp_path / "settings.env.enc"
            key_file.write_bytes(b"key")
            encrypted_file.write_bytes(b"enc")

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(openai_utils, "DotenvVault") as vault_mock,
                self.assertRaises(ValueError),
            ):
                vault_mock.return_value.load_to_environ.return_value = None
                openai_utils._load_api_key_from_encrypted_dotenv(
                    {
                        openai_utils.DOTENV_MASTER_KEY_PATH_ENV_VAR: str(key_file),
                        openai_utils.DOTENV_ENC_PATH_ENV_VAR: str(encrypted_file),
                    }
                )

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

    def test_get_async_openai_client_exits_when_key_missing(self) -> None:
        """Async client factory should fail fast when key is absent."""
        with (
            patch.object(openai_utils, "_load_api_key_to_environ", return_value=None),
            patch.object(openai_utils.logger, "error"),
            redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as context:
                openai_utils.get_async_openai_client()
            self.assertEqual(context.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
