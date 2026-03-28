"""OpenAI client helpers that require `OPENAI_API_KEY` in environment."""

import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI, OpenAI

logger = logging.getLogger(__name__)


def _load_api_key_to_environ() -> str | None:
    """Return normalized `OPENAI_API_KEY` from process environment only."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key and api_key.strip():
        normalized_api_key = api_key.strip()
        os.environ["OPENAI_API_KEY"] = normalized_api_key
        logger.debug("OPENAI_API_KEY loaded from environment.")
        return normalized_api_key

    logger.error("OPENAI_API_KEY is missing from environment.")
    return None


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
        print(
            "[FATAL] OPENAI_API_KEY is not defined in environment! Aborting.",
            file=sys.stderr,
        )
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
        print(
            "[FATAL] OPENAI_API_KEY is not defined in environment! Aborting.",
            file=sys.stderr,
        )
        sys.exit(1)
    return AsyncOpenAI(api_key=api_key)


def get_openai_api_key() -> str | None:
    """Return normalized `OPENAI_API_KEY` from environment or `None`."""
    return _load_api_key_to_environ()
