# app/db.py
# Grandma Buddy's memory: a small SQLite database file on this computer.
#
# - All health data stays in this file. It is never uploaded to GitHub.
# - init_db() creates every table (see the table list in docs/ARCHITECTURE.md).
#   It is safe to run every time the app starts: existing tables are kept.

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from app.config import get_settings


def now() -> str:
    """The local time as text, like "2026-10-27T08:05:00".

    Always local time, never SQLite's CURRENT_TIMESTAMP (which is UTC and
    would put her evening entries on the next day).
    """
    return datetime.now().isoformat(timespec="seconds")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Open the database, creating its folder if needed.

    Pass db_path in tests to use a temporary file instead of the real one.
    """
    if db_path is None:
        db_path = get_settings().database_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    # Rows behave like dictionaries (row["name"]), which is easier to read.
    connection.row_factory = sqlite3.Row
    return connection


def add_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Add a column to an older database's table, if it isn't there yet.
    (table, column, and definition come from our own code, never from a request.)"""
    if column not in [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db(db_path: str | None = None) -> None:
    """Create all tables if they don't exist yet."""
    connection = get_connection(db_path)
    try:
        connection.executescript(
            """
            -- Grandma's profile: one row. Set up once by a family member.
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT NOT NULL DEFAULT '',
                preferred_name TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT 'English',
                family_name TEXT NOT NULL DEFAULT '',
                family_email TEXT NOT NULL DEFAULT '',
                family_phone TEXT NOT NULL DEFAULT '',
                doctor_name TEXT NOT NULL DEFAULT '',
                doctor_phone TEXT NOT NULL DEFAULT '',
                voice_on INTEGER NOT NULL DEFAULT 1,
                voice_rate REAL NOT NULL DEFAULT 0.9,
                text_size TEXT NOT NULL DEFAULT 'normal',
                calm_mode INTEGER NOT NULL DEFAULT 0,  -- Settings: no movement on screen
                chime INTEGER NOT NULL DEFAULT 0,      -- Settings: soft tone when listening starts/stops
                theme TEXT NOT NULL DEFAULT 'auto'     -- Settings: 'auto', 'light', or 'dark'
            );

            -- Medications, entered by a family member exactly as on the label.
            CREATE TABLE IF NOT EXISTS medications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                label_dose TEXT NOT NULL DEFAULT '',
                times TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT ''
            );

            -- One row per pill per day: did she take it, snooze it, or miss it?
            CREATE TABLE IF NOT EXISTS med_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                medication_id INTEGER NOT NULL REFERENCES medications(id),
                due_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'due',
                snooze_until TEXT NOT NULL DEFAULT '',
                acted_at TEXT NOT NULL DEFAULT ''
            );

            -- The symptom diary, in her own words. conversation_id ties an
            -- entry to the talk it came from (one entry per "Something hurts").
            CREATE TABLE IF NOT EXISTS symptoms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,
                body_area TEXT NOT NULL DEFAULT '',
                pain_level INTEGER,
                since TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'chat',
                conversation_id TEXT NOT NULL DEFAULT ''
            );

            -- Daily moods from the check-in.
            CREATE TABLE IF NOT EXISTS moods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                mood TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            );

            -- One row per day once the daily check-in was started, or
            -- skipped with "Not today", so it is asked only once a day.
            CREATE TABLE IF NOT EXISTS check_ins (
                day TEXT PRIMARY KEY,
                started_at TEXT NOT NULL DEFAULT '',
                skipped INTEGER NOT NULL DEFAULT 0
            );

            -- Questions she wants to ask her doctor.
            CREATE TABLE IF NOT EXISTS doctor_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                question TEXT NOT NULL,
                resolved INTEGER NOT NULL DEFAULT 0
            );

            -- Saved conversation messages, so the companion remembers.
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                content TEXT NOT NULL
            );

            -- Past scam checks (short excerpts only, never passwords or numbers).
            CREATE TABLE IF NOT EXISTS scam_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                input_kind TEXT NOT NULL DEFAULT 'text',
                excerpt TEXT NOT NULL DEFAULT '',
                verdict TEXT NOT NULL DEFAULT '',
                red_flags TEXT NOT NULL DEFAULT '[]'
            );

            -- Every time the safety net showed an emergency/crisis screen.
            CREATE TABLE IF NOT EXISTS safety_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL,
                matched TEXT NOT NULL DEFAULT '[]',
                excerpt TEXT NOT NULL DEFAULT ''
            );

            -- The Memory book: one page per memory she told Buddy. her_words
            -- and talk are what was said; the AI writes title, story (a JSON
            -- list of paragraphs) and scene (what the picture shows, also its
            -- alt text). picture is a file name in data/memories/.
            -- status: writing, painting, ready, or no_picture.
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                conversation_id TEXT NOT NULL DEFAULT '',
                her_words TEXT NOT NULL DEFAULT '',
                talk TEXT NOT NULL DEFAULT '[]',
                title TEXT NOT NULL DEFAULT '',
                story TEXT NOT NULL DEFAULT '[]',
                scene TEXT NOT NULL DEFAULT '',
                picture TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'writing'
            );

            -- What Buddy remembers about her life (tools.remember_fact):
            -- people, pets, hobbies, shows, plans. Never health or feelings.
            -- follow_up is a question to ask on follow_up_on (an event's
            -- day after); asked_at says it was asked. forgotten: she or her
            -- family chose "Forget this" in Settings (Undo sets it back).
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL,
                fact TEXT NOT NULL,
                follow_up TEXT NOT NULL DEFAULT '',
                follow_up_on TEXT NOT NULL DEFAULT '',
                asked_at TEXT NOT NULL DEFAULT '',
                forgotten INTEGER NOT NULL DEFAULT 0
            );

            -- One or two sentences about each earlier day's talk, learned the
            -- next day (companion.learn_from_past_days). How many days have
            -- a row is how many days Buddy has learned from.
            CREATE TABLE IF NOT EXISTS talk_summaries (
                day TEXT PRIMARY KEY,
                summary TEXT NOT NULL DEFAULT '',
                made_at TEXT NOT NULL DEFAULT ''
            );

            -- How she likes to talk, learned day by day ("Loves puns",
            -- "Prefers short replies"). Never health, moods, or her mind.
            CREATE TABLE IF NOT EXISTS style_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL,
                forgotten INTEGER NOT NULL DEFAULT 0
            );

            -- Each pill reminder exists once per time per day.
            CREATE UNIQUE INDEX IF NOT EXISTS med_events_once ON med_events (medication_id, due_at);
            """
        )
        # A database made before these columns existed gets them, keeping
        # everything already saved.
        add_column(connection, "symptoms", "conversation_id", "TEXT NOT NULL DEFAULT ''")  # October 27
        add_column(connection, "profile", "calm_mode", "INTEGER NOT NULL DEFAULT 0")  # October 28
        add_column(connection, "profile", "chime", "INTEGER NOT NULL DEFAULT 0")  # October 28
        add_column(connection, "profile", "theme", "TEXT NOT NULL DEFAULT 'auto'")  # October 28
        add_column(connection, "moods", "conversation_id", "TEXT NOT NULL DEFAULT ''")  # October 28
        # A second family member to call (the welcome, Settings): October 29.
        add_column(connection, "profile", "family2_name", "TEXT NOT NULL DEFAULT ''")
        add_column(connection, "profile", "family2_phone", "TEXT NOT NULL DEFAULT ''")
        # WAL mode lets one connection read while another writes. Writers
        # still take turns, so the companion saves after each round of tools
        # (app/companion.py) and never holds the lock while the AI thinks.
        connection.execute("PRAGMA journal_mode=WAL")
        connection.commit()
    finally:
        connection.close()


# ---------- Small helpers used by several routes and the AI's tools ----------

PROFILE_TEXT_FIELDS = [
    "name", "preferred_name", "family_name", "family_email",
    "family_phone", "family2_name", "family2_phone", "doctor_name", "doctor_phone",
]


def get_profile(connection: sqlite3.Connection) -> dict:
    """Her profile as a dictionary. Creates the one empty row the first time."""
    connection.execute("INSERT OR IGNORE INTO profile (id) VALUES (1)")
    row = connection.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    profile = dict(row)
    for switch in ("voice_on", "calm_mode", "chime"):
        profile[switch] = bool(profile[switch])
    return profile


def save_message(connection: sqlite3.Connection, conversation_id: str, role: str, content: str,
                 at: datetime | None = None) -> None:
    """Remember one line of the conversation (said now, or at a given time).

    Roles: "user" (her), "assistant" (Buddy's AI replies), and "safety"
    (the safety net's fixed messages, kept apart so they are never mixed up
    with what the AI said).
    """
    connection.execute(
        "INSERT INTO messages (conversation_id, created_at, role, content) VALUES (?, ?, ?, ?)",
        (conversation_id, at.isoformat(timespec="seconds") if at else now(), role, content),
    )


def her_recent_words(connection: sqlite3.Connection, conversation_id: str, limit: int = 3) -> list[str]:
    """Her last few messages in this talk since the safety net last answered,
    oldest first. Used for the words saved in a diary entry."""
    last_safety = connection.execute(
        "SELECT MAX(id) FROM messages WHERE conversation_id = ? AND role = 'safety'",
        (conversation_id,),
    ).fetchone()[0] or 0
    rows = connection.execute(
        "SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' AND id > ? "
        "ORDER BY id DESC LIMIT ?",
        (conversation_id, last_safety, limit),
    ).fetchall()
    return [row["content"] for row in reversed(rows)]


def her_last_words(connection: sqlite3.Connection, minutes: int = 10, limit: int = 3) -> list[sqlite3.Row]:
    """Her last few messages (id and content) from the last few minutes, in
    ANY talk, oldest first, since the safety net last answered.

    The safety net checks them together, so a symptom told in pieces ("my
    chest" ... "tight") is caught even across a tap on "Something hurts" or
    midnight, without showing a screen again for later, unrelated messages.
    """
    since = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    last_safety = connection.execute("SELECT MAX(id) FROM messages WHERE role = 'safety'").fetchone()[0] or 0
    rows = connection.execute(
        "SELECT id, content FROM messages WHERE role = 'user' AND id > ? AND created_at >= ? ORDER BY id DESC LIMIT ?",
        (last_safety, since, limit),
    ).fetchall()
    return list(reversed(rows))


def talk_messages(connection: sqlite3.Connection, conversation_id: str) -> list[sqlite3.Row]:
    """Everything said in this talk (role and content) since the safety net
    last answered, oldest first."""
    last_safety = connection.execute(
        "SELECT MAX(id) FROM messages WHERE conversation_id = ? AND role = 'safety'",
        (conversation_id,),
    ).fetchone()[0] or 0
    return connection.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? AND id > ? ORDER BY id",
        (conversation_id, last_safety),
    ).fetchall()


