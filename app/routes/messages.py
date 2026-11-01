# app/routes/messages.py
# "Message Maria" and the daily postcard (docs/SPEC.md feature 22).
# - POST /api/messages              she tapped Send: the safety net first, then kept for the family page
# - POST /api/messages/voice        the same, with the recording Say it kept: Maria hears her voice too
# - GET  /api/messages              today's messages both ways, and any of the family's she hasn't seen
# - POST /api/messages/{id}/read    she has seen a family member's message
# - POST /api/family/reply          a signed-in family member writes to her (their words, never the AI's)
# - POST /api/family/voice          a signed-in family member's voice message (kept here, written down by Voice Transcribe)
# - GET  /api/messages/{id}/voice   that recording, to play
# - GET  /api/postcard/today        today's postcard (made now if it isn't yet)
# - POST /api/postcard/today/send   "Send postcard to Maria": the family page shows it
# - GET  /api/postcard/{id}/picture the painting (from data/memories/)
# Nothing here calls anyone or sends anything off this computer: a message
# is a row the family page reads (docs/SAFETY.md 9c).

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from datetime import datetime

from datetime import timedelta

from app import db, memories, notes, postcards, reminders, safety, tools, voice_messages
from app.routes.companion import safety_screen, save_safety_records
from app.routes.family_accounts import signed_in_account

router = APIRouter()

MAX_MESSAGE = tools.MAX_MESSAGE  # the same limit as the "Send this to Maria" button
WAITING_DAYS = 7  # a family message she hasn't seen stays on her screen this long


class MessageRequest(BaseModel):
    text: str


def message_for_screen(row) -> dict:
    """One message as her Family screen shows it: whose it is, whether it is
    new to her (only a family member's can be), and its recording to play
    when it is a voice message."""
    from_family = row["sender"] == "family"
    return {"id": row["id"], "time": notes.time_words(datetime.fromisoformat(row["created_at"])), "text": row["text"],
            "from": "family" if from_family else "her", "name": row["sender_name"] if from_family else "",
            "unread": from_family and not row["read_at"],
            "voice": f"/api/messages/{row['id']}/voice" if row["voice"] else ""}


def since_day() -> str:
    return (reminders.current_time().date() - timedelta(days=WAITING_DAYS)).isoformat()


@router.post("/api/messages")
def send_message(request: MessageRequest):
    """Her message, in her own words. The safety net runs first: words that
    need a safety screen show it and are never sent (the family sees only
    the screen's kind and time, as always)."""
    text = " ".join(request.text.split())
    if not text or len(text) > MAX_MESSAGE:
        raise HTTPException(status_code=400, detail="Please say a short message first.")
    connection = db.get_connection()
    try:
        result = safety.check(text)
        if result is not None:
            profile = db.get_profile(connection)
            result.message = safety.fixed_message(result.kind, profile["family_name"])
            # Recorded like any other input of her words, under its own talk id.
            save_safety_records(connection, "family-message", result, text)
            connection.commit()
            return safety_screen(result, profile)
        message_id = db.add_family_message(connection, text, reminders.current_time())
        connection.commit()
        row = connection.execute(f"SELECT {db.MESSAGE_FIELDS} FROM family_messages WHERE id = ?", (message_id,)).fetchone()
        return {"show": None, "message": message_for_screen(row)}
    finally:
        connection.close()


@router.post("/api/messages/voice")
def send_message_with_voice(audio: UploadFile, text: str = Form("")):
    """Her message with her own voice: the words she read over in the box
    (written down by Say it, so nothing goes to Meta again) and the
    recording Say it kept. The safety net runs on the words first; a match
    shows the safety screen and keeps nothing, not even the recording."""
    words = " ".join(text.split())
    if not words or len(words) > MAX_MESSAGE:
        raise HTTPException(status_code=400, detail="Please say a short message first.")
    recording = audio.file.read(voice_messages.MAX_VOICE_BYTES + 1)
    if not voice_messages.is_wav(recording):
        raise HTTPException(status_code=400, detail="That recording didn’t work. Please say it again, or send just the words.")
    connection = db.get_connection()
    try:
        result = safety.check(words)
        if result is not None:
            profile = db.get_profile(connection)
            result.message = safety.fixed_message(result.kind, profile["family_name"])
            save_safety_records(connection, "family-message", result, words)
            connection.commit()
            return safety_screen(result, profile)
        message_id = db.add_family_message(connection, words, reminders.current_time())
        name = voice_messages.keep(recording, message_id)
        connection.execute("UPDATE family_messages SET voice = ? WHERE id = ?", (name, message_id))
        connection.commit()
        row = connection.execute(f"SELECT {db.MESSAGE_FIELDS} FROM family_messages WHERE id = ?", (message_id,)).fetchone()
        return {"show": None, "message": message_for_screen(row)}
    finally:
        connection.close()


