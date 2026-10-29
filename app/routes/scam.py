# app/routes/scam.py
# "Check a message" (docs/SPEC.md feature 7): she pastes a strange text or
# email, reads it out loud (the page writes it down first, with
# /api/transcribe), or takes a photo of it. app/scam.py does the checking.

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db, scam

router = APIRouter()

MAX_TEXT = 4000
MAX_IMAGE = 3_000_000  # a data URL; the page shrinks photos to about 1600px first
KINDS = {"text", "voice", "photo"}
PHOTO = re.compile(r"data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+")


class ScamRequest(BaseModel):
    text: str = ""
    image: str = ""  # "data:image/jpeg;base64,..."
    kind: str = "text"  # "text" (pasted), "voice" (read out loud), or "photo"


@router.post("/api/scam-check")
def scam_check(request: ScamRequest):
    """Check one message: Likely scam, Suspicious, or Looks safe, with what to do."""
    text = request.text.strip()[:MAX_TEXT]
    image = request.image.strip()
    if request.kind not in KINDS:
        raise HTTPException(status_code=400, detail="Please try that again.")
    if image and (len(image) > MAX_IMAGE or not PHOTO.fullmatch(image)):
        raise HTTPException(status_code=400, detail="That picture didn't work. Please try another photo.")
    if not text and not image:
        raise HTTPException(status_code=400, detail="Please paste the message, read it out loud, or take a photo of it.")

    connection = db.get_connection()
    try:
        return scam.check(connection, db.get_profile(connection), text, image, request.kind)
    finally:
        connection.close()
