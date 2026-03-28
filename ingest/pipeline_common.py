"""Shared helpers for schema validation, prompt rendering, and OpenAI calls."""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from jsonschema import ValidationError, validate
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT_DIR / ".cache" / "openai_structured"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openai_utils import get_openai_client, get_openai_retryable_exceptions


class SchemaValidationError(Exception):
    """Raised when model output fails strict schema validation."""

    pass


def read_json(path: Path) -> Any:
    """Read JSON from disk and return the decoded value."""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_text_file(path: Path) -> str:
    """Read a UTF-8 text file and trim outer whitespace."""
    with path.open("r", encoding="utf-8") as file:
        return file.read().strip()


def render_prompt_template(template_path: Path, context: dict[str, Any]) -> str:
    """Render a Jinja template with strict undefined handling."""
    environment = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        autoescape=False,
    )
    template = environment.get_template(template_path.name)
    return template.render(**context).strip()


def write_json(path: Path, data: Any) -> None:
    """Write JSON to disk with UTF-8 and stable indentation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_schema(path: Path) -> dict[str, Any]:
    """Load and return a JSON schema document from disk."""
    return read_json(path)


def validate_with_schema(data: Any, schema: dict[str, Any]) -> None:
    """Validate data against JSON schema and raise on mismatch."""
    validate(instance=data, schema=schema)


def chapter_id_from_order(chapter_order: int) -> str:
    """Build a stable chapter identifier from a 1-based order."""
    return f"betrayal-{chapter_order:03d}"


def chunk_id_from_order(chapter_id: str, chunk_order: int) -> str:
    """Build a stable chunk identifier from chapter and chunk order."""
    return f"{chapter_id}-chunk-{chunk_order:03d}"


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
    """Create a cache key from model, prompts, schema, and input payload."""
    payload = {
        "model": model,
        "prompt": prompt,
        "schema_name": schema_name,
        "schema_hash": hash_json(schema),
        "input_hash": hash_json(input_payload),
    }
    return hash_json(payload)


def _cache_path(cache_key: str) -> Path:
    """Return the cache file path for a given cache key."""
    return CACHE_DIR / f"{cache_key}.json"


def load_cached_response(cache_key: str) -> Any | None:
    """Load a cached model response if present."""
    path = _cache_path(cache_key)
    if not path.exists():
        return None
    return read_json(path)


def save_cached_response(cache_key: str, value: Any) -> None:
    """Persist a model response in the structured-output cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    write_json(_cache_path(cache_key), value)


def _get_openai_client() -> Any:
    """Return a configured OpenAI client."""
    return get_openai_client()


def _build_retryable_exception_tuple() -> tuple[type[BaseException], ...]:
    """Build retryable exception tuple including OpenAI transport errors."""
    return (
        *get_openai_retryable_exceptions(),
        TimeoutError,
        SchemaValidationError,
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
    """Call OpenAI once using strict JSON schema response_format."""
    client = _get_openai_client()
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
        raise SchemaValidationError("Model returned empty content.")

    parsed = json.loads(content)
    try:
        validate_with_schema(parsed, schema)
    except ValidationError as error:
        raise SchemaValidationError(str(error)) from error
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
    max_attempts: int = 3,
) -> Any:
    """Call OpenAI with retries and cache the validated response."""
    cache_key = build_cache_key(
        model=model,
        prompt=f"{system_prompt}\n\n{user_prompt}",
        schema_name=schema_name,
        schema=schema,
        input_payload=input_payload,
    )
    cached = load_cached_response(cache_key)
    if cached is not None:
        return cached

    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception_type(_build_retryable_exception_tuple()),
        reraise=True,
    )

    last_result: Any = None
    for attempt in retryer:
        with attempt:
            last_result = _call_openai_once(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_name=schema_name,
                schema=schema,
                timeout_seconds=timeout_seconds,
            )

    save_cached_response(cache_key, last_result)
    return last_result
