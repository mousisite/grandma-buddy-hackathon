---
name: meta-model-api
description: How to call Meta's Model API correctly in Grandma Buddy - Muse Spark chat, function calling, structured outputs, image input, and Muse Voice Transcribe speech-to-text. Load before writing or changing app/meta_client.py or any code that talks to api.meta.ai.
---

# Meta Model API cheat sheet

Checked against Meta's docs in October 2026. If a call fails with HTTP 400, re-read the docs page listed at the bottom before guessing.

All calls to Meta live in `app/meta_client.py`. Nothing else in the app talks to `api.meta.ai`, and the browser never does.

## Basics

- Base URL: `https://api.meta.ai/v1`
- Auth header: `Authorization: Bearer <key>`. The app gets the key from `MODEL_API_KEY` through `app/config.py`. Never hard-code it, log it, or send it to the browser.
- Muse Code (the coding agent) uses a different variable, `META_API_KEY`. The app does not use that one.
- Models for this app:
  - `muse-spark-1.3`: conversation, reasoning, tools, structured outputs, image input. Standard mode, so Meta does not train on the content.
  - `muse-voice-transcribe-1.0`: speech-to-text.
  - Never use a `-contributor` model here. Contributor mode lets Meta train on the content, and this app handles health information.
  - Spark 1.3 does not fully support audio input, so speech goes through Voice Transcribe. (`muse-spark-1.2` accepts audio input, which is the fallback only if Grandma's language is not supported by Voice Transcribe.)
- Meta has no text-to-speech model. The browser reads replies aloud with `speechSynthesis`.

## Chat Completions (official `openai` Python package)

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.meta.ai/v1",
    api_key=settings.model_api_key,
    timeout=60,
    max_retries=2,
)

resp = client.chat.completions.create(
    model=settings.chat_model,  # "muse-spark-1.3"
    messages=[
        {"role": "developer", "content": COMPANION_PROMPT},
        {"role": "user", "content": "Good morning!"},
    ],
    reasoning_effort="low",
    max_completion_tokens=600,
)
reply = resp.choices[0].message.content
```

Rules:

- Roles: `developer` (preferred for system prompts; `system` is treated the same), `user`, `assistant`, `tool`.
- `reasoning_effort`: `"minimal"`, `"low"`, `"medium"`, `"high"`, or `"xhigh"`. `"none"` returns HTTP 400. Use `"low"` for conversation and `"medium"` for scam checks and doctor notes.
- Use `max_completion_tokens`. (`max_tokens` is still accepted; `max_output_tokens` is rejected on this endpoint.)
- These return HTTP 400 on Chat Completions: `stop`, `n` greater than 1, `verbosity`, `logit_bias`, `prediction`, `web_search_options`, `modalities`, `audio`, `logprobs: true`, and `text.format` (that belongs to the Responses API).
- Leave `temperature` at the default. Never set both `temperature` and `top_p`.
- The API keeps no state. Send the conversation every time, trimmed to the prompt plus the last 20 or so messages.
- `tool_choice`: only `"auto"` (the default) is supported. `"none"`, `"required"`, and named functions return HTTP 400 ("only `auto` is supported for `tool_choice`", seen October 27, 2026). So never send it. To get words instead of another tool call, add a short `developer` message at the end ("Now answer her in a few warm words. Don't call any tools.") and keep `tools` as they were; Meta accepts that after `tool` messages too.
- Message order is validated strictly. An assistant message with `tool_calls` must be followed by one `tool` message per call, each with the matching `tool_call_id`, before the next assistant turn. Replay the whole assistant message, not just its text, or you get HTTP 400.
- Non-streaming calls have a time limit (HTTP 504). If that happens, lower the reasoning effort or use `stream=True`.

## Function calling (companion tools)

```python
import json

TOOLS = [{
    "type": "function",
    "function": {
        "name": "log_mood",
        "description": "Save how Grandma says she feels right now.",
        "parameters": {
            "type": "object",
            "properties": {
                "mood": {"type": "string", "enum": ["great", "good", "okay", "low", "very_low"]},
                "note": {"type": "string"},
            },
            "required": ["mood", "note"],
            "additionalProperties": False,
        },
    },
}]

for _ in range(3):  # at most 3 tool rounds
    resp = client.chat.completions.create(
        model=settings.chat_model, messages=messages, tools=TOOLS, reasoning_effort="low",
    )
    msg = resp.choices[0].message
    if not msg.tool_calls:
        break
    messages.append(msg.model_dump(exclude_none=True))  # the whole assistant message
    for call in msg.tool_calls:
        result = run_tool(call.function.name, json.loads(call.function.arguments or "{}"))
        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
else:
    # still asking for tools after 3 rounds: one last call that asks for words
    # (no tool_choice="none": Meta rejects it with HTTP 400)
    resp = client.chat.completions.create(
        model=settings.chat_model,
        messages=messages + [{"role": "developer", "content": "Now answer her in a few warm words. Don't call any tools."}],
        tools=TOOLS,
        reasoning_effort="low",
    )
