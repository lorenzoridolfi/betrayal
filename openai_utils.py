"""OpenAI client helpers that load credentials from encrypted dotenv first."""

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.fernet import InvalidToken
from dotenv import dotenv_values

from dotenv_crypt import DotenvVault
from ingest.pipeline_params import (
    DOTENV_ENC_PATH_DEFAULT,
    DOTENV_MASTER_KEY_PATH_DEFAULT,
    OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK_DEFAULT,
)
from project_paths import ROOT_DIR

if TYPE_CHECKING:
    from openai import AsyncOpenAI, OpenAI

logger = logging.getLogger(__name__)

DOTENV_PATH_ENV_VAR = "DOTENV_PATH"
DOTENV_ENC_PATH_ENV_VAR = "DOTENV_ENC_PATH"
DOTENV_MASTER_KEY_PATH_ENV_VAR = "DOTENV_MASTER_KEY_PATH"
OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK_ENV_VAR = (
    "OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK"
)
DOTENV_PATH_DEFAULT = ROOT_DIR / ".env"
DOTENV_MASTER_KEY_PATH_DEFAULT_PATH = Path(DOTENV_MASTER_KEY_PATH_DEFAULT).expanduser()
DOTENV_ENC_PATH_DEFAULT_PATH = (
    Path(DOTENV_ENC_PATH_DEFAULT).expanduser()
    if Path(DOTENV_ENC_PATH_DEFAULT).expanduser().is_absolute()
    else ROOT_DIR / Path(DOTENV_ENC_PATH_DEFAULT)
)


def _resolve_path(path_value: str | None, default_path: Path) -> Path:
    """Resolve a configured path with support for home and relative values."""
    if path_value is None or not path_value.strip():
        candidate = default_path
    else:
        candidate = Path(path_value.strip()).expanduser()
        if not candidate.is_absolute():
            candidate = ROOT_DIR / candidate
    return candidate


def _normalize_and_store_api_key(api_key: str | None, source: str) -> str | None:
    """Normalize loaded API key and always set `OPENAI_API_KEY` in environment."""
    if api_key is None or not api_key.strip():
        return None
    normalized_api_key = api_key.strip()
    os.environ["OPENAI_API_KEY"] = normalized_api_key
    logger.debug("OPENAI_API_KEY loaded from %s.", source)
    return normalized_api_key


def _load_dotenv_config_values() -> dict[str, str]:
    """Load dotenv key/value config used to locate encrypted credentials."""
    dotenv_path = _resolve_path(
        os.environ.get(DOTENV_PATH_ENV_VAR), DOTENV_PATH_DEFAULT
    )
    if not dotenv_path.exists():
        return {}

    raw_values = dotenv_values(dotenv_path=dotenv_path)
    config_values: dict[str, str] = {}
    for key, value in raw_values.items():
        if value is not None and value.strip():
            config_values[key] = value.strip()
    return config_values


def _resolve_config_value(
    config_values: dict[str, str],
    env_var_name: str,
    *,
    default_value: str | None = None,
) -> str | None:
    """Resolve config from environment first, then dotenv config, then default."""
    env_value = os.environ.get(env_var_name)
    if env_value is not None and env_value.strip():
        return env_value.strip()
    if env_var_name in config_values:
        return config_values[env_var_name]
    return default_value


def _parse_boolean_flag(raw_value: str | None, *, setting_name: str) -> bool:
    """Parse strict boolean flags used by credential loading settings."""
    if raw_value is None:
        return False

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(
        f"{setting_name} must be one of: 1,true,yes,on,0,false,no,off. "
        f"Got '{raw_value}'."
    )


def _load_api_key_from_encrypted_dotenv(config_values: dict[str, str]) -> str:
    """Load API key from encrypted dotenv and export it to environment."""
    master_key_path_value = _resolve_config_value(
        config_values,
        DOTENV_MASTER_KEY_PATH_ENV_VAR,
        default_value=DOTENV_MASTER_KEY_PATH_DEFAULT,
    )
    if master_key_path_value is None:
        raise ValueError(
            f"Missing required setting {DOTENV_MASTER_KEY_PATH_ENV_VAR}. "
            f"Set it in environment, {DOTENV_PATH_DEFAULT}, or ingest.pipeline_params."
        )

    master_key_path = _resolve_path(
        master_key_path_value,
        DOTENV_MASTER_KEY_PATH_DEFAULT_PATH,
    )
    encrypted_dotenv_path_value = _resolve_config_value(
        config_values,
        DOTENV_ENC_PATH_ENV_VAR,
        default_value=DOTENV_ENC_PATH_DEFAULT,
    )
    encrypted_dotenv_path = _resolve_path(
        encrypted_dotenv_path_value,
        DOTENV_ENC_PATH_DEFAULT_PATH,
    )

    if not master_key_path.exists():
        raise FileNotFoundError(
            f"Configured dotenv master key file does not exist: {master_key_path}"
        )
    if not encrypted_dotenv_path.exists():
        raise FileNotFoundError(
            f"Configured encrypted dotenv file does not exist: {encrypted_dotenv_path}"
        )

    vault = DotenvVault(str(master_key_path))
    vault.load_to_environ(str(encrypted_dotenv_path))
    loaded_key = _normalize_and_store_api_key(
        os.environ.get("OPENAI_API_KEY"),
        source=f"encrypted dotenv ({encrypted_dotenv_path})",
    )
    if loaded_key is None:
        raise ValueError(
            "Encrypted dotenv loaded but OPENAI_API_KEY is missing or empty."
        )
    return loaded_key


