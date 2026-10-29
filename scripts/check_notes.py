# scripts/check_notes.py
# A hand-run check of the Doctor notes grouping with the REAL AI.
#
# Fills a throwaway database with the made-up demo week (scripts/seed_demo.py),
# asks Muse Spark to sort her diary entries into topics, and prints the page.
# It checks that the AI's grouping passed every check in app/notes.py (real
# entries, each exactly once, labels only in her words); if it didn't, the
# page falls back to grouping by where it hurts, and this says so.
#
# Run it by hand only (1 real call, well under a cent):
#   .venv\Scripts\python scripts\check_notes.py

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# A throwaway database, set BEFORE the app reads its settings.
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "check_notes.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, notes  # noqa: E402
from scripts.seed_demo import seed  # noqa: E402


def main() -> int:
    db.init_db()
    connection = db.get_connection()
    seed(connection, datetime.now())
    connection.commit()

    checked = []
    real_check = notes.checked_topics

    def recording_check(answer, entries):
        result = real_check(answer, entries)
        checked.append((answer, result))
        return result

    notes.checked_topics = recording_check
    page = notes.notes(connection, 7)
    connection.close()

    print(f"Notes for {page['doctor_name']}: {page['her_name']}, {page['period']}\n")
    for topic in page["topics"]:
        print(topic["label"])
        for entry in topic["entries"]:
            print(f"   {entry['date']}: \"{entry['words']}\"")
    print()
    for pill in page["pills"]:
        print(f"{pill['name']}: taken {pill['taken']} of {pill['total']}, missed {pill['missed']}")
    print("Moods:", ", ".join(f"{m['day']} {m['mood']}" for m in page["moods"]))
    print("Questions:", [q["question"] for q in page["questions"]], "\n")

    if not checked:
        print("PROBLEM: the AI didn't answer (the page grouped by where it hurts).")
        return 1
    answer, result = checked[0]
    if result is None:
        print("PROBLEM: the AI's grouping failed a check, so the page grouped by where it hurts.")
        print("        The AI said:", answer)
        return 1
    print("Notes check: OK (the AI's grouping passed every check)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
