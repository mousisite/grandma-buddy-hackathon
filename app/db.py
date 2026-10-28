# app/db.py
# Grandma Buddy's memory: a small SQLite database file on this computer.
#
# - All health data stays in this file. It is never uploaded to GitHub.
# - init_db() creates every table (see the table list in docs/ARCHITECTURE.md).
#   It is safe to run every time the app starts: existing tables are kept.

import json
import sqlite3
from datetime import datetime, timedelta
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
                text_size TEXT NOT NULL DEFAULT 'normal'
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

            -- The symptom diary, in her own words.
            CREATE TABLE IF NOT EXISTS symptoms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,
                body_area TEXT NOT NULL DEFAULT '',
                pain_level INTEGER,
                since TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'chat'
            );

            -- Daily moods from the check-in.
            CREATE TABLE IF NOT EXISTS moods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT '',
                mood TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT ''
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

            -- Each pill reminder exists once per time per day.
            CREATE UNIQUE INDEX IF NOT EXISTS med_events_once ON med_events (medication_id, due_at);
            """
        )
        # WAL mode lets the 30-second reminder check read while a slow
        # AI reply is being saved, instead of waiting for it.
        connection.execute("PRAGMA journal_mode=WAL")
        connection.commit()
    finally:
        connection.close()


# ---------- Small helpers used by several routes and the AI's tools ----------

PROFILE_TEXT_FIELDS = [
    "name", "preferred_name", "family_name", "family_email",
    "family_phone", "doctor_name", "doctor_phone",
]


def get_profile(connection: sqlite3.Connection) -> dict:
    """Her profile as a dictionary. Creates the one empty row the first time."""
    connection.execute("INSERT OR IGNORE INTO profile (id) VALUES (1)")
    row = connection.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    profile = dict(row)
    profile["voice_on"] = bool(profile["voice_on"])
    return profile


def save_message(connection: sqlite3.Connection, conversation_id: str, role: str, content: str) -> None:
    """Remember one line of the conversation.

    Roles: "user" (her), "assistant" (Buddy's AI replies), and "safety"
    (the safety net's fixed messages, kept apart so they are never mixed up
    with what the AI said).
    """
    connection.execute(
        "INSERT INTO messages (conversation_id, created_at, role, content) VALUES (?, ?, ?, ?)",
        (conversation_id, now(), role, content),
    )


def her_recent_words(connection: sqlite3.Connection, conversation_id: str, limit: int = 3) -> list[str]:
    """Her last few messages since the safety net last answered, oldest first.

    Used to catch a symptom told in pieces ("my chest" ... "tight"), without
    showing the same safety screen again for later, unrelated messages.
    """
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
) -> int:
    """Save a diary entry in her own words. Returns its id."""
    cursor = connection.execute(
        "INSERT INTO symptoms (created_at, description, body_area, pain_level, since, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (now(), description, body_area, pain_level, since, source),
    )
    return cursor.lastrowid


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
