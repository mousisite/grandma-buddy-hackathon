# app/routes/profile.py
# Her profile: her name, her family member's and doctor's names and numbers,
# and her voice settings. A family member fills this in once.

import re

from fastapi import APIRouter, Body, HTTPException

from app import db

router = APIRouter()

# Longest allowed length for each text field.
MAX_LENGTH = {
    "name": 80,
    "preferred_name": 80,
    "family_name": 80,
    "family_email": 120,
    "family_phone": 30,
    "doctor_name": 80,
    "doctor_phone": 30,
}
PHONE = re.compile(r"^[0-9+()\-. ]*$")
EMAIL = re.compile(r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
KIND_NO = "Please check that entry and try again."

# How the Family & settings form names each entry when one is refused.
FIELD_WORDS = {
    "name": "her full name",
    "preferred_name": "the name Buddy calls her",
    "family_name": "the family member’s name",
    "family_email": "the family email address",
    "family_phone": "the family phone number",
    "doctor_name": "the doctor’s name",
    "doctor_phone": "the doctor’s phone number",
}


def refuse(field: str, fix: str = ""):
    """Stop the save and say which entry needs another look, and how to fix it."""
    words = FIELD_WORDS.get(field)
    message = f"Please check {words}. {fix}".strip() if words else KIND_NO
    raise HTTPException(status_code=400, detail={"field": field, "message": message})


@router.get("/api/profile")
def read_profile():
    connection = db.get_connection()
    try:
        profile = db.get_profile(connection)
        connection.commit()
        return profile
    finally:
        connection.close()


@router.put("/api/profile")
def update_profile(changes: dict = Body(...)):
    """Save only the fields sent. Anything odd is refused, nothing is half-saved."""
    clean = {}
    for field, value in changes.items():
        if field in MAX_LENGTH:
            if not isinstance(value, str) or len(value.strip()) > MAX_LENGTH[field]:
                refuse(field, "It’s too long.")
            value = value.strip()
            # A phone number needs real digits (at least 3, like 911), or it is left empty.
            if field.endswith("phone") and value and (not PHONE.match(value) or sum(ch.isdigit() for ch in value) < 3):
                refuse(field, "Use numbers, like 555‑0123.")
            if field == "family_email" and not EMAIL.match(value):
                refuse(field, "It looks like name@example.com.")
            clean[field] = value
        elif field == "voice_on":
            if not isinstance(value, bool):
                refuse(field)
            clean[field] = int(value)
        elif field == "voice_rate":
            if not isinstance(value, (int, float)) or not 0.6 <= value <= 1.4:
                refuse(field)
            clean[field] = float(value)
        else:
            refuse(field)

    connection = db.get_connection()
    try:
        db.get_profile(connection)  # make sure the row exists
        for field, value in clean.items():
            # field comes from the fixed lists above, never from the request text
            connection.execute(f"UPDATE profile SET {field} = ? WHERE id = 1", (value,))
        profile = db.get_profile(connection)
        connection.commit()
        return profile
    finally:
        connection.close()
