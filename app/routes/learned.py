# app/routes/learned.py
# "What Buddy has learned" (Settings, for a family member): the facts Buddy
# remembers about her life and its notes on how she likes to talk, so she
# and her family can see them and take any of them back.
# - GET  /api/learned                              facts, notes, and how many days Buddy learned from
# - POST /api/learned/{facts|notes}/{id}/forget    "Forget this"
# - POST /api/learned/{facts|notes}/{id}/restore   Undo

from fastapi import APIRouter, HTTPException

from app import db

router = APIRouter()

TABLES = {"facts": "facts", "notes": "style_notes"}  # what the address says -> its table (never from the request)


@router.get("/api/learned")
def learned():
    connection = db.get_connection()
    try:
        return {
            "facts": [dict(row) for row in db.learned_facts(connection)],
            "notes": [dict(row) for row in db.style_notes(connection)],
            "days_learned": db.days_learned(connection),
        }
    finally:
        connection.close()


@router.post("/api/learned/{what}/{item_id}/{action}")
def forget_or_restore(what: str, item_id: int, action: str):
    if what not in TABLES or action not in ("forget", "restore"):
        raise HTTPException(status_code=404, detail="I couldn’t find that.")
    connection = db.get_connection()
    try:
        changed = connection.execute(
            f"UPDATE {TABLES[what]} SET forgotten = ? WHERE id = ?", (int(action == "forget"), item_id)
        ).rowcount
        if not changed:
            raise HTTPException(status_code=404, detail="I couldn’t find that.")
        connection.commit()
        return {"ok": True}
    finally:
        connection.close()
