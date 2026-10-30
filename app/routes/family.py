# app/routes/family.py
# The family update (docs/SPEC.md feature 9): GET /api/family/summary gives
# one day's update and a mailto: link. Nothing is sent from here: she sends
# it from her own email app (docs/SAFETY.md section 9).

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from app import db, family, reminders

router = APIRouter()

MAX_DAYS_BACK = 30


@router.get("/api/family/summary")
def family_summary(day: str = Query("", alias="date")):
    """The update for one day ("2026-10-28"); today when no day is given."""
    today = reminders.current_time().date()
    try:
        chosen = date.fromisoformat(day) if day else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Please choose a day.")
    if chosen > today or chosen < today - timedelta(days=MAX_DAYS_BACK):
        raise HTTPException(status_code=400, detail="Please choose a day from the last month.")
    connection = db.get_connection()
    try:
        return family.summary(connection, chosen)
    finally:
        connection.close()
