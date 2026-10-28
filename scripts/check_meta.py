# scripts/check_meta.py
# One tiny real call to Muse Spark. It proves the API key and billing work.
#
# Run it BY HAND only: .venv\Scripts\python scripts\check_meta.py
# Never run it from tests. Tests must never call the real API.
#
# Before running: copy .env.example to .env and put your real key in .env.

import sys
from pathlib import Path

# Let this script import app/ no matter where it is run from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI  # noqa: E402

from app.config import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()

    if not settings.model_api_key or settings.model_api_key == "paste-your-key-here":
        print("No API key found.")
        print("Copy .env.example to .env and put your real Meta Model API key in it,")
        print("then run this script again.")
        return 1

    client = OpenAI(
        base_url="https://api.meta.ai/v1",
        api_key=[redacted],
        timeout=60,
        max_retries=2,
    )
    response = client.chat.completions.create(
        model=settings.chat_model,
        messages=[{"role": "user", "content": 'Say "Meta API key works!"'}],
        reasoning_effort="low",
        max_completion_tokens=50,
    )
    reply = (response.choices[0].message.content or "").strip()
    print("Success! Muse Spark answered:")
    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
