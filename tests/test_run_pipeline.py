"""Tests for run_pipeline profile parsing and invocation flow."""

import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from project_paths import INGEST_DIR


if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

import run_pipeline
from pipeline_params import PASS_01_5_SCRIPT, PROFILE_DEFAULT, PROFILE_PREVIEW


class RunPipelineTests(unittest.TestCase):
    """Ensure run_pipeline enforces and forwards profile correctly."""

    def test_uses_full_as_default_profile(self) -> None:
        """Default invocation should run all passes with full profile."""
        with (
            patch.object(sys, "argv", ["run_pipeline.py"]),
            patch.object(run_pipeline, "run_script") as run_mock,
        ):
            run_pipeline.main()

        self.assertEqual(run_mock.call_count, 3)
        self.assertEqual(run_mock.call_args_list[0].args[1], PROFILE_DEFAULT)
        self.assertEqual(run_mock.call_args_list[1].args[1], PROFILE_DEFAULT)
        self.assertEqual(run_mock.call_args_list[2].args[1], PROFILE_DEFAULT)
        self.assertEqual(run_mock.call_args_list[1].args[0], PASS_01_5_SCRIPT)

    def test_uses_preview_profile(self) -> None:
        """Preview argument should be passed to all pass scripts."""
        with (
            patch.object(sys, "argv", ["run_pipeline.py", PROFILE_PREVIEW]),
            patch.object(run_pipeline, "run_script") as run_mock,
        ):
            run_pipeline.main()

        self.assertEqual(run_mock.call_count, 3)
        self.assertEqual(run_mock.call_args_list[0].args[1], PROFILE_PREVIEW)
        self.assertEqual(run_mock.call_args_list[1].args[1], PROFILE_PREVIEW)
        self.assertEqual(run_mock.call_args_list[2].args[1], PROFILE_PREVIEW)
        self.assertEqual(run_mock.call_args_list[1].args[0], PASS_01_5_SCRIPT)

    def test_rejects_invalid_profile(self) -> None:
        """Unknown profile should exit with argparse-like status code 2."""
        with (
            patch.object(sys, "argv", ["run_pipeline.py", "invalid"]),
            redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as context:
                run_pipeline.main()
        self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