def memory_talk(connection: sqlite3.Connection, conversation_id: str, after: str) -> list[dict]:
    """What she and Buddy said in this talk after a time, for a Memory book
    page, oldest first. Only after the safety net last answered in ANY talk,
    and never words that were not kept: nothing said around a safety screen
    ever reaches a page."""
    last_safety = connection.execute("SELECT MAX(id) FROM messages WHERE role = 'safety'").fetchone()[0] or 0
    rows = connection.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? AND id > ? AND created_at > ? "
        "AND role IN ('user', 'assistant') AND content != ? ORDER BY id",
        (conversation_id, last_safety, after, NOT_KEPT),
    ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def save_mood(connection: sqlite3.Connection, conversation_id: str, mood: str, note: str) -> None:
    """Save how she feels overall: one mood per talk. The AI may save it again
    later in the same talk; then her latest words replace the first ones, so
    her doctor notes never count one feeling twice."""
    changed = connection.execute(
        "UPDATE moods SET mood = ?, note = ?, created_at = ? WHERE conversation_id = ? AND conversation_id != ''",
        (mood, note, now(), conversation_id),
    ).rowcount
    if not changed:
        connection.execute(
            "INSERT INTO moods (created_at, mood, note, conversation_id) VALUES (?, ?, ?, ?)",
            (now(), mood, note, conversation_id),
        )


