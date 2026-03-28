import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
INGEST_DIR = ROOT_DIR / "ingest"
if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import run_pipeline


class RunPipelineTests(unittest.TestCase):
    def test_uses_full_as_default_profile(self) -> None:
        with (
            patch.object(sys, "argv", ["run_pipeline.py"]),
            patch.object(run_pipeline, "run_script") as run_mock,
        ):
            run_pipeline.main()

        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(run_mock.call_args_list[0].args[1], "full")
        self.assertEqual(run_mock.call_args_list[1].args[1], "full")

    def test_uses_preview_profile(self) -> None:
        with (
            patch.object(sys, "argv", ["run_pipeline.py", "preview"]),
            patch.object(run_pipeline, "run_script") as run_mock,
        ):
            run_pipeline.main()

        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(run_mock.call_args_list[0].args[1], "preview")
        self.assertEqual(run_mock.call_args_list[1].args[1], "preview")

    def test_rejects_invalid_profile(self) -> None:
        with (
            patch.object(sys, "argv", ["run_pipeline.py", "invalid"]),
            redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as context:
                run_pipeline.main()
        self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
