# app/routes/checkin.py
# The daily check-in (docs/SPEC.md feature 5). The first time she opens
# the app each day, Home offers it. Buddy asks how she is feeling (a fixed
# opening, no AI), then the AI asks whether anything hurts and whether she
# took her morning pills, in /api/chat with mode "check_in", and saves her
# answers with its tools (log_mood, log_symptom, mark_pill_taken).
#
# - GET  /api/check-in        is today's check-in still to do? today's mood
# - POST /api/check-in/start  Buddy's opening question (asked once a day)
# - POST /api/check-in/skip   "Not today"

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db, reminders

router = APIRouter()


def today() -> str:
    """Today's date, "2026-10-27" (tests set the clock in reminders)."""
    return reminders.current_time().date().isoformat()


def opening_words(profile: dict) -> str:
    """Buddy's first question: "Good morning, Rose. How are you feeling today?"

    Fixed words, not the AI. At night it still says "Good evening", like Home.
    """
    part = reminders.part_of_day(reminders.current_time())
    greeting = "Good " + ("evening" if part == "night" else part)
    name = (profile.get("preferred_name") or profile.get("name") or "").strip()
    return f"{greeting}{', ' + name if name else ''}. How are you feeling today?"


def save_today(connection, skipped: bool) -> None:
    """Remember that today's check-in was started (or skipped). Once a day:
    starting it again later ("Start" on Home) keeps the first row."""
    connection.execute(
        "INSERT OR IGNORE INTO check_ins (day, started_at, skipped) VALUES (?, ?, ?)",
        (today(), reminders.current_time().isoformat(timespec="seconds"), int(skipped)),
    )


@router.get("/api/check-in")
def check_in_status():
    """Whether today's check-in is still to do, and her latest mood today."""
    connection = db.get_connection()
    try:
        done = connection.execute("SELECT 1 FROM check_ins WHERE day = ?", (today(),)).fetchone()
        mood = connection.execute(
            "SELECT mood, created_at FROM moods WHERE created_at LIKE ? ORDER BY id DESC LIMIT 1",
            (today() + "%",),
        ).fetchone()
        return {"due": done is None, "mood": {"mood": mood["mood"], "at": mood["created_at"]} if mood else None}
    finally:
        connection.close()


class StartRequest(BaseModel):
    conversation_id: str = "check-in"


@router.post("/api/check-in/start")
def start_check_in(request: StartRequest):
    """Start today's check-in: returns Buddy's opening question, and keeps it
    in the conversation so the AI knows it already asked how she feels."""
    if len(request.conversation_id) > 80:
        raise HTTPException(status_code=400, detail="Please try again.")
    connection = db.get_connection()
    try:
        opening = opening_words(db.get_profile(connection))
        save_today(connection, skipped=False)
        db.save_message(connection, request.conversation_id, "assistant", opening)
        connection.commit()
        return {"opening": opening}
    finally:
        connection.close()


@router.post("/api/check-in/skip")
def skip_check_in():
    """"Not today": the check-in isn't offered again until tomorrow."""
    connection = db.get_connection()
    try:
        save_today(connection, skipped=True)
        connection.commit()
        return {"ok": True}
    finally:
        connection.close()
