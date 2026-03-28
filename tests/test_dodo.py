"""Tests for doit task definitions in ingest/dodo.py."""

import sys
import unittest

from project_paths import INGEST_DIR


if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import dodo
from pipeline_params import (
    PASS_01_5_SCRIPT,
    PROFILE_CHOICES,
    PROFILE_DEFAULT,
    RUN_PIPELINE_SCRIPT,
    SCHEMA_CONTRACT_VALIDATION_FILE,
    VALIDATE_SCHEMA_CONTRACTS_SCRIPT,
)


class DodoTests(unittest.TestCase):
    """Validate expected doit tasks and parameters."""

    def test_has_schema_contract_validation_task(self) -> None:
        """Ensure schema-contract task declares expected deps and target."""
        task = dodo.task_validate_schema_contracts()
        self.assertIn(str(VALIDATE_SCHEMA_CONTRACTS_SCRIPT), task["file_dep"])
        self.assertIn(str(SCHEMA_CONTRACT_VALIDATION_FILE), task["targets"])

    def test_has_single_pipeline_task_with_profile_param(self) -> None:
        """Ensure pipeline task exposes one profile parameter."""
        task = dodo.task_pipeline()

        self.assertIn(str(RUN_PIPELINE_SCRIPT), task["file_dep"])
        self.assertIn(str(PASS_01_5_SCRIPT), task["file_dep"])
        self.assertIn(
            f"uv run python {RUN_PIPELINE_SCRIPT} %(profile)s", task["actions"]
        )

        params = task["params"]
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["name"], "profile")
        self.assertEqual(params[0]["default"], PROFILE_DEFAULT)
        self.assertEqual(params[0]["choices"], list(PROFILE_CHOICES))
        self.assertIn("validate_schema_contracts", task["task_dep"])


if __name__ == "__main__":
    unittest.main()
