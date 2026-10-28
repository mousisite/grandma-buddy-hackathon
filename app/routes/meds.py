# app/routes/meds.py
# Her pills.
# - /api/meds: a family member adds, changes, and removes pills (name, the
#   label exactly as on the bottle, and the times of day). Removing only
#   hides a pill, so "Undo" can bring it back and past records stay.
# - /api/reminders: today's reminders for the banner and the Pills screen,
#   and her answers: "I took it" and "Remind me in 10 minutes".
# The rules live in app/reminders.py.

import json
import re

from fastapi import APIRouter, Body, HTTPException

from app import db, reminders, safety

router = APIRouter()

TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")  # "08:00" to "23:59"
MAX_TIMES = 6
MAX_IDS = 20


def refuse(field: str, message: str):
    raise HTTPException(status_code=400, detail={"field": field, "message": message})


def clean_pill(pill: dict) -> dict:
    """Check what the family entered. Anything odd is refused, and the
    message names the entry to fix."""
    name = pill.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        refuse("name", "Please type the pill’s name, as on the bottle.")
    label = pill.get("label_dose", "")
    if not isinstance(label, str) or len(label.strip()) > 200:
        refuse("label_dose", "Please check the label text. It can be up to 200 letters.")
    times = pill.get("times")
    if not isinstance(times, list) or not times or len(times) > MAX_TIMES:
        refuse("times", f"Please choose from 1 to {MAX_TIMES} times of day.")
    if not all(isinstance(t, str) and TIME.match(t) for t in times):
        refuse("times", "Please check the times of day.")
    return {"name": name.strip(), "label_dose": label.strip(), "times": sorted(set(times))}


@router.get("/api/meds")
def read_pills():
    connection = db.get_connection()
    try:
        return reminders.active_pills(connection)
    finally:
        connection.close()


@router.post("/api/meds")
def add_pill(pill: dict = Body(...)):
    clean = clean_pill(pill)
    connection = db.get_connection()
    try:
        cursor = connection.execute(
            "INSERT INTO medications (name, label_dose, times, created_at) VALUES (?, ?, ?, ?)",
            (clean["name"], clean["label_dose"], json.dumps(clean["times"]), db.now()),
        )
        connection.commit()
        return {"id": cursor.lastrowid, **clean}
    finally:
        connection.close()


@router.put("/api/meds/{pill_id}")
def change_pill(pill_id: int, pill: dict = Body(...)):
    clean = clean_pill(pill)
    connection = db.get_connection()
    try:
        changed = connection.execute(
            "UPDATE medications SET name = ?, label_dose = ?, times = ? WHERE id = ? AND active = 1",
            (clean["name"], clean["label_dose"], json.dumps(clean["times"]), pill_id),
        ).rowcount
        if not changed:
            raise HTTPException(status_code=404, detail="That pill isn’t there anymore.")
        # Today's waiting reminders follow the new times (ones at a time it
        # still has stay, snooze and all).
        reminders.forget_waiting_reminders(connection, pill_id, reminders.current_time(), keep_times=clean["times"])
        connection.commit()
        return {"id": pill_id, **clean}
    finally:
        connection.close()


@router.delete("/api/meds/{pill_id}")
def remove_pill(pill_id: int):
    """Hide the pill (Undo brings it back). Taken and missed records stay."""
    connection = db.get_connection()
    try:
        connection.execute("UPDATE medications SET active = 0 WHERE id = ?", (pill_id,))
        reminders.forget_waiting_reminders(connection, pill_id, reminders.current_time())
        connection.commit()
        return {"ok": True}
    finally:
        connection.close()


@router.post("/api/meds/{pill_id}/restore")
def restore_pill(pill_id: int):
    """Undo a removal."""
    connection = db.get_connection()
    try:
        connection.execute("UPDATE medications SET active = 1 WHERE id = ?", (pill_id,))
        connection.commit()
        return {"ok": True}
    finally:
        connection.close()


# ---------- Reminders ----------

def todays_reminders(connection) -> dict:
    """What the banner, the Pills screen, and the Today card need."""
    now = reminders.current_time()
    found = reminders.reminders_now(connection, now)
    connection.commit()  # today's new reminder rows
    due = [r for r in found if r["status"] == "due"]
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    poison_control = connection.execute(
        "SELECT 1 FROM safety_events WHERE kind = 'poison_control' AND created_at >= ?", (start_of_day,)
    ).fetchone()
    return {
        "reminders": found,
        "due_words": reminders.reminder_words(due) if due else "",
        "has_pills": bool(reminders.active_pills(connection)),
        # After a Poison Control screen today, the page doesn't read pill
        # reminders aloud and shows the Poison Control message instead.
        "after_poison_control": poison_control is not None,
        "poison_control_words": safety.POISON_CONTROL_MESSAGE if poison_control else "",
    }


@router.get("/api/reminders")
def read_reminders():
    connection = db.get_connection()
    try:
        return todays_reminders(connection)
    finally:
        connection.close()


def reminder_ids(body: dict) -> list[int]:
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > MAX_IDS or not all(type(i) is int for i in ids):
        raise HTTPException(status_code=400, detail="Please try again.")
    return ids


@router.post("/api/reminders/taken")
def took_it(body: dict = Body(...)):
    """ "I took it" (also after a reminder was missed: she may take it late)."""
    ids = reminder_ids(body)
    connection = db.get_connection()
    try:
        reminders.mark_taken(connection, ids, reminders.current_time())
        return todays_reminders(connection)
    finally:
        connection.close()


@router.post("/api/reminders/snooze")
def remind_me_later(body: dict = Body(...)):
    """ "Remind me in 10 minutes"."""
    ids = reminder_ids(body)
    connection = db.get_connection()
    try:
        reminders.snooze(connection, ids, reminders.current_time())
        return todays_reminders(connection)
    finally:
        connection.close()
