"""Import tests for summarize program local dependencies."""

import importlib
import unittest


class SummarizeImportsTests(unittest.TestCase):
    """Verify summarize module imports resolve correctly in test runtime."""

    def test_import_summarize_module(self) -> None:
        """summarize_betrayal_json should import with local dependencies available."""
        module = importlib.import_module("summarize_betrayal_json")
        self.assertTrue(callable(getattr(module, "main", None)))

    def test_import_eta_estimator_module(self) -> None:
        """eta_estimator should import and expose EtaEstimator class."""
        module = importlib.import_module("eta_estimator")
        self.assertTrue(callable(getattr(module, "EtaEstimator", None)))


if __name__ == "__main__":
    unittest.main()
