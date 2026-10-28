# app/routes/companion.py
# Talking with Grandma Buddy.
# - /api/transcribe: her recorded voice becomes text.
# - /api/chat: her words go through the safety net FIRST (app/safety.py,
#   plain rules, no AI). An emergency, Poison Control, or crisis match
#   returns the fixed screen right away, and the AI is never asked.
#   Otherwise Buddy's AI companion answers (app/companion.py).

import sqlite3

import requests
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app import companion, db, meta_client, safety

router = APIRouter()

# Our recorder stops at 2 minutes, which is about 4 MB. Anything much
# bigger did not come from it, so it is refused before reaching Meta.
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_TEXT = 2000
MODES = {"chat", "check_in", "diary"}


@router.post("/api/transcribe")
def transcribe(audio: UploadFile):
    """Receive a WAV recording from the browser and return what she said."""
    wav = audio.file.read(MAX_AUDIO_BYTES + 1)
    # A WAV file starts with the letters "RIFF", then its size, then "WAVE".
    if len(wav) > MAX_AUDIO_BYTES or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise HTTPException(status_code=400, detail="That recording didn't work. Please try again.")

    try:
        transcript = meta_client.transcribe(wav, db.get_keywords())
    except (meta_client.MetaError, requests.RequestException) as problem:
        # Log what went wrong for us, but never what she said.
        print(f"Speech-to-text failed: {type(problem).__name__}: {problem}")
        raise HTTPException(status_code=502, detail="I couldn't hear that clearly. Please try again.")
    return {"transcript": transcript}


class ChatRequest(BaseModel):
    conversation_id: str = "default"
    text: str
    mode: str = "chat"  # "chat", "check_in", or "diary"


@router.post("/api/chat")
def chat(request: ChatRequest):
    """Her words in, Buddy's answer out. The safety net always goes first."""
    text = request.text.strip()
    if not text or request.mode not in MODES or len(request.conversation_id) > 80:
        raise HTTPException(status_code=400, detail="I didn't catch that. Please try again.")

    # 1. The safety net on her whole message, before anything else, even
    #    before the database. It needs no database, AI, or internet.
    result = safety.check(text)

    try:
        connection = db.get_connection()
    except sqlite3.Error as problem:
        print(f"Database problem: {problem}")
        if result is not None:
            # The database is broken, but the safety screen still appears.
            return safety_screen(result, {"family_name": "", "family_phone": ""})
        raise HTTPException(status_code=503, detail="Please try again in a moment.")

    try:
        profile = db.get_profile(connection)
        saved_text = text[:MAX_TEXT]  # very long messages are kept short
        db.save_message(connection, request.conversation_id, "user", saved_text)

        # Her last few messages together, so "my chest" ... "tight" still counts.
        recent = db.her_recent_words(connection, request.conversation_id)
        together = safety.check_recent(recent) if len(recent) > 1 else None
        said = " ".join(recent) if together is not None else saved_text
        result = safety.merge(result, together, profile["family_name"])
        if result is not None:
            result.message = safety.fixed_message(result.kind, profile["family_name"])
            save_safety_records(connection, request.conversation_id, result, said)
            connection.commit()
            return safety_screen(result, profile)

        # Saved before the slow AI call, so nothing else waits on this database.
        connection.commit()

        # 2. Nothing urgent: Buddy's AI companion answers (app/companion.py).
        return companion.answer(connection, profile, request.conversation_id, saved_text, request.mode)
    except sqlite3.Error as problem:
        print(f"Database problem: {problem}")
        if result is not None:
            return safety_screen(result, {"family_name": "", "family_phone": ""})
        raise HTTPException(status_code=503, detail="Please try again in a moment.")
    finally:
        connection.close()


def safety_screen(result: safety.SafetyResult, profile: dict) -> dict:
    """What the screen needs to show a safety screen."""
    return {
        "reply": result.message,
        "show": result.kind,
        "actions": safety.buttons_for(result, profile["family_name"], profile["family_phone"]),
    }


def save_safety_records(connection, conversation_id: str, result: safety.SafetyResult, said: str) -> None:
    """Record what happened, for her diary, doctor, and family update.

    Her words are kept for emergencies (for her diary and doctor). When crisis
    words were part of it, only the kind of event is kept, never her words.
    """
    crisis = "crisis" in result.kinds
    for kind in result.kinds:
        db.add_safety_event(connection, kind, result.matched, "" if crisis else said)
    if "emergency" in result.kinds:
        signs = ", ".join(name for name in result.matched if name != "thoughts of dying or self-harm")
        db.add_symptom(connection, f"Emergency warning signs ({signs})" if crisis else said, source="safety_net")
    db.save_message(connection, conversation_id, "safety", result.message)
