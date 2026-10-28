# app/routes/diary.py
# Her symptom diary: what she told Buddy about how she feels, in her own
# words. Entries are written by the companion's log_symptom tool and by
# the safety net; this route only reads them for the Diary screen.

from fastapi import APIRouter, Query

from app import db

router = APIRouter()


@router.get("/api/diary")
def read_diary(days: int = Query(7, ge=1, le=90)):
    """Diary entries from the last `days` days, newest first."""
    connection = db.get_connection()
    try:
        return db.diary_entries(connection, days)
    finally:
        connection.close()
