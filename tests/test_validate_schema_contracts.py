"""Integration tests for schema contract validation against real schema files."""

import sys
import unittest

from project_paths import INGEST_DIR


if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import validate_schema_contracts


class ValidateSchemaContractsIntegrationTests(unittest.TestCase):
    """Validate schema contracts using repository schemas without any mocking."""

    def test_real_schema_contracts_are_valid(self) -> None:
        """Real pass_01 and pass_02 schema contracts should validate successfully."""
        report = validate_schema_contracts.run_validation()

        self.assertTrue(report["is_valid"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["pass_01_errors"], [])
        self.assertEqual(report["pass_02_errors"], [])


if __name__ == "__main__":
    unittest.main()
