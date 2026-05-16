import os
from openai import OpenAI

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def generate_reply(tweet_text: str) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=256,
        messages=[
            {
                "role": "system",
                "content": (
                    "You help write short, genuine, engaging replies to tweets. "
                    "Always reply in the same language as the tweet. "
                    "Write in first person, no hashtags, no emoji unless the original has them. "
                    "One or two sentences maximum."
                ),
            },
            {
                "role": "user",
                "content": f"Write a reply to this tweet:\n\n{tweet_text}",
            },
        ],
    )
    return response.choices[0].message.content.strip()


def generate_replies(tweets: list[dict]) -> list[str]:
    return [generate_reply(t["text"]) for t in tweets]
