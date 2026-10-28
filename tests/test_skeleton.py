# Tests for the Day 1 skeleton: /api/ping and the database tables.
# Written FIRST, before the app code (test-driven development).
# These tests never touch the real Meta API or the real database file.

import sqlite3

from fastapi.testclient import TestClient


def test_ping_returns_ok():
    # The server check: GET /api/ping must answer {"ok": true}.
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_home_page_loads():
    # The home screen must load at /.
    from app.main import app

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Tap to talk" in response.text


def test_database_has_all_tables(tmp_path):
    # db.py must create every table from docs/ARCHITECTURE.md.
    from app import db

    db_path = tmp_path / "test.db"
    db.init_db(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        found = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()

    expected = {
        "profile",
        "medications",
        "med_events",
        "symptoms",
        "moods",
        "doctor_questions",
        "messages",
        "scam_checks",
        "safety_events",
    }
    assert expected.issubset(found)