def _load_api_key_from_plain_dotenv(config_values: dict[str, str]) -> str:
    """Load API key from plaintext dotenv and export it to environment."""
    dotenv_path_value = _resolve_config_value(
        config_values,
        DOTENV_PATH_ENV_VAR,
        default_value=str(DOTENV_PATH_DEFAULT),
    )
    dotenv_path = _resolve_path(dotenv_path_value, DOTENV_PATH_DEFAULT)
    if not dotenv_path.exists():
        raise FileNotFoundError(f"Configured dotenv file does not exist: {dotenv_path}")

    dotenv_map = dotenv_values(dotenv_path=dotenv_path)
    loaded_key = _normalize_and_store_api_key(
        dotenv_map.get("OPENAI_API_KEY"),
        source=f"plain dotenv ({dotenv_path})",
    )
    if loaded_key is None:
        raise ValueError("Plain dotenv is missing OPENAI_API_KEY or it is empty.")
    return loaded_key


def _load_api_key_to_environ() -> str | None:
    """Load API key from encrypted dotenv, with optional plaintext fallback.

    This function is intentionally fail-fast: encrypted-load errors are re-raised
    unless explicit plaintext fallback is enabled.
    """
    config_values = _load_dotenv_config_values()
    fallback_default_value = (
        "1" if OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK_DEFAULT else "0"
    )
    fallback_flag_value = _resolve_config_value(
        config_values,
        OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK_ENV_VAR,
        default_value=fallback_default_value,
    )
    allow_plaintext_fallback = _parse_boolean_flag(
        fallback_flag_value,
        setting_name=OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK_ENV_VAR,
    )

    try:
        return _load_api_key_from_encrypted_dotenv(config_values)
    except (FileNotFoundError, OSError, InvalidToken, ValueError) as error:
        if not allow_plaintext_fallback:
            raise

        encrypted_error = error
        try:
            return _load_api_key_from_plain_dotenv(config_values)
        except (FileNotFoundError, ValueError) as plain_error:
            raise ValueError(
                "Failed to load OPENAI_API_KEY from plaintext dotenv fallback after "
                f"encrypted dotenv failure: {encrypted_error}"
            ) from plain_error


def get_openai_retryable_exceptions() -> tuple[type[BaseException], ...]:
    """Return retryable OpenAI exception classes when SDK is installed."""
    try:
        from openai import APIConnectionError, APITimeoutError
    except ModuleNotFoundError:
        return ()
    return (APITimeoutError, APIConnectionError)


def get_openai_client() -> "OpenAI":
    """Create a synchronous OpenAI client; fail fast if key is missing."""
    try:
        from openai import OpenAI
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "Missing dependency 'openai'. Install dependencies with `uv sync`."
        ) from error

    api_key = _load_api_key_to_environ()
    if api_key is None:
        logger.error("[FATAL] OPENAI_API_KEY is not defined in environment! Aborting.")
        sys.exit(1)
    return OpenAI(api_key=api_key)


def get_async_openai_client() -> "AsyncOpenAI":
    """Create an async OpenAI client; fail fast if key is missing."""
    try:
        from openai import AsyncOpenAI
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "Missing dependency 'openai'. Install dependencies with `uv sync`."
        ) from error

    api_key = _load_api_key_to_environ()
    if api_key is None:
        logger.error("[FATAL] OPENAI_API_KEY is not defined in environment! Aborting.")
        sys.exit(1)
    return AsyncOpenAI(api_key=api_key)


def get_openai_api_key() -> str | None:
    """Return resolved `OPENAI_API_KEY` loaded using configured credential sources."""
    return _load_api_key_to_environ()
