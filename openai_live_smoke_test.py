"""Minimal live smoke test for OpenAI connectivity and credentials."""

from openai_utils import get_openai_client


SMOKE_TEST_MODEL = "gpt-5-mini"
SMOKE_TEST_TIMEOUT_SECONDS = 240


def main() -> None:
    """Run one live chat completion and print raw text output."""
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
    print(text)


if __name__ == "__main__":
    main()
