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
- `reasoning_effort`: `"minimal"`, `"low"`, `"medium"`, `"high"`, or `"xhigh"`. `"none"` returns HTTP 400. Use `"minimal"` for conversation and `"medium"` for scam checks and doctor notes. Measured Nov 1 on the real companion prompt (3.5k tokens): `"low"` thinks for 850 to 1200 hidden tokens a round (5 to 6 seconds), `"minimal"` for 100 to 500 (2 to 3.5 seconds), with the same words and the same tool calls. Prompt length barely matters next to that.
- Use `max_completion_tokens`. (`max_tokens` is still accepted; `max_output_tokens` is rejected on this endpoint.)
- These return HTTP 400 on Chat Completions: `stop`, `n` greater than 1, `verbosity`, `logit_bias`, `prediction`, `web_search_options`, `modalities`, `audio`, `logprobs: true`, and `text.format` (that belongs to the Responses API).
- Leave `temperature` at the default. Never set both `temperature` and `top_p`.
- The API keeps no state. Send the conversation every time, trimmed to the prompt plus the last 20 or so messages.
- `tool_choice`: only `"auto"` (the default) is supported. `"none"`, `"required"`, and named functions return HTTP 400 ("only `auto` is supported for `tool_choice`", seen October 27, 2026). So never send it. To get words instead of another tool call, add a short `developer` message at the end ("Now answer her in a few warm words. Don't call any tools.") and keep `tools` as they were; Meta accepts that after `tool` messages too.
- Message order is validated strictly. An assistant message with `tool_calls` must be followed by one `tool` message per call, each with the matching `tool_call_id`, before the next assistant turn. Replay the whole assistant message, not just its text, or you get HTTP 400.
- Non-streaming calls have a time limit (HTTP 504). If that happens, lower the reasoning effort or use `stream=True`.
- `stream=True` works (checked Nov 1), but Muse Spark sends a message's words as ONE chunk after its hidden thinking (then a chunk per piece of each tool call), so nothing arrives any earlier than without streaming. The app doesn't stream from Meta; it streams its own events to the page instead (a fixed bridge line while a slow tool runs).
- A reply that calls a tool needs a second round for the words. Tried Nov 1 and dropped: asking for the words in a second request at the same time (the developer message above, no tools run). Asked for words alone, Muse Spark sometimes narrates instead of answering ("I'll sit with her in it", "I'll get those call options ready"), about one reply in four, so the round after the tool, with the tool's answer in view, is the only reliable source of words.
- Make one `OpenAI()` client and reuse it (`meta_client._clients`): each new client opens a new connection to Meta, a few tenths of a second per round.

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
- Tools may only touch our own database, tell the screen to show something, or (`look_up_today` only) ask Meta's own web search about one of three topics our code words (weather, local news, sports). No tool sends messages, calls people, or visits a website: our code never fetches a web page.

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

## Image input (scam photos, letters and bills for Read it to me, pill bottle labels)

Muse Spark accepts images. Send OpenAI-style content parts with a base64 data URL:

```python
{"role": "user", "content": [
    {"type": "text", "text": "Is this message a scam?"},
    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
]}
```

- Confirm the exact format on Meta's image understanding docs page before relying on it.
- Shrink photos in the browser with a `<canvas>` (about 1600 px on the long side, JPEG) before uploading, so no extra Python package is needed.
- A pill bottle label (`app/labels.py`): a strict form `{readable, name, label}` with low reasoning; the real check (`scripts/check_label.py`) read a drawn label exactly as printed, in its own capitals. The words only fill in the form, and a family member checks each one before it is saved.

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
- A realtime WebSocket endpoint (`wss://api.meta.ai/v1/asr/realtime`) streams live: see "Live speech-to-text" below (hands-free talking uses it; tap-to-talk does not).

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

## Finding things in a photo: SAM 3.1 (`meta_client.segment`)

Checked against Meta's SAM docs on October 29, 2026, and with one real call (`scripts/check_find.py`).

```python
response = client.responses.create(
    model=settings.sam_model,  # "sam-3.1"
    input=[{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": "glasses"},                      # ONE short noun phrase
        {"type": "input_image", "image_url": "data:image/jpeg;base64,..."},
    ]}],
    metadata={"include_confidence": "true", "mask_encoding": "one_bit"},  # values are strings
    store=False,  # Meta doesn't keep her photo; big inline photos can also 413 when stored
)
line = response.output_text  # "" when nothing matched
```

- The answer is one line: `<0f>0<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..;c=0.91|><|mask;x=0;y=0;data=H,W,!…|>,3<|box…|>…`. Each match is an id, a box, and a mask. Boxes are in the photo's own pixels, `x2` and `y2` included; `w,h` is the photo's size; `c` is the confidence (only with `include_confidence`).
- Some everyday phrases find nothing: "pill bottle" matched nothing in a clear photo, while "medicine bottle" (0.82) and "bottle" (0.96) found it. Map her words to SAM's in `finder.SAM_WORDS`, and try a new phrase with the real model before trusting it.
- No threshold or "max objects" input exists: every match comes back, so filter by `c` in our code (`finder.best_match`, at least 0.5).
- The mask's base85 encoding isn't documented, and Meta's `meta-sam-parser` has no published license, so we don't use masks: the page draws a halo around the box.
- $0.0025 per image. Retries on 429 like chat.

## Live speech-to-text: realtime WebSocket (`meta_client.open_listening`)

Checked against Meta's realtime docs and with real calls (`scripts/check_realtime.py`, also `--relay` through our `/api/listen`), October 31, 2026.

