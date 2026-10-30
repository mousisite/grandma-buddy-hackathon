# scripts/seed_demo.py
# A made-up week for "Rose", for the demo video: every screen filled in.
# Every name, pill, phone number, and story here is made up (docs/SAFETY.md
# section 9: demo data only, never real health information).
#
#   - her profile: Maria (her daughter) and Daniel (her son), Dr. Lee;
#   - 2 pills on a schedule, mostly taken this week;
#   - 5 daily check-ins with mixed moods;
#   - a knee pain that comes and goes, in her own words;
#   - 2 questions for Dr. Lee and 1 checked scam text;
#   - 2 Memory book pages (painted with Muse Image if an API key is set);
#   - what Buddy has learned: Leo visits on Sundays, she loves gardening,
#     how she likes to talk, and 3 days of talks.
#
# Run it by hand:
#   .venv\Scripts\python scripts\seed_demo.py
# It refuses if the app already has pills or diary entries, so nothing is
# ever overwritten by accident. To start over with the demo week:
#   .venv\Scripts\python scripts\seed_demo.py --reset
# --reset first saves a copy of the database (data\backup-<date>-<time>.db),
# then wipes it and the Memory book pictures, then adds the demo week.
# The 2 Memory book pictures cost about 2 cents; --no-paint skips them.

import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, memories  # noqa: E402
from app.config import get_settings  # noqa: E402

PROFILE = {
    "name": "Rose Demo",
    "preferred_name": "Rose",
    "family_name": "Maria",
    "family_phone": "555-0100",          # 555-01xx numbers are reserved for fiction
    "family_email": "maria@example.com",  # example.com never delivers real mail
    "family2_name": "Daniel",
    "family2_phone": "555-0144",
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

# A knee pain that comes and goes, in her own words:
# (days ago, time, her words, where, pain, since, source)
DIARY = [
    (6, "09:20", "My knee is sore when I walk, about a 4", "knee", 4, "", "diary"),
    (5, "16:40", "The knee is better this afternoon, I barely notice it", "knee", None, "", "chat"),
    (3, "10:05", "My knee hurts again going up the stairs, maybe a 5", "knee", 5, "", "diary"),
    (2, "09:15", "My knee is stiff this morning, about a 3", "knee", 3, "this morning", "check_in"),
    (0, "09:10", "My knee feels much better today", "knee", None, "", "check_in"),
]
# One mood a day from the daily check-in, today first, then going back.
MOODS = ["great", "good", "low", "okay", "good"]
QUESTIONS = [
    "Is it okay to keep walking every day with my knee?",
    "Can I take my pills with coffee?",
]
# The grandparent scam she checked (a short excerpt, never long numbers).
SCAM = ("Grandma it's me, I'm in jail, send $2,000 in gift cards and don't tell mom",
        ["Someone in trouble asks for money", "Asks for gift cards", "Says to keep it secret"])

# Two Memory book pages, written the way Buddy writes them.
PAGES = [
    (4, "Summers at aunt Lucy's farm",
     ["When I was a girl we spent every summer at my aunt Lucy's farm. It was about 1958.",
      "I fed the chickens every morning, and we picked blueberries by the old stone wall. My little brother "
      "Tom was there too, and he always ate more berries than he picked."],
     "A farm in summer morning light, with chickens and blueberry bushes by an old stone wall. Two small "
     "figures seen from behind, far away."),
    (2, "The church hall dance",
     ["I met my husband Walter at a dance at the church hall. He stepped on my feet all night.",
      "My best friend June was there too. It was the spring of 1961, and the hall smelled of lilacs."],
     "An old church hall in spring light with lilacs at the open doors. Small figures dancing far away, "
     "seen from behind."),
]

# What Buddy has learned about her (Settings, "What Buddy has learned").
FACTS = [
    ("person", "Her grandson Leo visits on Sundays", "Did Leo come by on Sunday?"),  # asked in today's greeting
    ("hobby", "She loves gardening, especially her roses", ""),
    ("person", "Her daughter Maria lives nearby", ""),
]
NOTES = ["Loves a gentle joke", "Prefers short replies", "Lights up talking about her garden"]
SUMMARIES = [  # (days ago, what they talked about)
    (3, "Rose talked about her roses and the squirrels that keep digging in the garden."),
    (2, "Rose told the story of the church hall dance where she met Walter."),
    (1, "Rose said Leo is learning to ride a bike and wants to show her on Sunday."),
]


def at(now: datetime, days_ago: int, clock: str) -> str:
    """ "2026-10-26T09:20:00" for a time on a day this week."""
    hour, minute = (int(part) for part in clock.split(":"))
    day = now - timedelta(days=days_ago)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec="seconds")


