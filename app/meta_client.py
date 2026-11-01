# app/meta_client.py
# Every call to Meta's Model API lives in this file. Nothing else in the app
# talks to api.meta.ai, and the browser never does, so the API key stays here.
# Never print or log the API key.

import asyncio
import base64
import json
import time

import openai
import requests
import websockets
from openai import OpenAI
from websockets.asyncio.client import connect as ws_connect  # tests replace this

from app.config import get_settings

BASE_URL = "https://api.meta.ai/v1"
REALTIME_URL = "wss://api.meta.ai/v1/asr/realtime"  # live speech-to-text (hands-free talking)
TIMEOUT_SECONDS = 60
RETRIES = 3  # extra tries when Meta says it is too busy (HTTP 429)
PAINT_TIMEOUT_SECONDS = 180  # painting takes longer than talking
PICTURE_SIZE = "1536x1024"  # a landscape page picture (3:2)
# Muse Image may look up reference pictures on the web. Never for her
# memories: her story stays in the request, and it never copies a real
# person's likeness.
NO_LOOKUPS = {"enable_image_search": False, "enable_web_search": False, "enable_shell": False}


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


def chat(messages: list[dict], tools: list[dict] | None = None,
         reasoning: str = "low", max_tokens: int = 3000) -> dict:
    """Ask Muse Spark for the next reply.

    There is no tool_choice: Meta only supports "auto" (the default) and
    answers "none" or "required" with HTTP 400. To get words instead of a
    tool call, ask for words in the messages (see companion.words_only).

    max_tokens counts the model's hidden thinking too. At 1200, longer talks
    sometimes used it all on thinking and came back with no words, so it
    has room to spare; the prompt keeps the spoken reply itself short.

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

    response = _create(request)
    message = response.choices[0].message
    calls = [
        {"id": call.id, "name": call.function.name, "arguments": call.function.arguments or "{}"}
        for call in (message.tool_calls or [])
    ]
    return {"content": message.content, "tool_calls": calls, "message": message.model_dump(exclude_none=True)}


def structured(messages: list[dict], name: str, schema: dict, reasoning: str = "medium",
               max_tokens: int = 3000) -> dict:
    """Ask Muse Spark for an answer that fills in a form (a strict JSON schema,
    "structured outputs"), like the scam checker's verdict. Returns it as a
    dictionary. If the answer isn't valid JSON, asks once more, then gives up
    with MetaError. The caller still checks every field.

    A message's content can be words, or a list of parts with a photo:
      [{"type": "text", "text": "..."},
       {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}]
    """
    request = {
        "model": get_settings().chat_model,  # muse-spark-1.3, standard (never -contributor)
        "messages": messages,
        "reasoning_effort": reasoning,  # "medium": a scam check is worth a little more thought
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
    }
    for _ in range(2):
        content = _create(request).choices[0].message.content or ""
        try:
            answer = json.loads(content)
        except ValueError:
            continue
        if isinstance(answer, dict):
            return answer
    raise MetaError(f"{name} did not come back as a filled-in form, twice")


def _create(request: dict):
    """Send one Chat Completions request, waiting and retrying when Meta is busy."""
    if not get_settings().model_api_key:
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

    if response.choices[0].finish_reason == "length":
        print("A reply ran out of room (max_completion_tokens).")  # never her words
    return response


def paint(prompt: str) -> bytes:
    """Paint one picture with Muse Image (POST /v1/images/generations, the
    OpenAI Images format). Returns the picture's bytes (WebP by default).
    Costs $0.01 per picture, so it is called once per Memory book page."""
    settings = get_settings()
    if not settings.model_api_key:
        raise MetaError("no API key is set up in .env")
    client = _client()
    for attempt in range(RETRIES + 1):
        try:
            response = client.images.generate(
                model=settings.image_model,  # muse-image-1.0, a standard model
                prompt=prompt,
                n=1,
                size=PICTURE_SIZE,
                extra_body={"tool_enablement": NO_LOOKUPS},  # a Meta extra, so it goes in extra_body
                timeout=PAINT_TIMEOUT_SECONDS,
            )
            break
        except (openai.RateLimitError, openai.InternalServerError) as problem:
            # 429 (too busy) and 503 (painting failed this time) are worth
            # another try; any other server problem is not.
            if attempt == RETRIES or getattr(problem, "status_code", 0) not in (429, 503):
                raise MetaError(f"paint failed with HTTP {problem.status_code}")
            time.sleep(2**attempt)  # wait 1, then 2, then 4 seconds
        except openai.APIStatusError as problem:
            raise MetaError(f"paint failed with HTTP {problem.status_code}")
        except (openai.APITimeoutError, openai.APIConnectionError) as problem:
            raise MetaError(f"paint failed: {type(problem).__name__}")

    picture = response.data[0].b64_json if response.data else None
    if not picture:
        raise MetaError("no picture came back")
    return base64.b64decode(picture)


def segment(image: str, phrase: str) -> str:
    """Find a thing in a photo with SAM 3.1 (POST /v1/responses).

    image is a data URL ("data:image/jpeg;base64,..."), and phrase is one
    short noun phrase, like "glasses". Returns SAM's one-line answer: a box
    (and a mask) for every match, or "" when nothing matches. app/finder.py
    reads it. Costs $0.0025 per photo.

    store=False: Meta doesn't keep her photo. (Big inline photos can also
    fail with HTTP 413 when stored.)
    """
    settings = get_settings()
    if not settings.model_api_key:
        raise MetaError("no API key is set up in .env")
    request = {
        "model": settings.sam_model,  # sam-3.1
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": phrase},
            {"type": "input_image", "image_url": image},
        ]}],
        # Meta's settings are words, even "true". one_bit masks are the small kind.
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        "store": False,
    }
    return (_respond(request, "SAM").output_text or "").strip()


def _respond(request: dict, what: str):
    """Send one Responses API request (SAM, web search), waiting and
    retrying when Meta is busy. `what` names it in a failure."""
    client = _client()
    for attempt in range(RETRIES + 1):
        try:
            return client.responses.create(**request)
        except openai.RateLimitError:
            if attempt == RETRIES:
                raise MetaError(f"{what} stayed busy (HTTP 429)")
            time.sleep(2**attempt)  # too busy: wait 1, then 2, then 4 seconds
        except openai.APIStatusError as problem:
            raise MetaError(f"{what} failed with HTTP {problem.status_code}")
        except (openai.APITimeoutError, openai.APIConnectionError) as problem:
            raise MetaError(f"{what} failed: {type(problem).__name__}")


def search(question: str, instructions: str, town: str) -> dict:
    """Ask Muse Spark with Meta's own web search (POST /v1/responses, the
    built-in web_search tool), near her town ("Portland, Oregon"), or
    anywhere when town is "".

    Returns {"text", "sources": [{"title", "url"}], "searched"}: the answer,
    the pages it cites, and whether it really searched (the model may answer
    from memory instead, which is no good for today's weather).
    Costs $0.0025 per search, plus tokens.

    Our code never visits a website: the search runs inside Meta's API.
    Only her town is sent for the briefing, and only a phone number or web
    address out of a message for the scam lookup: never her name or her words.
    """
    settings = get_settings()
    if not settings.model_api_key:
        raise MetaError("no API key is set up in .env")
    web_search = {"type": "web_search", "search_context_size": "low"}
    if town.strip():  # the scam lookup sends no town: a number is the same everywhere
        city, _, region = (part.strip() for part in town.partition(","))
        web_search["user_location"] = {"type": "approximate", "country": "US", "city": city}
        if region:
            web_search["user_location"]["region"] = region
    response = _respond({
        "model": settings.chat_model,
        "instructions": instructions,
        "input": question,
        "tools": [web_search],
        "include": ["web_search_call.action.sources"],  # the pages each search found
        "reasoning": {"effort": "low"},
        "max_tool_calls": 2,  # at most 2 searches for one answer
        "max_output_tokens": 1500,  # reasoning and words together
        "store": False,
    }, "Web search")
    searched = [item for item in response.output if getattr(item, "type", "") == "web_search_call"]
    # Before searching, the model may say what it will do ("I'll check
    # today's web sources…"): the answer is its last message.
    messages = [item for item in response.output if getattr(item, "type", "") == "message"]
    parts = [part for part in (getattr(messages[-1], "content", None) or [] if messages else [])
             if getattr(part, "type", "") == "output_text"]
    text = " ".join((part.text or "").strip() for part in parts).strip()
    sources = []

    def add(url: str, title: str = "") -> None:
        if url and all(url != source["url"] for source in sources):
            sources.append({"title": title, "url": url})

    for part in parts:
        for note in getattr(part, "annotations", None) or []:
            if getattr(note, "type", "") == "url_citation":
                add(note.url, getattr(note, "title", "") or "")
    if not sources:  # no citation: the pages its searches found
        for call in searched:
            for found in getattr(getattr(call, "action", None), "sources", None) or []:
                add(getattr(found, "url", "") or "")
    return {"text": text, "sources": sources, "searched": bool(searched)}


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


async def open_listening(keywords: list[str]):
    """Open Meta's realtime speech-to-text for hands-free talking: Muse Voice
    Transcribe in ENDPOINTING mode, which hears where each of her turns
    starts and ends. Returns the open connection, its handshake done: send it
    16 kHz 16-bit mono sound, about in real time, and read its events
    (live words, each turn's start and end, each turn's final words).

    The key travels in the first message (Meta reads no header here), which
    is why the page talks to our relay (app/routes/listen.py), never to Meta.
    Costs $0.18 an hour of sound.
    """
    settings = get_settings()
    if not settings.model_api_key:
        raise MetaError("no API key is set up in .env")
    handshake = {
        "authorization": {"accessToken": f"Bearer {settings.model_api_key}"},
        "audioEncoding": "PCM_16KHZ",
        "model": settings.transcribe_model,
        "mode": "ENDPOINTING",
        "partialMode": "CUMULATIVE",  # each live update is the whole turn so far
        "emitAudioProgress": False,
        "languageBias": [settings.language],
        "keywords": keywords,  # names she is likely to say (family, doctor, pills)
    }
    try:
        socket = await ws_connect(REALTIME_URL, open_timeout=10, max_size=2**20)
        await socket.send(json.dumps(handshake))
        answer = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
    except (OSError, asyncio.TimeoutError, ValueError, websockets.exceptions.WebSocketException) as problem:
        raise MetaError(f"live speech-to-text failed: {type(problem).__name__}")
    # Meta's "ready" answer is its only message with no "type": an error
    # event carries a sessionId too (an empty one).
    if not isinstance(answer, dict) or "type" in answer or not answer.get("sessionId"):
        await socket.close()
        raise MetaError("live speech-to-text refused to start")
    return socket
