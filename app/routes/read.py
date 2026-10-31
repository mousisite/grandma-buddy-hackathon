# app/routes/read.py
# "Read it to me": POST /api/read with a photo of a letter, a bill, or a
# form; app/reader.py reads it. The words on the paper aren't hers, so the
# safety net doesn't run on them (like the scam checker); nothing she says
# is involved. Her photo is only passed along to Meta: never saved or
# logged here, and the answer isn't saved either.

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db, meta_client, reader
from app.routes.find import MAX_IMAGE, PHOTO

router = APIRouter()

COULDNT_READ_NOW = "I couldn’t read it just now. Please try again in a moment."


class ReadRequest(BaseModel):
    image: str  # "data:image/jpeg;base64,..."


@router.post("/api/read")
def read_it(request: ReadRequest):
    if len(request.image) > MAX_IMAGE or not PHOTO.fullmatch(request.image):
        raise HTTPException(status_code=400, detail="That photo didn’t work. Please try another photo.")
    connection = db.get_connection()
    try:
        profile = db.get_profile(connection)
    finally:
        connection.close()
    try:
        return reader.read(request.image, profile)
    except meta_client.MetaError as problem:
        print(f"Reading a paper failed: {problem}")  # never the paper's words
        raise HTTPException(status_code=503, detail=COULDNT_READ_NOW)
