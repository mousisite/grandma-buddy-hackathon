# app/routes/notes.py
# Doctor notes (docs/SPEC.md feature 8) and the questions for her doctor.
# - GET  /api/doctor-notes?days=7       the page (app/notes.py)
# - POST /api/doctor-questions          add a question ("Add a question", or
#                                       "Add to doctor notes" after a talk)
# - POST /api/doctor-questions/{id}/asked   she asked it: off the page
# - POST /api/doctor-questions/{id}/reopen  Undo: back on the page

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db, notes

router = APIRouter()


@router.get("/api/doctor-notes")
def doctor_notes(days: int = 7):
    """The doctor notes page for the last 7, 14, or 30 days."""
    if days not in notes.DAY_CHOICES:
        raise HTTPException(status_code=400, detail="Please choose 7, 14, or 30 days.")
    connection = db.get_connection()
    try:
        return notes.notes(connection, days)
    finally:
        connection.close()


class Question(BaseModel):
    question: str


@router.post("/api/doctor-questions")
def add_question(body: Question):
    question = body.question.strip()
    if not question or len(question) > 300:
        raise HTTPException(status_code=400, detail="Please say the question again.")
    connection = db.get_connection()
    try:
        question_id = db.add_doctor_question(connection, question)
        connection.commit()
    finally:
        connection.close()
    return {"id": question_id, "question": question}


def set_asked(question_id: int, asked: bool) -> dict:
    """Mark a question asked (it leaves the page) or not asked (Undo).
    Questions are never deleted."""
    connection = db.get_connection()
    try:
        changed = connection.execute(
            "UPDATE doctor_questions SET resolved = ? WHERE id = ?", (int(asked), question_id)
        ).rowcount
        connection.commit()
    finally:
        connection.close()
    if not changed:
        raise HTTPException(status_code=404, detail="That question isn't there anymore.")
    return {"ok": True}


@router.post("/api/doctor-questions/{question_id}/asked")
def question_asked(question_id: int):
    return set_asked(question_id, True)


@router.post("/api/doctor-questions/{question_id}/reopen")
def question_reopened(question_id: int):
    return set_asked(question_id, False)
