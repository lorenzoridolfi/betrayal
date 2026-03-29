"""Generic cached OpenAI structured-output client helpers."""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from openai_utils import get_openai_client, get_openai_retryable_exceptions
from project_paths import ROOT_DIR


logger = logging.getLogger(__name__)

CACHE_DIR_ENV_VAR = "OPENAI_STRUCTURED_CACHE_DIR"
CACHE_DIR_DEFAULT = ROOT_DIR / ".cache" / "openai_structured"
CACHE_TTL_DAYS_ENV_VAR = "OPENAI_STRUCTURED_CACHE_TTL_DAYS"
CACHE_TTL_DAYS_DEFAULT = 30
MAX_ATTEMPTS_DEFAULT = 6


class StructuredOutputValidationError(Exception):
    """Raised when structured output is empty or fails JSON schema validation."""


def resolve_cache_dir() -> Path:
    """Resolve cache directory from environment or fallback default path."""
    configured_dir = os.environ.get(CACHE_DIR_ENV_VAR)
    if configured_dir:
        return Path(configured_dir)
    return CACHE_DIR_DEFAULT


def resolve_cache_ttl_days() -> int:
    """Resolve cache expiration in days from environment or default value."""
    raw_ttl_days = os.environ.get(CACHE_TTL_DAYS_ENV_VAR, str(CACHE_TTL_DAYS_DEFAULT))
    try:
        ttl_days = int(raw_ttl_days)
    except ValueError as error:
        raise ValueError(
            f"{CACHE_TTL_DAYS_ENV_VAR} must be an integer. Got '{raw_ttl_days}'."
        ) from error

    if ttl_days <= 0:
        raise ValueError(f"{CACHE_TTL_DAYS_ENV_VAR} must be greater than zero.")
    return ttl_days


def _is_cache_file_expired(cache_path: Path, ttl_days: int) -> bool:
    """Return True when a cache file is older than configured TTL days."""
    file_age_seconds = time.time() - cache_path.stat().st_mtime
    return file_age_seconds > (ttl_days * 24 * 60 * 60)


def hash_json(data: Any) -> str:
    """Return a deterministic hash for any JSON-serializable value."""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_cache_key(
    *,
    model: str,
    prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    input_payload: Any,
) -> str:
    """Build deterministic cache key from request-defining input values."""
    payload = {
        "model": model,
        "prompt": prompt,
        "schema_name": schema_name,
        "schema_hash": hash_json(schema),
        "input_hash": hash_json(input_payload),
    }
    return hash_json(payload)


def _cache_path(cache_key: str, cache_dir: Path) -> Path:
    """Build path for cached response JSON file under a cache directory."""
    return cache_dir / f"{cache_key}.json"


def load_cached_response(cache_key: str, cache_dir: Path | None = None) -> Any | None:
    """Load a cached response by key, returning None when not found."""
    effective_cache_dir = resolve_cache_dir() if cache_dir is None else cache_dir
    ttl_days = resolve_cache_ttl_days()
    path = _cache_path(cache_key, effective_cache_dir)
    if not path.exists():
        logger.debug("cache miss key=%s path=%s", cache_key, path)
        return None

    if _is_cache_file_expired(path, ttl_days):
        # Remove stale cache to avoid unbounded growth.
        path.unlink()
        logger.info("cache expired key=%s ttl_days=%d", cache_key, ttl_days)
        return None

    logger.info("cache hit key=%s", cache_key)
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_cached_response(
    cache_key: str, value: Any, cache_dir: Path | None = None
) -> Path:
    """Persist response to cache and return written file path."""
    effective_cache_dir = resolve_cache_dir() if cache_dir is None else cache_dir
    effective_cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_key, effective_cache_dir)
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)

    logger.info("cache save key=%s path=%s", cache_key, path)
    return path


def _build_retryable_exceptions() -> tuple[type[BaseException], ...]:
    """Build retryable exception tuple including OpenAI transport errors."""
    return (
        *get_openai_retryable_exceptions(),
        TimeoutError,
        StructuredOutputValidationError,
    )


def _call_openai_once(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    timeout_seconds: int,
) -> Any:
    """Execute one strict-schema OpenAI chat completion and validate JSON output."""
    client = get_openai_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
        timeout=timeout_seconds,
    )

    content = response.choices[0].message.content
    if not content:
        raise StructuredOutputValidationError("Model returned empty content.")

    parsed = json.loads(content)
    try:
        validate(instance=parsed, schema=schema)
    except ValidationError as error:
        raise StructuredOutputValidationError(str(error)) from error
    return parsed


def call_openai_structured_cached(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    input_payload: Any,
    timeout_seconds: int = 240,
    max_attempts: int = MAX_ATTEMPTS_DEFAULT,
    cache_dir: Path | None = None,
) -> Any:
    """Call OpenAI structured output with deterministic cache and retries."""
    cache_key = build_cache_key(
        model=model,
        prompt=f"{system_prompt}\n\n{user_prompt}",
        schema_name=schema_name,
        schema=schema,
        input_payload=input_payload,
    )
    cached = load_cached_response(cache_key, cache_dir=cache_dir)
    if cached is not None:
        return cached

    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception_type(_build_retryable_exceptions()),
        reraise=True,
    )

    last_result: Any = None
    for attempt in retryer:
        logger.debug(
            "openai call attempt=%d schema=%s",
            attempt.retry_state.attempt_number,
            schema_name,
        )
        with attempt:
            last_result = _call_openai_once(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_name=schema_name,
                schema=schema,
                timeout_seconds=timeout_seconds,
            )

    save_cached_response(cache_key, last_result, cache_dir=cache_dir)
    return last_result
