"""Shared helpers for IO, schema validation, and generic structured OpenAI caching."""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from jsonschema import validate


ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openai_structured_cache import (
    StructuredOutputValidationError,
    build_cache_key,
    call_openai_structured_cached,
    hash_json,
    load_cached_response,
    save_cached_response,
)


logger = logging.getLogger(__name__)

# Backward-compatible alias used by ingest scripts and tests.
SchemaValidationError = StructuredOutputValidationError


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
