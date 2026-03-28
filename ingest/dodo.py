"""doit tasks for schema-contract checks and pipeline execution."""

from pathlib import Path

from pipeline_params import (
    PIPELINE_FILE_DEPS,
    PROFILE_CHOICES,
    PROFILE_DEFAULT,
    RUN_PIPELINE_SCRIPT,
    SCHEMA_CONTRACT_FILE_DEPS,
    SCHEMA_CONTRACT_VALIDATION_FILE,
    VALIDATE_SCHEMA_CONTRACTS_SCRIPT,
)


ROOT_DIR = Path(__file__).resolve().parents[1]

DOIT_CONFIG = {
    "dep_file": str(ROOT_DIR / ".doit"),
}


def task_validate_schema_contracts() -> dict[str, object]:
    """Validate item-vs-book schema compatibility before running pipeline."""
    return {
        "file_dep": [str(path) for path in SCHEMA_CONTRACT_FILE_DEPS],
        "targets": [str(SCHEMA_CONTRACT_VALIDATION_FILE)],
        "actions": [f"uv run python {VALIDATE_SCHEMA_CONTRACTS_SCRIPT}"],
        "clean": True,
    }


def task_pipeline() -> dict[str, object]:
    """Run the three-step ingest pipeline for the selected profile."""
    return {
        "task_dep": ["validate_schema_contracts"],
        "file_dep": [str(path) for path in PIPELINE_FILE_DEPS],
        "actions": [f"uv run python {RUN_PIPELINE_SCRIPT} %(profile)s"],
        "params": [
            {
                "name": "profile",
                "long": "profile",
                "default": PROFILE_DEFAULT,
                "choices": list(PROFILE_CHOICES),
            }
        ],
        "clean": True,
    }