def buddy_last_words(connection: sqlite3.Connection, conversation_id: str) -> str:
    """What Buddy said last in this talk ("" before Buddy has said anything)."""
    row = connection.execute(
        "SELECT content FROM messages WHERE conversation_id = ? AND role IN ('assistant', 'safety') "
        "ORDER BY id DESC LIMIT 1",
        (conversation_id,),
    ).fetchone()
    return row["content"] if row else ""


NOT_KEPT = "(Not kept: she shared something painful, and Buddy showed the crisis screen.)"


def forget_her_words(connection: sqlite3.Connection, message_ids: list[int]) -> None:
    """Replace her words in these messages (docs/SAFETY.md 7b: crisis words are never kept)."""
    connection.executemany("UPDATE messages SET content = ? WHERE id = ?", [(NOT_KEPT, i) for i in message_ids])


def add_safety_event(connection: sqlite3.Connection, kind: str, matched: list[str], excerpt: str = "") -> None:
    connection.execute(
        "INSERT INTO safety_events (created_at, kind, matched, excerpt) VALUES (?, ?, ?, ?)",
        (now(), kind, json.dumps(matched), excerpt[:200]),
    )


def add_doctor_question(connection: sqlite3.Connection, question: str) -> int:
    cursor = connection.execute(
        "INSERT INTO doctor_questions (created_at, question) VALUES (?, ?)", (now(), question)
    )
    return cursor.lastrowid


