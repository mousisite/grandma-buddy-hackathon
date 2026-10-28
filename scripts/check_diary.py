# scripts/check_diary.py
# A hand-run check of "Something hurts" talks with the REAL AI.
#
# It plays two made-up diary talks through Buddy's real /api/chat (safety
# net, prompt, tools, advice guard) and prints, for each of her answers,
# what Buddy said, whether the advice guard had to step in, which buttons
# appeared, and whether the entry was saved. The second talk asks for
# advice in the middle. At the end it prints the diary as stored.
#
# Run it by hand only (about 8 to 14 real calls, a fraction of a cent):
#   .venv\Scripts\python scripts\check_diary.py
# It uses a throwaway database, so it never touches her real data.

import os
import sys
import tempfile
from pathlib import Path

# A throwaway database, set BEFORE the app reads its settings.
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "check_diary.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, guard  # noqa: E402
from app.main import app  # noqa: E402

# Made-up answers, as if she tapped "Something hurts" and talked.
TALKS = [
    ["my knee hurts when I walk", "about a 5", "since Tuesday", "no, nothing new"],
    ["my back is sore today", "should I put heat or ice on it?", "about a 6", "since this morning"],
]


def main() -> int:
    # Note what the guard decided about each AI reply, before she sees it.
    verdicts = []
    real_check = guard.check_reply

    def recording_check(reply, own_pills=None):
        verdicts.append(real_check(reply, own_pills))
        return verdicts[-1]

    guard.check_reply = recording_check

    with TestClient(app) as client:  # "with" runs the app's startup (creates the tables)
        client.put("/api/profile", json={"preferred_name": "Rose", "family_name": "Maria", "family_phone": "555-0100",
                                         "doctor_name": "Dr. Lee", "doctor_phone": "555-0199"})
        for number, answers in enumerate(TALKS, start=1):
            print(f"===== Talk {number} =====")
            for words in answers:
                verdicts.clear()
                answer = client.post(
                    "/api/chat", json={"conversation_id": f"check-diary-{number}", "text": words, "mode": "diary"}
                ).json()
                stepped_in = [v for v in verdicts if v]
                print(f"She:   {words}")
                print(f"Buddy: {answer['reply']}")
                print(f"       guard stepped in: {stepped_in or 'no'}  saved: {answer.get('diary_saved')}  "
                      f"talk done: {answer.get('diary_done')}")
                print(f"       buttons: {[a['label'] for a in answer['actions']]}\n")
                if answer.get("show") or answer.get("diary_done"):  # the page ends the talk the same way
                    break

    connection = db.get_connection()
    entries = db.diary_entries(connection, days=1)
    connection.close()
    for entry in reversed(entries):
        print(f"Saved: \"{entry['description']}\"  where={entry['body_area']!r} pain={entry['pain_level']} "
              f"since={entry['since']!r} source={entry['source']}")
    if len(entries) < len(TALKS):
        print(f"ONLY {len(entries)} OF {len(TALKS)} DIARY ENTRIES WERE SAVED.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
