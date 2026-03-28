from openai_utils import get_openai_client


def main() -> None:
    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-5-mini",
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
        timeout=240,
    )

    text = (response.choices[0].message.content or "").strip()
    print(text)


if __name__ == "__main__":
    main()