```

- Tool handlers live in `app/tools.py`, validate their arguments, and return small JSON results.
- Tools may only touch our own database or tell the screen to show something. No tool sends messages, calls people, or contacts the internet.

## Structured outputs (scam check, doctor notes)

```python
resp = client.chat.completions.create(
    model=settings.chat_model,
    messages=messages,
    reasoning_effort="medium",
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "scam_result", "schema": SCAM_SCHEMA, "strict": True},
    },
)
data = json.loads(resp.choices[0].message.content)
```

- On Chat Completions, structured output goes in `response_format`. The `json_schema` shape above follows the OpenAI format that Meta says it is compatible with. If Meta rejects it, check the structured outputs page in Meta's docs.
- In strict schemas, list every property in `required`, set `"additionalProperties": false`, and use enums for levels and verdicts.
- Always validate the parsed result in Python. If it fails, retry once. If it fails again, show a friendly "Sorry, please try again" message. For the scam checker, the fallback advice is "Not sure. Don't click anything, and call {family} before you reply or pay."

## Image input (scam photos, pill bottle labels)

Muse Spark accepts images. Send OpenAI-style content parts with a base64 data URL:

```python
{"role": "user", "content": [
    {"type": "text", "text": "Is this message a scam?"},
    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
]}
```

- Confirm the exact format on Meta's image understanding docs page before relying on it.
- Shrink photos in the browser with a `<canvas>` (about 1600 px on the long side, JPEG) before uploading, so no extra Python package is needed.

## Speech-to-text: Muse Voice Transcribe (file upload)

- `POST https://api.meta.ai/v1/asr/transcribe`
- Headers: `Authorization: Bearer <key>` and `Accept: application/json`
- Body: `multipart/form-data` with two parts:
  - `request`: JSON settings, content type `application/json`
  - `audio`: the WAV file, content type `audio/wav`
- Audio must be WAV, mono, 16-bit integer PCM, at 16 kHz or 24 kHz. Up to 10 minutes and 32 MB.
- Response: `{"sessionId": "...", "transcript": "...", "audioDurationMs": 8240, "turns": []}`. Use `transcript`.

```python
import json
import requests

def transcribe(wav_bytes: bytes, keywords: list[str]) -> str:
    settings_json = {
        "model": settings.transcribe_model,     # "muse-voice-transcribe-1.0"
        "audioEncoding": "WAV",
        "mode": "PUSH_TO_TALK",
        "languageBias": [settings.language],   # a hint, e.g. ["English"]
        "keywords": keywords,                  # medication and family names; keep it short
    }
    resp = requests.post(
        "https://api.meta.ai/v1/asr/transcribe",
        headers={"Authorization": f"Bearer {settings.model_api_key}", "Accept": "application/json"},
        files={
            "request": (None, json.dumps(settings_json), "application/json"),
            "audio": ("speech.wav", wav_bytes, "audio/wav"),
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("transcript", "").strip()
```

- Errors: 400 (not a supported WAV, longer than 10 minutes, or not multipart), 406 (unsupported `Accept`), 413 (over 32 MB), 429 (too many at once; wait and retry with backoff), 500 (failed; show a friendly "please try again").
- Supported languages (25): Arabic, Bengali, Dutch, English, French, German, Hebrew, Hindi, Indonesian, Italian, Japanese, Kannada, Korean, Malay, Mandarin Chinese, Marathi, Polish, Portuguese, Spanish, Tagalog, Tamil, Telugu, Thai, Turkish, Vietnamese.
- `languageBias` and `keywords` are hints. Recognition is biased toward them, not forced.
- A realtime WebSocket endpoint (`wss://api.meta.ai/v1/asr/realtime`) exists for live streaming. Tap-to-talk does not need it.

## Browser side: making the WAV (`static/recorder.js`)

- `navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}})`
- Capture Float32 samples with an `AudioWorklet` (fall back to `ScriptProcessorNode` if needed), downsample to 16000 Hz, convert to Int16, and write a standard 44-byte RIFF/WAVE header (PCM format 1, 1 channel, 16000 Hz, 16 bits). Post it as a `Blob` with type `audio/wav`.
- The microphone only works on `http://localhost` or HTTPS.

## Costs (standard mode)

- Muse Spark: about $1.25 per million input tokens and $4.25 per million output tokens.
- Voice Transcribe: $0.18 per hour of audio.
- Keep prompts short, trim history, and use low reasoning effort for small talk.

## Testing

- Tests never call the real API. In `tests/conftest.py`, replace the functions in `app.meta_client` with fakes that return fixed replies, tool calls, and JSON results.
- `scripts/check_meta.py` is the one live check that the key and billing work. It is run by hand, never by tests.

## Docs to check when unsure

- Chat Completions: https://dev.meta.ai/docs/protocols/chat-completions
- Models: https://dev.meta.ai/docs/models
- Speech to text: https://dev.meta.ai/docs/speech-to-text
- Transcribe API reference: https://dev.meta.ai/docs/api-reference/voice/transcribe
