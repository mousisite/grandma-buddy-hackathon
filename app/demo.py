# app/demo.py
# The demo week: a made-up week for "Rose", so every screen has something
# to show for the demo video and the judges. Every name, pill, phone
# number, and story here is made up (docs/SAFETY.md section 9: demo data
# only, never real health information). Built relative to today, so it is
# always "this week":
#
#   - her profile: Maria (her daughter) and Daniel (her son), Dr. Lee;
#   - 2 pills on a schedule, mostly taken this week, this morning's taken;
#   - 5 daily check-ins with mixed moods, today's done this morning;
#   - a knee pain that comes and goes, in her own words, a note today;
#   - 2 questions for Dr. Lee and 1 checked scam text;
#   - 3 Memory book pages (painted with Muse Image if an API key is set);
#   - 4 messages with Maria (today's from Maria still new), yesterday's
#     postcard (sent), today's postcard (ready to send), and this morning's
#     talk about her tulips;
#   - what Buddy has learned: Leo visits on Sundays, she loves gardening,
#     how she likes to talk, and 3 days of talks.
#
# scripts/seed_demo.py runs this by hand; "Reset the demo week" in Settings
# (Her data) runs it with one tap, in demo mode only (no Stripe key).

import json
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app import accounts, db, memories
from app.config import get_settings

ROOT = Path(__file__).resolve().parent.parent
DEMO_NAME = "Rose Demo"  # the profile name the demo week sets: how a screen knows the demo week is loaded

# Maria's account on the family page (/family). A demo password, made up
# like everything else here: never a real one.
FAMILY_ACCOUNT = {"name": "Maria", "email": "maria@example.com", "password": "rose-garden-2026"}

PROFILE = {
    "name": DEMO_NAME,
    "preferred_name": "Rose",
    "family_name": "Maria",
    "family_phone": "555-0100",          # 555-01xx numbers are reserved for fiction
    "family_email": "maria@example.com",  # example.com never delivers real mail
    "family2_name": "Daniel",
    "family2_phone": "555-0144",
    "doctor_name": "Dr. Lee",
    "doctor_phone": "555-0199",
    "city": "Portland, Oregon",  # for the weather and what's happening in town (a real city; nothing else about her)
}

# (name, label exactly as on the bottle, times)
PILLS = [
    ("Lisinopril", "10 mg tablet, take 1 by mouth daily", ["08:00"]),
    ("Metformin", "500 mg tablet, take 1 by mouth twice daily with meals", ["08:00", "18:00"]),
]
# Days ago, time, pill, the reminder she never answered (not taken).
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
# A page she started from an old photo: the kitchen painted for Find my
# things (no one in it), as if it were a photo of her first kitchen.
PHOTO_PAGE = {
    "title": "My first kitchen",
    "paragraphs": ["Our first kitchen was tiny, but the window caught the morning sun. I kept a blue teapot on the table, "
                   "always warm.",
                   "Walter built the shelves himself the week we moved in. They were crooked, and I loved them."],
    "scene": "A small sunny kitchen with a blue teapot on a wooden table and crooked shelves, morning light.",
    "photo_scene": "A small kitchen with a wooden table, a blue teapot, and shelves by a sunny window.",
    "photo": ROOT / "scripts" / "find_photos" / "kitchen.webp",
}

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

# This morning's talk (the line today's postcard is painted from): (clock, who, words).
TODAY_TALK = [
    ("10:20", "user", "The tulips came up this morning, the red ones by the gate"),
    ("10:20", "assistant", "Red tulips by the gate, how lovely. Did you plant them yourself?"),
    ("10:21", "user", "Walter and I planted them years ago and they still come back every spring"),
    ("10:21", "assistant", "Every spring, like a little visit from him. I hope you get to sit out with them today."),
]
# Messages between her and Maria: (days ago, time, who, the words, seen by
# her?). Today's from Maria is still new, so Home says so and Buddy reads it.
MESSAGES = [
    (1, "17:05", "her", "Leo rode his bike all the way to the corner and back, I clapped", True),
    (1, "17:20", "family", "He was so proud, Mom. See you Sunday!", True),
    (0, "10:25", "her", "The red tulips are up, come and see them on Sunday", True),
    (0, "10:40", "family", "Can't wait to see them. I'll bring Leo on Sunday", False),
]
# Two postcards: yesterday's, sent (the kitchen painted for Find my things,
# which fits her words), and today's, ready to send (the tulips Muse Image
# painted in scripts/check_messages.py, for her line this morning).
POSTCARDS = [
    {"days_ago": 1, "sent": "16:10",
     "sentence": "I had my tea in the kitchen sun this morning and the whole room smelled of toast",
     "scene": "A small sunny kitchen with a blue teapot on a wooden table, morning light through the window.",
     "picture": ROOT / "scripts" / "find_photos" / "kitchen.webp"},
    {"days_ago": 0, "sent": "",
     "sentence": TODAY_TALK[0][2],
     "scene": "A garden gate with red tulips blooming beside it in gentle spring morning light.",
     "picture": ROOT / "scripts" / "memory_photos" / "tulips.webp"},
]


def demo_mode() -> bool:
    """Demo mode: no Stripe key, so the Family plan is the no-card flow and
    the demo week can be reset from Settings."""
    return not get_settings().stripe_secret_key


