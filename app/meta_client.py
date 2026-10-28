# app/meta_client.py
# Every call to Meta's Model API lives in this file. Nothing else in the app
# talks to api.meta.ai, and the browser never does, so the API key stays here.
# Never print or log the API key.

import json
import time

import openai
import requests
from openai import OpenAI

from app.config import get_settings

BASE_URL = "https://api.meta.ai/v1"
TIMEOUT_SECONDS = 60
RETRIES = 3  # extra tries when Meta says it is too busy (HTTP 429)


class MetaError(Exception):
    """Meta's API answered with a problem. The screen shows a kind message instead."""


def _client() -> OpenAI:
    """The connection for chat: the official openai package pointed at Meta.

    Tests replace this function so they can never reach the real API.
    The package's own retries are off (max_retries=0): this file does its
    own waiting and retrying, so she never waits through both.
    """
    return OpenAI(
        base_url=BASE_URL,
        api_key=get_settings().model_api_key,
        timeout=TIMEOUT_SECONDS,
        max_retries=0,
    )


def chat(messages: list[dict], tools: list[dict] | None = None, tool_choice: str | None = None,
         reasoning: str = "low", max_tokens: int = 1200) -> dict:
    """Ask Muse Spark for the next reply.

    Returns a plain dictionary:
      content     her reply text (may be empty when it asks for tools)
      tool_calls  [{"id", "name", "arguments"}] the tools it wants to run
      message     the whole assistant message, to send back on the next turn
    """
    settings = get_settings()
    request = {
        "model": settings.chat_model,  # muse-spark-1.3, a standard model (never -contributor)
        "messages": messages,
        "reasoning_effort": reasoning,  # "low" keeps everyday talk quick
        "max_completion_tokens": max_tokens,
    }
    if tools:
        request["tools"] = tools
    if tool_choice:
        request["tool_choice"] = tool_choice

    if not settings.model_api_key:
        raise MetaError("no API key is set up in .env")
    client = _client()
    for attempt in range(RETRIES + 1):
        try:
            response = client.chat.completions.create(**request)
            break
        except openai.RateLimitError:
            if attempt == RETRIES:
                raise MetaError("chat stayed busy (HTTP 429)")
            time.sleep(2**attempt)  # too busy: wait 1, then 2, then 4 seconds
        except openai.APIStatusError as problem:
            raise MetaError(f"chat failed with HTTP {problem.status_code}")
        except (openai.APITimeoutError, openai.APIConnectionError) as problem:
            raise MetaError(f"chat failed: {type(problem).__name__}")

    message = response.choices[0].message
    calls = [
        {"id": call.id, "name": call.function.name, "arguments": call.function.arguments or "{}"}
        for call in (message.tool_calls or [])
    ]
    return {"content": message.content, "tool_calls": calls, "message": message.model_dump(exclude_none=True)}


def transcribe(wav_bytes: bytes, keywords: list[str]) -> str:
    """Turn a recording (16 kHz mono 16-bit WAV) into text with Muse Voice Transcribe.

    keywords are names she is likely to say (family, doctor, pills), sent as
    hints so speech-to-text spells them right.
    """
    settings = get_settings()
    request_settings = {
        "model": settings.transcribe_model,
        "audioEncoding": "WAV",
        "mode": "PUSH_TO_TALK",
        "languageBias": [settings.language],
    }
    if keywords:
        request_settings["keywords"] = keywords

    for attempt in range(RETRIES + 1):
        response = requests.post(
            f"{BASE_URL}/asr/transcribe",
            headers={
                "Authorization": f"Bearer {settings.model_api_key}",
                "Accept": "application/json",
            },
            # Two form parts: the settings as JSON, and the sound file.
            files={
                "request": (None, json.dumps(request_settings), "application/json"),
                "audio": ("speech.wav", wav_bytes, "audio/wav"),
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 429 or attempt == RETRIES:
            break
        time.sleep(2**attempt)  # too busy: wait 1, then 2, then 4 seconds

    if response.status_code != 200:
        raise MetaError(f"transcribe failed with HTTP {response.status_code}")
    return response.json().get("transcript", "").strip()