def has_data(connection) -> bool:
    return any(connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in ("symptoms", "medications"))


def seed(connection, now: datetime) -> list[int]:
    """Add the demo week, ending today. Returns the Memory book pages to paint."""
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
                    continue  # later today: the app shows it as upcoming
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
    for days_ago, question in zip((5, 3), QUESTIONS):
        db.add_doctor_question(connection, question)
        connection.execute("UPDATE doctor_questions SET created_at = ? WHERE id = last_insert_rowid()",
                           (at(now, days_ago, "11:00"),))
    connection.execute("INSERT INTO scam_checks (created_at, input_kind, excerpt, verdict, red_flags) "
                       "VALUES (?, 'text', ?, 'likely_scam', ?)", (at(now, 3, "14:20"), SCAM[0], json.dumps(SCAM[1])))
    pages = []
    for days_ago, title, paragraphs, scene in PAGES:
        when = at(now, days_ago, "15:00")
        pages.append(connection.execute(
            "INSERT INTO memories (created_at, updated_at, conversation_id, her_words, talk, title, story, scene, status) "
            "VALUES (?, ?, ?, ?, '[]', ?, ?, ?, 'no_picture')",
            (when, when, f"demo-memory-{days_ago}", " ".join(paragraphs), title, json.dumps(paragraphs), scene),
        ).lastrowid)
    today = now.date().isoformat()
    for kind, fact, follow_up in FACTS:
        connection.execute("INSERT INTO facts (created_at, updated_at, kind, fact, follow_up, follow_up_on) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           (at(now, 3, "10:00"), at(now, 3, "10:00"), kind, fact, follow_up, today if follow_up else ""))
    connection.executemany("INSERT INTO style_notes (created_at, note) VALUES (?, ?)",
                           [(at(now, 1, "20:00"), note) for note in NOTES])
    connection.executemany("INSERT INTO talk_summaries (day, summary, made_at) VALUES (?, ?, ?)",
                           [(at(now, days_ago, "12:00")[:10], summary, at(now, days_ago - 1, "09:00"))
                            for days_ago, summary in SUMMARIES])
    return pages


def back_up_and_wipe(path: str) -> Path:
    """Save a copy of the database (SQLite's own backup, so nothing is
    missed), then empty every table and remove the Memory book pictures."""
    backup = Path(path).parent / f"backup-{datetime.now():%Y%m%d-%H%M%S}.db"
    source = sqlite3.connect(path)
    copy = sqlite3.connect(backup)
    source.backup(copy)
    copy.close()
    tables = [row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:  # names come from the database itself, never from a request
        source.execute(f"DELETE FROM {table}")
    source.execute("DELETE FROM sqlite_sequence")  # ids start from 1 again
    source.commit()
    source.close()
    shutil.rmtree(memories.pictures_dir(), ignore_errors=True)
    return backup


def main(args: list[str]) -> int:
    path = get_settings().database_path
    db.init_db(path)
    connection = db.get_connection(path)
    try:
        if has_data(connection) and "--reset" not in args:
            print("The app already has pills or diary entries, so nothing was changed.")
            print("To start over with the demo week (a backup is saved first), run:")
            print("  .venv\\Scripts\\python scripts\\seed_demo.py --reset")
            return 1
    finally:
        connection.close()
    if "--reset" in args:
        print(f"Saved a copy of the old data in {back_up_and_wipe(path)}")
    connection = db.get_connection(path)
    try:
        pages = seed(connection, datetime.now())
        connection.commit()
    finally:
        connection.close()
    print("Added a made-up week for Rose: 2 pills, 5 check-ins, a knee that comes and goes, 2 questions for Dr. Lee,")
    print("1 checked scam text, 2 Memory book pages, and what Buddy has learned about her.")
    if "--no-paint" in args or not get_settings().model_api_key:
        print("The Memory book pages have no pictures yet: open a page and tap \"Paint it again\".")
    else:
        print("Painting the 2 Memory book pictures with Muse Image (about 2 cents)…")
        for page in pages:
            connection = db.get_connection(path)
            memories.paint_again(connection, page)
            connection.commit()
            connection.close()
            memories.make_page(page)
        print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
