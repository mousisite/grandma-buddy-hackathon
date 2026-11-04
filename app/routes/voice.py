# app/routes/voice.py
# Buddy's natural voice (app/voice.py).
# - GET  /api/voice  is it here and ready, and which voices can she choose?
#                    ("loading" while the model loads after a start)
# - POST /api/speak  Buddy saying some words, as a WAV. 503 when the natural
#   voice isn't here, isn't loaded yet, or fails: the page then uses the
#   browser's own voice. In a public demo each visitor has a share of the
#   voice (app/public_demo.py); past it, 429 with kind words, and the page
#   uses the browser's voice. The safety words and Buddy's fixed lines are
#   never capped.
# The words go in the request body, never the address, so they never show
# up in the server's log.

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import public_demo, voice

router = APIRouter()


class SpeakRequest(BaseModel):
    text: str
    voice: str = voice.DEFAULT_VOICE
    speed: float = 0.9  # her Voice speed in Settings: 0.75, 0.9, or 1.1


@router.get("/api/voice")
def voice_status():
    return {
        "available": voice.available() and voice.ready(),
        "loading": voice.coming(),
        "process": voice.PROCESS,  # the same on every request when the host runs one process, as it must
        "default": voice.DEFAULT_VOICE,
        "voices": [{"id": key, "name": name} for key, name in voice.VOICES.items()],
    }


@router.post("/api/speak")
def speak(request: SpeakRequest, http: Request):
    text = request.text.strip()
    if not text or len(text) > voice.MAX_TEXT or request.voice not in voice.VOICES or not 0.6 <= request.speed <= 1.4:
        raise HTTPException(status_code=400, detail="Please try again.")
    if not voice.available():
        raise HTTPException(status_code=503, detail="The natural voice isn't set up.")
    if not voice.ready():
        raise HTTPException(status_code=503, detail="The natural voice is still waking up.")
    if not voice.is_fixed(text):  # the safety words and Buddy's fixed lines are never capped
        words = public_demo.speak_allowed(http.headers, http.client.host if http.client else "")
        if words:
            raise HTTPException(status_code=429, detail=words)
    try:
        wav = voice.speech(text, request.voice, round(request.speed, 2))
    except Exception as problem:  # any trouble: the page speaks with the browser voice instead
        print(f"The natural voice failed: {type(problem).__name__}")  # never her words
        raise HTTPException(status_code=503, detail="The natural voice isn't working right now.")
    return Response(wav, media_type="audio/wav")