```python
socket = await websockets.asyncio.client.connect("wss://api.meta.ai/v1/asr/realtime", open_timeout=10)
await socket.send(json.dumps({
    "authorization": {"accessToken": f"Bearer {key}"},   # in the first message: Meta reads no HTTP header here
    "audioEncoding": "PCM_16KHZ",                        # or PCM_24KHZ (native); no default
    "model": "muse-voice-transcribe-1.0",
    "mode": "ENDPOINTING",                               # it hears where each turn starts and ends
    "partialMode": "CUMULATIVE",                         # each live update is the whole turn so far
    "emitAudioProgress": False,
    "languageBias": ["English"], "keywords": [...],
}))
answer = json.loads(await socket.recv())  # {"sessionId": ...}: the ONLY message with no "type"
```

- Within 10 seconds of opening. An error event also carries a `sessionId` (empty), so "ready" means no `type` and a real `sessionId`.
- Then binary frames of raw 16-bit little-endian mono PCM, about real time (80 ms each works). Meta needs sound all the time: send silence (zeros), not nothing, while Buddy speaks, or it closes the stream. Never more than 5 seconds ahead.
- Events (JSON text): `speechStart` (`turnId`), `transcript` (`transcript`, `final`; partials, no `turnId`), `speechEnd`, `speechComplete` (`turnId`, `transcript`: the turn's final words), `error` (just before a close). Many turns per session. `{"type": "endStream"}` ends the session (Meta closes with 1000). Close codes: 1008 bad request or pacing, 1011 server (or 60 minutes), 1013 rate limited.
- Real timing: connecting and the handshake took about 4 seconds (open it when the talk screen opens, before she speaks); live words every 0.3 seconds; each turn's `speechComplete` about 1 second after she stopped talking.
- The key would be exposed in a browser, so the page talks to our relay and the relay to Meta. $0.18 per hour of sound.

## Painting a picture: Muse Image (`meta_client.paint`)

Checked with real calls (`scripts/seed_demo.py`, `scripts/check_messages.py`), October 29 to 31, 2026. The OpenAI Images format, `POST /v1/images/generations`:

```python
response = client.images.generate(
    model=settings.image_model,  # muse-image-1.0, a standard model
    prompt=prompt,               # a fixed style (memories.STYLE) plus the checked scene
    n=1,
    size=PICTURE_SIZE,           # "1536x1024", a landscape 3:2 page picture
    extra_body={"tool_enablement": NO_LOOKUPS},  # Meta's extra: no image or web search while painting
    timeout=PAINT_TIMEOUT_SECONDS,  # 180 seconds: painting takes longer than talking
)
picture = base64.b64decode(response.data[0].b64_json)  # WebP bytes by default
```

- About $0.01 per picture: paint once per Memory book page and once per postcard a day, never in a loop. 429 and 503 are worth a retry with a wait; anything else is a `MetaError`.
- Plain code checks what came back is a picture file (`memories.PICTURE_KINDS`) before saving it, and every scene the AI wrote before painting it (no names, numbers, health words, or advice).
- The prompt always asks for small faceless figures seen from behind, so no real person's likeness is ever made.

## Web search grounding: Responses API `web_search` (`meta_client.search`)

Checked against Meta's search-grounding docs and with real calls (`scripts/check_briefing.py`), October 30, 2026. Not available on Chat Completions (`web_search_options` is a 400 there).

```python
response = client.responses.create(
    model=settings.chat_model,                     # muse-spark-1.3
    instructions=instructions,                     # this request only
    input=question,                                # our code writes it (app/briefing.py)
    tools=[{"type": "web_search", "search_context_size": "low",
            "user_location": {"type": "approximate", "country": "US", "city": "Portland", "region": "Oregon"}}],
    include=["web_search_call.action.sources"],    # the pages each search found
    reasoning={"effort": "low"},
    max_tool_calls=2,                              # caps built-in calls like web_search
    max_output_tokens=1500,                        # reasoning + words
    store=False,
)
```

- Before searching, the model writes short messages of its own ("I'll check today's web sources…"). `response.output_text` glues ALL message texts together with no spaces, so use the LAST `message` item's `output_text` parts as the answer.
- The answer's `url_citation` annotations (`url`, `title`, `start_index`, `end_index`) sit on that last message. Sometimes there are none: then the `web_search_call` items' `action.sources` (`{"type": "url", "url"}`) list the pages found (20+ is normal); name the first few sites only.
- A `web_search_call` item with `action.type == "url"` is the model opening a page. No search call at all means it answered from memory: no good for today's weather, so we don't use it.
- One set of instructions covering several topics made it answer all of them at once: give each question only its own rules.
- `tool_choice` only "auto": the model decides whether to search. `$0.0025` per search plus tokens. No per-request domain filters on Responses.
- The scam lookup (`app/scam.py` `searched`) passes `town=""`, so no `user_location` is sent (a number is the same everywhere): only the phone number or web address goes in the question, with `prompts.SCAM_LOOKUP` as the instructions, and plain code reads only the first word of the answer (REPORTED, CLEAR, UNKNOWN). Both uses share the day's budget of 30 searches (`briefing.take_search`).

## Docs to check when unsure

- Chat Completions: https://dev.meta.ai/docs/protocols/chat-completions
- Models: https://dev.meta.ai/docs/models
- Speech to text: https://dev.meta.ai/docs/speech-to-text
- Transcribe API reference: https://dev.meta.ai/docs/api-reference/voice/transcribe
- SAM 3.1: https://dev.meta.ai/docs/sam/reading-segmentation and https://dev.meta.ai/docs/api-reference/responses/create-response
- Web search: https://dev.meta.ai/docs/search-grounding and https://dev.meta.ai/docs/protocols/responses
