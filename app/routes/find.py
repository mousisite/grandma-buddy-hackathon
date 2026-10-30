# app/routes/find.py
# "Find my things" (docs/SPEC.md feature 12): she says what she's looking
# for and sends a photo of the room. app/finder.py does the looking.
#
# The safety net runs first on what she said, like everything she says to
# Buddy ("my pills, I took them twice" shows Poison Control, with no AI).
# Her photo is only passed along to Meta: never saved or logged here.

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db, finder, meta_client, safety
from app.routes.companion import safety_screen, save_safety_records

router = APIRouter()

MAX_SAID = 200
MAX_IMAGE = 6_000_000  # a data URL; the page shrinks photos to about 1600px first
PHOTO = re.compile(r"data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+")


class FindRequest(BaseModel):
    thing: str  # what she said or typed: "Where are my glasses?"
    image: str  # "data:image/jpeg;base64,..."
    width: int = 0  # the photo's size, from the page
    height: int = 0


@router.post("/api/find")
def find(request: FindRequest):
    """Look for her thing: {found, thing, sentence, box, width, height},
    or a safety screen ({show, reply, actions}) if her words need one."""
    said = request.thing.strip()[:MAX_SAID]

    # 1. The safety net, before anything else.
    result = safety.check(said) if said else None
    if result is not None:
        connection = db.get_connection()
        try:
            profile = db.get_profile(connection)
            result.message = safety.fixed_message(result.kind, profile["family_name"])
            save_safety_records(connection, "find", result, said)
            connection.commit()
            return safety_screen(result, profile)
        finally:
            connection.close()

    # 2. What she's looking for, and her photo.
    thing = finder.clean_thing(said)
    if not thing:
        raise HTTPException(status_code=400, detail="Please tell me what you're looking for.")
    image = request.image.strip()
    if len(image) > MAX_IMAGE or not PHOTO.fullmatch(image):
        raise HTTPException(status_code=400, detail="That photo didn't work. Please try another photo.")

    # 3. Look.
    try:
        found = finder.find(image, thing, request.width, request.height)
    except meta_client.MetaError as problem:
        print(f"Find failed: {problem}")  # never her photo or her words
        raise HTTPException(status_code=503, detail=finder.LOOK_FAILED)
    return {"thing": thing, **found}
