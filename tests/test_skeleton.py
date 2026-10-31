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


def test_the_page_and_its_files_are_always_checked_for_updates():
    # Without this, a browser can keep an old copy of a script for hours
    # after it changed (it kept the old speech.js and its robotic voice).
    from app.main import app

    client = TestClient(app)
    for path in ["/", "/static/speech.js", "/static/styles.css"]:
        assert client.get(path).headers.get("cache-control") == "no-cache", path


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


def test_the_database_is_always_in_the_project_folder(monkeypatch, tmp_path):
    # Started from another folder, the app and scripts/seed_demo.py must
    # still use the same database: a relative path counts from the project.
    from pathlib import Path

    from app.config import get_settings

    project = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", "data/grandma_buddy.db")
    assert Path(get_settings().database_path) == project / "data" / "grandma_buddy.db"
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "elsewhere.db"))  # a full path stays as it is
    assert Path(get_settings().database_path) == tmp_path / "elsewhere.db"
