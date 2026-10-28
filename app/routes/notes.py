# app/routes/notes.py
# Questions for her doctor. She can add one by voice ("I want to ask my
# doctor about...") or by tapping "Add to doctor notes" under Buddy's reply.
# (The printable doctor notes page comes later.)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db

router = APIRouter()


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
