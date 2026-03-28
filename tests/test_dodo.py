import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
INGEST_DIR = ROOT_DIR / "ingest"
if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import dodo


class DodoTests(unittest.TestCase):
    def test_has_single_pipeline_task_with_profile_param(self) -> None:
        task = dodo.task_pipeline()

        self.assertIn("ingest/run_pipeline.py", task["file_dep"])
        self.assertIn(
            "uv run python ingest/run_pipeline.py %(profile)s", task["actions"]
        )

        params = task["params"]
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["name"], "profile")
        self.assertEqual(params[0]["default"], "full")
        self.assertEqual(params[0]["choices"], ["full", "preview"])


if __name__ == "__main__":
    unittest.main()
