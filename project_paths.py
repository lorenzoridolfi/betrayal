"""Project-wide path constants used by scripts, pipeline, and tests."""

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
SCHEMAS_DIR = ROOT_DIR / "schemas"
PROMPTS_DIR = ROOT_DIR / "prompts"
INGEST_DIR = ROOT_DIR / "ingest"
