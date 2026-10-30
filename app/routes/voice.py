# app/routes/voice.py
# Buddy's natural voice (app/voice.py).
# - GET  /api/voice  is it here, and which voices can she choose?
# - POST /api/speak  Buddy saying some words, as a WAV. 503 when the natural
#   voice isn't here or fails: the page then uses the browser's own voice.
# The words go in the request body, never the address, so they never show
# up in the server's log.

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app import voice

router = APIRouter()


class SpeakRequest(BaseModel):
    text: str
    voice: str = voice.DEFAULT_VOICE
    speed: float = 0.9  # her Voice speed in Settings: 0.75, 0.9, or 1.1


@router.get("/api/voice")
def voice_status():
    return {
        "available": voice.available(),
        "default": voice.DEFAULT_VOICE,
        "voices": [{"id": key, "name": name} for key, name in voice.VOICES.items()],
    }


@router.post("/api/speak")
def speak(request: SpeakRequest):
    text = request.text.strip()
    if not text or len(text) > voice.MAX_TEXT or request.voice not in voice.VOICES or not 0.6 <= request.speed <= 1.4:
        raise HTTPException(status_code=400, detail="Please try again.")
    if not voice.available():
        raise HTTPException(status_code=503, detail="The natural voice isn't set up.")
    try:
        wav = voice.speech(text, request.voice, round(request.speed, 2))
    except Exception as problem:  # any trouble: the page speaks with the browser voice instead
        print(f"The natural voice failed: {type(problem).__name__}")  # never her words
        raise HTTPException(status_code=503, detail="The natural voice isn't working right now.")
    return Response(wav, media_type="audio/wav")
