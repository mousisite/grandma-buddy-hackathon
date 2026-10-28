# Tests for her symptom diary: /api/diary lists what was written down,
# newest first, from the last few days. (Saving entries is tested in
# test_companion.py and test_chat_safety.py.) Made-up entries only.

import sqlite3
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import db
from app.main import app


def add_entry(path, days_ago, description, **facts):
    """Write a diary entry as if it were made `days_ago` days ago."""
    connection = db.get_connection(path)
    entry_id = db.add_symptom(connection, description, source=facts.pop("source", "diary"), **facts)
    when = (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds")
    connection.execute("UPDATE symptoms SET created_at = ? WHERE id = ?", (when, entry_id))
    connection.commit()
    connection.close()


def test_the_diary_lists_recent_entries_newest_first(safe_test_setup):
    add_entry(safe_test_setup, 10, "my hip was sore")  # too old for 7 days
    add_entry(safe_test_setup, 3, "my knee hurts when I walk", body_area="knee", pain_level=5, since="Tuesday")
    add_entry(safe_test_setup, 0, "I feel dizzy this morning", source="check_in")

    entries = TestClient(app).get("/api/diary?days=7").json()

    assert [e["description"] for e in entries] == ["I feel dizzy this morning", "my knee hurts when I walk"]
    knee = entries[1]
    assert (knee["body_area"], knee["pain_level"], knee["since"], knee["source"]) == ("knee", 5, "Tuesday", "diary")
    assert entries[0]["pain_level"] is None  # not asked yet is not the same as 0


def test_a_longer_window_shows_older_entries(safe_test_setup):
    add_entry(safe_test_setup, 10, "my hip was sore")
    assert len(TestClient(app).get("/api/diary?days=30").json()) == 1


def test_an_older_database_gets_the_new_column_and_keeps_its_entries(tmp_path):
    # Databases made before diary entries knew their talk (October 26).
    path = str(tmp_path / "older.db")
    older = sqlite3.connect(path)
    older.execute(
        "CREATE TABLE symptoms (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT '', "
        "description TEXT NOT NULL, body_area TEXT NOT NULL DEFAULT '', pain_level INTEGER, "
        "since TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'chat')"
    )
    older.execute("INSERT INTO symptoms (description) VALUES ('my hip was sore')")
    older.commit()
    older.close()

    db.init_db(path)
    db.init_db(path)  # running it again changes nothing

    connection = db.get_connection(path)
    row = connection.execute("SELECT description, conversation_id FROM symptoms").fetchone()
    connection.close()
    assert (row["description"], row["conversation_id"]) == ("my hip was sore", "")


def test_odd_day_counts_are_refused():
    client = TestClient(app)
    assert client.get("/api/diary?days=0").status_code == 422
    assert client.get("/api/diary?days=1000").status_code == 422
