"""Minimal live smoke test for OpenAI connectivity and credentials."""

from ingest.logging_utils import configure_logging, get_logger
from openai_utils import get_openai_client


SMOKE_TEST_MODEL = "gpt-5-mini"
SMOKE_TEST_TIMEOUT_SECONDS = 240
logger = get_logger(__name__)


def main() -> None:
    """Run one live chat completion and log the one-word response."""
    effective_log_level = configure_logging()
    logger.debug(
        "Starting openai_live_smoke_test with LOG_LEVEL=%s", effective_log_level
    )
    logger.info(
        "Running smoke test model=%s timeout_seconds=%d",
        SMOKE_TEST_MODEL,
        SMOKE_TEST_TIMEOUT_SECONDS,
    )
    client = get_openai_client()
    response = client.chat.completions.create(
        model=SMOKE_TEST_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Answer in exactly one word.",
            },
            {
                "role": "user",
                "content": "What is the capital of France?",
            },
        ],
        timeout=SMOKE_TEST_TIMEOUT_SECONDS,
    )

    text = (response.choices[0].message.content or "").strip()
    logger.info("Smoke test response=%s", text)


if __name__ == "__main__":
    main()
