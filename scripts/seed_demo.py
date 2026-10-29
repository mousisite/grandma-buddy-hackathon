# scripts/seed_demo.py
# A made-up week for "Rose", for the demo video and for trying the Doctor
# notes and the family update. Every name, pill, and symptom here is made up
# (docs/SAFETY.md section 9: demo data only, never real health information).
#
# Run it by hand:
#   .venv\Scripts\python scripts\seed_demo.py
# It refuses if the app already has pills or diary entries, so nothing is
# ever overwritten by accident. To start over with the demo week:
#   .venv\Scripts\python scripts\seed_demo.py --replace
# --replace first saves a copy of the database next to it
# (data\backup-<date>-<time>.db), then clears it and adds the demo week.

import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402

CLEARED = ["symptoms", "moods", "med_events", "medications", "doctor_questions", "check_ins",
           "scam_checks", "safety_events", "messages"]

PROFILE = {
    "name": "Rose Demo",
    "preferred_name": "Rose",
    "family_name": "Maria",
    "family_phone": "555-0100",          # 555-01xx numbers are reserved for fiction
    "family_email": "maria@example.com",  # example.com never delivers real mail
    "doctor_name": "Dr. Lee",
    "doctor_phone": "555-0199",
}

# (name, label exactly as on the bottle, times)
PILLS = [
    ("Lisinopril", "10 mg tablet, take 1 by mouth daily", ["08:00"]),
    ("Metformin", "500 mg tablet, take 1 by mouth twice daily with meals", ["08:00", "18:00"]),
]
# Days ago, time, pill, the reminder she never answered (missed).
MISSED = {(4, "18:00", "Metformin"), (1, "08:00", "Lisinopril")}

# (days ago, time, her words, where, pain, since, source)
DIARY = [
    (6, "09:20", "My left knee is sore when I walk, about a 4", "left knee", 4, "", "diary"),
    (4, "15:10", "My head hurts, a headache since lunch", "head", None, "since lunch", "diary"),
    (3, "10:05", "My knee hurts again going up the stairs, maybe a 5", "knee", 5, "", "diary"),
    (2, "09:00", "I felt a bit dizzy when I stood up this morning", "", None, "this morning", "check_in"),
    (1, "09:30", "The knee is a little better today, about a 2", "knee", 2, "", "check_in"),
]
# One mood a day, from the daily check-in: today first, then going back.
MOODS = ["good", "good", "okay", "low", "okay", "good", "good"]
QUESTIONS = [
    "Is it okay to keep walking every day with my knee?",
    "Why do I feel dizzy when I stand up?",
    "Can I take my pills with coffee?",
]


def at(now: datetime, days_ago: int, clock: str) -> str:
    """ "2026-10-26T09:20:00" for a time on a day this week."""
    hour, minute = (int(part) for part in clock.split(":"))
    day = now - timedelta(days=days_ago)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec="seconds")


def has_data(connection) -> bool:
    return any(connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in ("symptoms", "medications"))


def seed(connection, now: datetime) -> None:
    """Add the demo week, ending today."""
    db.get_profile(connection)  # makes sure her profile row is there
    connection.execute(
        "UPDATE profile SET " + ", ".join(f"{field} = ?" for field in PROFILE) + " WHERE id = 1",
        list(PROFILE.values()),
    )
    for name, label, times in PILLS:
        pill = connection.execute(
            "INSERT INTO medications (name, label_dose, times, active, created_at) VALUES (?, ?, ?, 1, ?)",
            (name, label, json.dumps(times), at(now, 7, "07:00")),
        ).lastrowid
        # This week's reminders, up to now: taken a few minutes late, except two never answered.
        for days_ago in range(6, -1, -1):
            for clock in times:
                due = at(now, days_ago, clock)
                if due > now.isoformat(timespec="seconds"):
                    continue
                answered = (days_ago, clock, name) not in MISSED
                acted = (datetime.fromisoformat(due) + timedelta(minutes=7)).isoformat(timespec="seconds")
                connection.execute(
                    "INSERT INTO med_events (medication_id, due_at, status, acted_at) VALUES (?, ?, ?, ?)",
                    (pill, due, "taken" if answered else "due", acted if answered else ""),
                )
    for days_ago, clock, words, where, pain, since, source in DIARY:
        db.add_symptom(connection, words, source, where, pain, since, f"demo-{days_ago}")
        connection.execute("UPDATE symptoms SET created_at = ? WHERE id = last_insert_rowid()", (at(now, days_ago, clock),))
    for days_ago, mood in enumerate(MOODS):
        connection.execute("INSERT INTO moods (created_at, mood, note, conversation_id) VALUES (?, ?, '', ?)",
                           (at(now, days_ago, "09:00"), mood, f"demo-mood-{days_ago}"))
        connection.execute("INSERT OR IGNORE INTO check_ins (day, started_at, skipped) VALUES (?, ?, 0)",
                           (at(now, days_ago, "09:00")[:10], at(now, days_ago, "09:00")))
    for days_ago, question in zip((5, 3, 2), QUESTIONS):
        db.add_doctor_question(connection, question)
        connection.execute("UPDATE doctor_questions SET created_at = ? WHERE id = last_insert_rowid()",
                           (at(now, days_ago, "11:00"),))


def main(args: list[str]) -> int:
    path = get_settings().database_path
    db.init_db(path)
    connection = db.get_connection(path)
    try:
        if has_data(connection):
            if "--replace" not in args:
                print("The app already has pills or diary entries, so nothing was changed.")
                print("To replace everything with the demo week (a backup is saved first), run:")
                print("  .venv\\Scripts\\python scripts\\seed_demo.py --replace")
                return 1
            backup = Path(path).parent / f"backup-{datetime.now():%Y%m%d-%H%M%S}.db"
            connection.close()
            shutil.copyfile(path, backup)
            print(f"Saved a copy of the old data in {backup}")
            connection = db.get_connection(path)
            for table in CLEARED:
                connection.execute(f"DELETE FROM {table}")
        seed(connection, datetime.now())
        connection.commit()
    finally:
        connection.close()
    print("Added a made-up week for Rose: 2 pills, 5 diary entries, 7 moods, and 3 questions for Dr. Lee.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