def recent_history(connection: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """The last messages across ALL days, oldest first, for the AI to read.

    Buddy remembers what she shared on earlier days. The safety net's fixed
    messages are shown to the AI as Buddy's own words.
    """
    rows = connection.execute(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        {"role": "assistant" if row["role"] == "safety" else row["role"], "content": row["content"]}
        for row in reversed(rows)
    ]


def crisis_recently(connection: sqlite3.Connection, hours: int = 24) -> bool:
    """True if the crisis screen was shown in the last day."""
    since = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    row = connection.execute(
        "SELECT 1 FROM safety_events WHERE kind = 'crisis' AND created_at >= ? LIMIT 1", (since,)
    ).fetchone()
    return row is not None


def active_pill_names(connection: sqlite3.Connection) -> list[str]:
    return [row["name"] for row in connection.execute("SELECT name FROM medications WHERE active = 1")]


def add_symptom(
    connection: sqlite3.Connection,
    description: str,
    source: str,
    body_area: str = "",
    pain_level: int | None = None,
    since: str = "",
    conversation_id: str = "",
) -> int:
    """Save a diary entry in her own words. Returns its id."""
    cursor = connection.execute(
        "INSERT INTO symptoms (created_at, description, body_area, pain_level, since, source, conversation_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (now(), description, body_area, pain_level, since, source, conversation_id),
    )
    return cursor.lastrowid


def save_talk_entry(
    connection: sqlite3.Connection,
    conversation_id: str,
    description: str,
    body_area: str = "",
    pain_level: int | None = None,
    since: str = "",
    source: str = "diary",
) -> int:
    """The one diary entry of a "Something hurts" talk or a daily check-in
    (source "check_in"). Saving again in the same talk updates it: all her
    words so far, plus any new facts (a fact she gave earlier stays if
    nothing new replaces it). Returns its id."""
    row = connection.execute(
        "SELECT id, body_area, pain_level, since FROM symptoms WHERE conversation_id = ? AND source = ? "
        "ORDER BY id LIMIT 1",
        (conversation_id, source),
    ).fetchone()
    if row is None:
        return add_symptom(connection, description, source, body_area, pain_level, since, conversation_id)
    connection.execute(
        "UPDATE symptoms SET description = ?, body_area = ?, pain_level = ?, since = ? WHERE id = ?",
        (
            description,
            body_area or row["body_area"],
            row["pain_level"] if pain_level is None else pain_level,
            since or row["since"],
            row["id"],
        ),
    )
    return row["id"]


# ---------- What Buddy remembers, and what it learned ----------

def save_fact(connection: sqlite3.Connection, kind: str, fact: str, follow_up: str, follow_up_on: str) -> bool:
    """Remember a fact about her life. The same fact again (any capitals,
    with or without a period) updates it. False if she asked Buddy to
    forget it: then it stays forgotten."""
    same = fact.lower().rstrip(".")
    row = connection.execute(
        "SELECT id, forgotten FROM facts WHERE lower(rtrim(fact, '.')) = ? LIMIT 1", (same,)
    ).fetchone()
    if row is None:
        connection.execute(
            "INSERT INTO facts (created_at, updated_at, kind, fact, follow_up, follow_up_on) VALUES (?, ?, ?, ?, ?, ?)",
            (now(), now(), kind, fact, follow_up, follow_up_on),
        )
        return True
    if row["forgotten"]:
        return False
    connection.execute(
        "UPDATE facts SET updated_at = ?, kind = ?, follow_up = ?, follow_up_on = ?, asked_at = '' WHERE id = ?",
        (now(), kind, follow_up, follow_up_on, row["id"]),
    )
    return True


def known_facts(connection: sqlite3.Connection, events_since: str, limit: int = 30) -> list[sqlite3.Row]:
    """The facts Buddy keeps in mind, newest first: everything not
    forgotten, but an event only until a week after it."""
    return connection.execute(
        "SELECT id, kind, fact, follow_up, follow_up_on FROM facts WHERE forgotten = 0 "
        "AND (kind != 'event' OR follow_up_on = '' OR follow_up_on >= ?) ORDER BY updated_at DESC, id DESC LIMIT ?",
        (events_since, limit),
    ).fetchall()


def due_follow_up(connection: sqlite3.Connection, today: str, since: str) -> sqlite3.Row | None:
    """The oldest follow-up question due now (from `since` to today) and
    not yet asked."""
    return connection.execute(
        "SELECT id, follow_up FROM facts WHERE forgotten = 0 AND follow_up != '' AND asked_at = '' "
        "AND follow_up_on BETWEEN ? AND ? ORDER BY follow_up_on, id LIMIT 1",
        (since, today),
    ).fetchone()


def learned_facts(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every fact not forgotten, newest first (for "What Buddy has learned")."""
    return connection.execute(
        "SELECT id, kind, fact, follow_up FROM facts WHERE forgotten = 0 ORDER BY updated_at DESC, id DESC"
    ).fetchall()


def style_notes(connection: sqlite3.Connection, forgotten: bool = False) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT id, note FROM style_notes WHERE forgotten = ? ORDER BY id", (int(forgotten),)
    ).fetchall()


def days_learned(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM talk_summaries").fetchone()[0]


def recent_summaries(connection: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    """The last few days' summaries, oldest first (empty ones left out)."""
    rows = connection.execute(
        "SELECT day, summary FROM talk_summaries WHERE summary != '' ORDER BY day DESC LIMIT ?", (limit,)
    ).fetchall()
    return list(reversed(rows))


def days_to_learn(connection: sqlite3.Connection, today: str, limit: int = 5) -> list[str]:
    """Earlier days (the last two weeks) when she talked with Buddy and that
    Buddy hasn't learned from yet, oldest first, at most `limit`."""
    since = (date.fromisoformat(today) - timedelta(days=14)).isoformat()
    rows = connection.execute(
        "SELECT DISTINCT substr(created_at, 1, 10) AS day FROM messages WHERE role = 'user' AND content != ? "
        "AND substr(created_at, 1, 10) < ? AND substr(created_at, 1, 10) >= ? "
        "AND substr(created_at, 1, 10) NOT IN (SELECT day FROM talk_summaries) ORDER BY day DESC LIMIT ?",
        (NOT_KEPT, today, since, limit),
    ).fetchall()
    return [row["day"] for row in reversed(rows)]


def day_talk(connection: sqlite3.Connection, day: str, limit: int = 80) -> list[dict]:
    """What she and Buddy said on one day, oldest first: never the safety
    net's messages or words that were not kept."""
    rows = connection.execute(
        "SELECT role, content FROM messages WHERE substr(created_at, 1, 10) = ? AND role IN ('user', 'assistant') "
        "AND content != ? ORDER BY id DESC LIMIT ?",
        (day, NOT_KEPT, limit),
    ).fetchall()
    return [{"role": row["role"], "content": row["content"][:300]} for row in reversed(rows)]


def save_learned_day(connection: sqlite3.Connection, day: str, summary: str, notes: list[str]) -> None:
    """One day learned: its summary, and her style notes as they are now
    (only replaced when there are new ones; forgotten notes stay forgotten)."""
    connection.execute("INSERT OR REPLACE INTO talk_summaries (day, summary, made_at) VALUES (?, ?, ?)",
                       (day, summary, now()))
    if notes:
        connection.execute("DELETE FROM style_notes WHERE forgotten = 0")
        connection.executemany("INSERT INTO style_notes (created_at, note) VALUES (?, ?)",
                               [(now(), note) for note in notes])


def last_talk_at(connection: sqlite3.Connection) -> str:
    """When she or Buddy last said something ("" if never)."""
    return connection.execute(
        "SELECT MAX(created_at) FROM messages WHERE role IN ('user', 'assistant')"
    ).fetchone()[0] or ""


def buddy_last_reply(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT content FROM messages WHERE role = 'assistant' ORDER BY id DESC LIMIT 1").fetchone()
    return row["content"] if row else ""


def last_memory(connection: sqlite3.Connection, conversation_id: str) -> sqlite3.Row | None:
    """The newest Memory book page made from this talk (id and created_at), or None."""
    return connection.execute(
        "SELECT id, created_at FROM memories WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conversation_id,)
    ).fetchone()


def add_memory(connection: sqlite3.Connection, conversation_id: str, her_words: str, talk: list[dict]) -> int:
    """A new Memory book page, waiting to be written and painted. Returns its id."""
    return connection.execute(
        "INSERT INTO memories (created_at, updated_at, conversation_id, her_words, talk) VALUES (?, ?, ?, ?, ?)",
        (now(), now(), conversation_id, her_words, json.dumps(talk)),
    ).lastrowid


def talk_has_entry(connection: sqlite3.Connection, conversation_id: str) -> bool:
    """True once a "Something hurts" talk has saved its diary entry."""
    return connection.execute(
        "SELECT 1 FROM symptoms WHERE conversation_id = ? AND source = 'diary'", (conversation_id,)
    ).fetchone() is not None


def diary_entries(connection: sqlite3.Connection, days: int) -> list[dict]:
    """Her diary entries from the last `days` days, newest first."""
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    rows = connection.execute(
        "SELECT id, created_at, description, body_area, pain_level, since, source FROM symptoms "
        "WHERE created_at >= ? ORDER BY created_at DESC, id DESC",
        (since,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_keywords(db_path: str | None = None) -> list[str]:
    """Names she is likely to say: her family member, her doctor, and her pills.

    Speech-to-text gets these as hints so it spells them right.
    Blanks and repeats are skipped, and the list is kept short.
    """
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            "SELECT family_name FROM profile "
            "UNION ALL SELECT doctor_name FROM profile "
            "UNION ALL SELECT name FROM medications WHERE active = 1"
        ).fetchall()
    finally:
        connection.close()
    names = [row[0].strip() for row in rows if row[0] and row[0].strip()]
    return list(dict.fromkeys(names))[:20]  # dict.fromkeys drops repeats, keeps order