def at(now: datetime, days_ago: int, clock: str) -> str:
    """ "2026-10-26T09:20:00" for a time on a day this week."""
    hour, minute = (int(part) for part in clock.split(":"))
    day = now - timedelta(days=days_ago)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec="seconds")


def has_data(connection) -> bool:
    return any(connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in ("symptoms", "medications"))


# The three Memory book paintings, made by Muse Image for this project and
# kept small, so the demo week has its pictures without painting anything
# (a fresh install, the public demo). pictures=False leaves the pages to be
# painted instead (scripts/seed_demo.py --paint).
DEMO_PICTURES = ROOT / "scripts" / "demo_pictures"


def seed(connection, now: datetime, pictures: bool = True) -> list[int]:
    """Add the demo week, ending today. Returns the Memory book pages still
    to paint: none when the bundled pictures are used."""
    db.get_profile(connection)  # makes sure her profile row is there
    connection.execute(
        "UPDATE profile SET " + ", ".join(f"{field} = ?" for field in PROFILE) + " WHERE id = 1",
        list(PROFILE.values()),
    )
    # Maria can sign in on the family page, and Rose shares her diary there in the demo.
    accounts.create_account(connection, **FAMILY_ACCOUNT)
    connection.execute("UPDATE profile SET share_diary = 1 WHERE id = 1")
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
    # A third page, started from an old photo (the kitchen painted for Find
    # my things: no one in it, so the page gets a painting and shows the
    # photo under the story).
    when = at(now, 1, "16:00")
    photo_page = connection.execute(
        "INSERT INTO memories (created_at, updated_at, conversation_id, her_words, talk, title, story, scene, status, "
        "people, photo_scene) VALUES (?, ?, 'demo-memory-photo', ?, '[]', ?, ?, ?, 'no_picture', 0, ?)",
        (when, when, " ".join(PHOTO_PAGE["paragraphs"]), PHOTO_PAGE["title"], json.dumps(PHOTO_PAGE["paragraphs"]),
         PHOTO_PAGE["scene"], PHOTO_PAGE["photo_scene"]),
    ).lastrowid
    memories.pictures_dir().mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PHOTO_PAGE["photo"], memories.pictures_dir() / f"photo-{photo_page}.webp")
    connection.execute("UPDATE memories SET photo = ? WHERE id = ?", (f"photo-{photo_page}.webp", photo_page))
    pages.append(photo_page)
    if pictures:
        pages = give_pictures(connection, pages)
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
    # This morning's talk, the messages with Maria, and the two postcards.
    for clock, role, words in TODAY_TALK:
        db.save_message(connection, "demo-today", role, words, at=datetime.fromisoformat(at(now, 0, clock)))
    connection.executemany(
        "INSERT INTO family_messages (created_at, text, sender, sender_name, read_at) VALUES (?, ?, ?, ?, ?)",
        [(at(now, days_ago, clock), text, who, "Maria" if who == "family" else "",
          at(now, days_ago, clock) if seen else "") for days_ago, clock, who, text, seen in MESSAGES])
    for card in POSTCARDS:
        made = at(now, card["days_ago"], "10:30")
        postcard = connection.execute(
            "INSERT INTO postcards (day, created_at, updated_at, sentence, scene, status, said_until, shared_at) "
            "VALUES (?, ?, ?, ?, ?, 'ready', ?, ?)",
            (made[:10], made, made, card["sentence"], card["scene"], at(now, card["days_ago"], "10:21"),
             at(now, card["days_ago"], card["sent"]) if card["sent"] else ""),
        ).lastrowid
        shutil.copyfile(card["picture"], memories.pictures_dir() / f"postcard-{postcard}.webp")
        connection.execute("UPDATE postcards SET picture = ? WHERE id = ?", (f"postcard-{postcard}.webp", postcard))
    return pages


def give_pictures(connection, pages: list[int]) -> list[int]:
    """Each page gets its bundled painting (the first page the first file,
    and so on) and is ready. Returns the pages left without one."""
    left = []
    for number, memory_id in enumerate(pages, start=1):
        bundled = DEMO_PICTURES / f"{number}.webp"
        if not bundled.exists():
            left.append(memory_id)
            continue
        name = f"{memory_id}.webp"
        shutil.copyfile(bundled, memories.pictures_dir() / name)
        memories.set_status(connection, memory_id, "ready", picture=name)
    return left


def back_up_and_wipe(path: str) -> Path:
    """Save a copy of the database (SQLite's own backup, so nothing is
    missed), then empty every table and remove the pictures and voices."""
    from app import voice_messages

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
    shutil.rmtree(voice_messages.voices_dir(), ignore_errors=True)
    return backup


def reset(now: datetime | None = None) -> dict:
    """Start the demo week over: a backup, a wipe, and the week again, ending
    today. Returns the backup's name and the pages still to paint (the caller
    paints them, in the background or by hand)."""
    path = get_settings().database_path
    db.init_db(path)
    backup = back_up_and_wipe(path)
    connection = db.get_connection(path)
    try:
        pages = seed(connection, now or datetime.now())  # with the bundled pictures: nothing left to paint
        connection.commit()
    finally:
        connection.close()
    return {"backup": backup.name, "pages": pages}
