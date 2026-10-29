# scripts/check_checkin.py
# A hand-run check of the daily check-in with the REAL AI.
#
# Sets up a made-up pill that is due right now, starts today's check-in
# (Buddy's fixed opening question), then answers like Rose would through the
# real /api/chat (safety net, prompt, tools, advice guard), replying to what
# Buddy actually asked:
#   - "I'm feeling pretty good"                   -> her mood is saved
#   - "My knee is a bit sore since yesterday"     -> a diary entry (check_in)
#   - a follow-up about the knee                  -> "The left one, ..."
#   - asked about her pills                       -> "Yes, I took them" (taken)
# It prints what Buddy said and checks the three records, that her diary
# entry holds only her words about her knee, and that Buddy gave no advice.
#
# Run it by hand only (about 6 to 10 real calls, a fraction of a cent):
#   .venv\Scripts\python scripts\check_checkin.py
# It uses a throwaway database, so it never touches her real data.

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# A throwaway database, set BEFORE the app reads its settings.
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "check_checkin.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, guard, tools  # noqa: E402
from app.main import app  # noqa: E402

TALK = datetime.now().strftime("%Y-%m-%d") + "-check-in"
MAX_ANSWERS = 6


def rose_answers(buddy: str, answered: list[str]) -> str:
    """What Rose says next, depending on what Buddy just asked."""
    if not answered:
        return "I'm feeling pretty good"
    if tools.asks_about_pills(buddy, ["Lisinopril"]):
        return "Yes, I took them"
    if len(answered) == 1:
        return "My knee is a bit sore since yesterday"
    if "The left one" not in " ".join(answered):
        return "The left one, it aches a little when I walk"
    return "No, nothing else"


def main() -> int:
    verdicts = []
    real_check = guard.check_reply

    def recording_check(reply, own_pills=None):
        verdicts.append(real_check(reply, own_pills))
        return verdicts[-1]

    guard.check_reply = recording_check
    problems = []

    with TestClient(app) as client:  # "with" runs the app's startup (creates the tables)
        client.put("/api/profile", json={"preferred_name": "Rose", "family_name": "Maria", "family_phone": "555-0100",
                                         "doctor_name": "Dr. Lee", "doctor_phone": "555-0199"})
        client.post("/api/meds", json={"name": "Lisinopril", "label_dose": "10 mg tablet, take 1 by mouth daily",
                                       "times": [datetime.now().strftime("%H:%M")]})
        client.get("/api/reminders")  # makes today's reminder, due now

        opening = client.post("/api/check-in/start", json={"conversation_id": TALK}).json()["opening"]
        print(f"Buddy: {opening}\n")
        buddy, answered = opening, []
        while len(answered) < MAX_ANSWERS and "Yes, I took them" not in answered:
            words = rose_answers(buddy, answered)
            answered.append(words)
            verdicts.clear()
            answer = client.post("/api/chat", json={"conversation_id": TALK, "text": words, "mode": "check_in"}).json()
            print(f"She:   {words}")
            print(f"Buddy: {answer['reply']}")
            print(f"       guard stepped in: {[v for v in verdicts if v] or 'no'}  "
                  f"buttons: {[a['label'] for a in answer['actions']]}\n")
            if any(verdicts):
                problems.append(f"The advice guard had to step in after {words!r}.")
            buddy = answer["reply"]

        connection = db.get_connection()
        moods = [r["mood"] for r in connection.execute("SELECT mood FROM moods")]
        diary = [(r["description"], r["body_area"], r["source"]) for r in connection.execute("SELECT * FROM symptoms")]
        connection.close()
        pills = [(r["name"], r["status"]) for r in client.get("/api/reminders").json()["reminders"]]
        print("Mood saved:  ", moods)
        print("Diary saved: ", diary)
        print("Pills after: ", pills)

        if not moods:
            problems.append("No mood was saved.")
        if not any(source == "check_in" and "knee" in words.lower() for words, _, source in diary):
            problems.append("The sore knee was not saved in her diary from the check-in.")
        if any("pretty good" in words or "took them" in words for words, _, _ in diary):
            problems.append("Her mood or pill answer ended up in her diary entry.")
        if ("Lisinopril", "taken") not in pills:
            problems.append("Lisinopril was not marked taken.")

    for problem in problems:
        print("PROBLEM:", problem)
    print("Check-in check:", "PROBLEMS FOUND" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
