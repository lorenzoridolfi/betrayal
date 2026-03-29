"""Tests for live smoke test wiring without real network calls."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import openai_live_smoke_test


class OpenAILiveSmokeTestTests(unittest.TestCase):
    """Validate smoke test uses shared OpenAI credential/client path."""

    def test_main_uses_openai_utils_client_and_expected_request(self) -> None:
        """Smoke test should call get_openai_client and execute one completion."""
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Paris"))]
        )
        create_mock = Mock(return_value=fake_response)
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )

        with (
            patch.object(
                openai_live_smoke_test, "configure_logging", return_value="DEBUG"
            ),
            patch.object(
                openai_live_smoke_test, "get_openai_client", return_value=fake_client
            ) as client_mock,
            patch.object(openai_live_smoke_test, "logger") as logger_mock,
        ):
            openai_live_smoke_test.main()

        client_mock.assert_called_once_with()
        create_mock.assert_called_once()
        self.assertEqual(
            create_mock.call_args.kwargs["model"],
            openai_live_smoke_test.SMOKE_TEST_MODEL,
        )
        self.assertEqual(
            create_mock.call_args.kwargs["timeout"],
            openai_live_smoke_test.SMOKE_TEST_TIMEOUT_SECONDS,
        )
        logger_mock.info.assert_any_call("Smoke test response=%s", "Paris")

    def test_main_propagates_client_creation_failure(self) -> None:
        """Smoke test should not hide credential/client initialization errors."""
        with (
            patch.object(
                openai_live_smoke_test, "configure_logging", return_value="DEBUG"
            ),
            patch.object(
                openai_live_smoke_test,
                "get_openai_client",
                side_effect=SystemExit(1),
            ),
            self.assertRaises(SystemExit),
        ):
            openai_live_smoke_test.main()


if __name__ == "__main__":
    unittest.main()