@router.get("/api/messages")
def messages_today():
    """Today's messages both ways, plus any of the family's she hasn't seen
    yet, oldest first; how many are new; and the newest new one, for Home."""
    connection = db.get_connection()
    try:
        day = reminders.current_time().date().isoformat()
        shown = [message_for_screen(row) for row in db.messages_for_her(connection, day, since_day())]
        waiting = db.unread_family_messages(connection, since_day())
        return {
            "messages": shown,
            "unread": len(waiting),
            "latest_unread": {"name": waiting[0]["sender_name"], "text": waiting[0]["text"],
                              "voice": f"/api/messages/{waiting[0]['id']}/voice" if waiting[0]["voice"] else ""} if waiting else None,
        }
    finally:
        connection.close()


@router.post("/api/messages/{message_id}/read")
def message_read(message_id: int):
    """She has seen (and heard) a family member's message on her Family screen."""
    connection = db.get_connection()
    try:
        if not db.mark_message_read(connection, message_id, reminders.current_time()):
            raise HTTPException(status_code=404, detail="There’s no such message.")
        connection.commit()
        return {"ok": True}
    finally:
        connection.close()


@router.get("/api/messages/{message_id}/voice")
def message_voice(message_id: int):
    """A family member's recording, to play on her Family screen (and on
    the family page). Only a file name saved by our own code."""
    connection = db.get_connection()
    try:
        row = connection.execute("SELECT voice FROM family_messages WHERE id = ?", (message_id,)).fetchone()
    finally:
        connection.close()
    path = voice_messages.voice_path(row["voice"]) if row else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="There’s no recording for that message.")
    return FileResponse(path, media_type="audio/wav")


@router.post("/api/family/voice")
def family_voice(audio: UploadFile, http_request: Request):
    """A signed-in family member's voice message (a WAV from the family
    page's recorder). Kept on this computer and played as it is; Meta's
    Voice Transcribe writes down what it heard so the words show too."""
    recording = audio.file.read(voice_messages.MAX_VOICE_BYTES + 1)
    if not voice_messages.is_wav(recording):
        raise HTTPException(status_code=400, detail="That recording didn’t work. Please try again.")
    connection = db.get_connection()
    try:
        account = signed_in_account(http_request, connection)
        profile = db.get_profile(connection)
        connection.commit()  # the profile row may have been made just now: let go before Meta works
        words = voice_messages.words_of(recording, profile["preferred_name"] or profile["name"])
        message_id = db.add_family_message(connection, words, reminders.current_time(), "family", account["name"])
        name = voice_messages.keep(recording, message_id)
        connection.execute("UPDATE family_messages SET voice = ? WHERE id = ?", (name, message_id))
        connection.commit()
        row = connection.execute(f"SELECT {db.MESSAGE_FIELDS} FROM family_messages WHERE id = ?", (message_id,)).fetchone()
        return {"message": message_for_screen(row)}
    finally:
        connection.close()


class ReplyRequest(BaseModel):
    text: str


@router.post("/api/family/reply")
def family_reply(request: ReplyRequest, http_request: Request):
    """A signed-in family member writes to her. Their words, as they wrote
    them, shown on her Family screen as theirs ("Maria wrote: …") and read
    aloud there; never through the AI (docs/SAFETY.md 9c)."""
    text = " ".join(request.text.split())
    if not text or len(text) > MAX_MESSAGE:
        raise HTTPException(status_code=400, detail="Please write a short message first.")
    connection = db.get_connection()
    try:
        account = signed_in_account(http_request, connection)
        message_id = db.add_family_message(connection, text, reminders.current_time(), "family", account["name"])
        connection.commit()
        row = connection.execute(f"SELECT {db.MESSAGE_FIELDS} FROM family_messages WHERE id = ?", (message_id,)).fetchone()
        return {"message": message_for_screen(row)}
    finally:
        connection.close()


@router.get("/api/postcard/today")
def postcard_today():
    """Today's postcard: {"postcard": {...} or null, "status", "why"}. Made
    now when there isn't one yet (Muse Spark picks, Muse Image paints), so
    this can take a little while: the screen shows a shimmer."""
    connection = db.get_connection()
    try:
        day = reminders.current_time().date().isoformat()
        postcard, status, why = postcards.make_today(connection, day)
        return {"postcard": postcard, "status": status, "why": why}
    finally:
        connection.close()


@router.post("/api/postcard/today/send")
def send_postcard():
    connection = db.get_connection()
    try:
        day = reminders.current_time().date().isoformat()
        postcard = postcards.send(connection, day, reminders.current_time())
        if postcard is None:
            raise HTTPException(status_code=400, detail="There’s no postcard to send yet today.")
        connection.commit()
        return {"postcard": postcard}
    finally:
        connection.close()


@router.get("/api/postcard/{postcard_id}/picture")
def postcard_picture(postcard_id: int):
    connection = db.get_connection()
    try:
        row = connection.execute("SELECT picture FROM postcards WHERE id = ?", (postcard_id,)).fetchone()
    finally:
        connection.close()
    # Only a file name we saved ourselves, never a path from the request.
    path = memories.picture_path(row["picture"]) if row else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="No picture yet.")
    return FileResponse(path, media_type=memories.MEDIA_TYPES[path.suffix[1:]])
