# app/routes/listen.py
# Hands-free talking: /api/listen passes her microphone, live, to Meta's
# realtime speech-to-text (meta_client.open_listening) and sends back what
# she is saying (live words) and each finished turn. The page then sends the
# turn to /api/chat like any words, so the safety net still checks every
# word first (docs/SAFETY.md section 7d).
# - Only Buddy's own page may open it. (WebSocket requests skip the HTTP
#   checks in app/main.py, so the same checks run here.)
# - One at a time, and at most 15 minutes: the page opens a new one when needed.
# - Her sound is passed on as it is and never saved or printed. Only her
#   words come back, and only on her own screen.
#
# To the page:  {"type": "ready"}        Meta is listening: send sound
#               {"type": "hearing"}      she started talking
#               {"type": "live", "text"} her words so far in this turn
#               {"type": "turn", "text"} her finished turn
#               {"type": "unavailable"}  no live speech-to-text: tap to talk instead

import asyncio
import json

from fastapi import APIRouter, WebSocket

from app import db, meta_client, security
from app.config import get_settings

router = APIRouter()

LONGEST_SECONDS = 15 * 60
listening = {"open": False}  # one at a time


def from_buddys_page(socket: WebSocket) -> bool:
    host = socket.headers.get("host", "")
    own_origin = ("https" if socket.url.scheme == "wss" else "http") + "://" + host
    return security.allowed_host(host, get_settings().allowed_hosts) and security.from_buddys_page(socket.headers, own_origin)


@router.websocket("/api/listen")
async def listen(socket: WebSocket):
    if not from_buddys_page(socket):
        await socket.close(code=1008)  # policy: another website, or another name for this computer
        return
    if listening["open"]:
        await socket.close(code=1013)  # try again later: already listening
        return
    listening["open"] = True
    try:
        await socket.accept()
        try:
            meta = await meta_client.open_listening(await asyncio.to_thread(db.get_keywords))
        except meta_client.MetaError as problem:
            print(f"Hands-free talking can't start: {problem}")
            await socket.send_json({"type": "unavailable"})
            await socket.close()
            return
        try:
            await socket.send_json({"type": "ready"})
            await asyncio.wait_for(relay(socket, meta), timeout=LONGEST_SECONDS)
        except asyncio.TimeoutError:
            pass  # 15 minutes: the page opens a new one if she is still talking
        finally:
            await meta.close()
            try:
                await socket.close()
            except RuntimeError:
                pass  # the page already left
    finally:
        listening["open"] = False


async def relay(socket: WebSocket, meta) -> None:
    """Her sound to Meta, and her words back, until either side ends."""

    async def from_page():
        while True:
            message = await socket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes"):
                await meta.send(message["bytes"])  # her sound, as it is

    async def from_meta():
        async for message in meta:
            if isinstance(message, bytes):
                continue
            event = json.loads(message)
            kind = event.get("type")
            if kind == "speechStart":
                await socket.send_json({"type": "hearing"})
            elif kind == "transcript":
                await socket.send_json({"type": "live", "text": str(event.get("transcript", ""))})
            elif kind == "speechComplete":
                await socket.send_json({"type": "turn", "text": str(event.get("transcript", ""))})
            elif kind == "error":
                print(f"Live speech-to-text stopped: {event.get('errorType') or 'an error'}")  # never her words

    page = asyncio.create_task(from_page())
    heard = asyncio.create_task(from_meta())
    done, waiting = await asyncio.wait({page, heard}, return_when=asyncio.FIRST_COMPLETED)
    if page in done:
        # She left voice mode: tell Meta her sound has ended, so it closes cleanly.
        try:
            await meta.send(json.dumps({"type": "endStream"}))
        except Exception:
            pass
    for task in waiting:
        task.cancel()
    for task in done:
        if not task.cancelled() and task.exception():
            print(f"Hands-free talking stopped: {type(task.exception()).__name__}")
