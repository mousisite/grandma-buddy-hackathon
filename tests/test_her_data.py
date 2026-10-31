# Tests for "Her data" (docs/SPEC.md feature 21): a family member can export
# everything (one zip: the database and her pictures) and delete everything
# (every table, every picture and photo, every backup, then the file
# shrunk), only by typing DELETE. And the installable app's pieces: the
# manifest, its icons, and a service worker that never caches /api.
# No Meta here. Made-up data only.

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, memories
from app.main import STATIC_DIR, app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def her_data(safe_test_setup):
    """A little of everything: her name, a diary entry, a page with a
    painting and an old photo, a family session, and an old backup file."""
    connection = db.get_connection(safe_test_setup)
    db.get_profile(connection)
    connection.execute("UPDATE profile SET preferred_name = 'Rose' WHERE id = 1")
    connection.execute("INSERT INTO symptoms (created_at, description, source) VALUES ('2026-10-30T09:10:00', 'My knee is sore', 'diary')")
    connection.execute("INSERT INTO memories (created_at, updated_at, conversation_id, her_words, talk, title, story, scene, "
                       "status, picture, photo) VALUES ('2026-10-30T15:00:00', '2026-10-30T15:00:00', 'day', 'the lake', '[]', "
                       "'The lake', '[\"We went to the lake.\"]', 'A lake', 'ready', '1.webp', 'photo-1.jpg')")
    connection.execute("INSERT INTO family_accounts (created_at, name, email, password_hash, salt) VALUES "
                       "('2026-10-30T10:00:00', 'Maria', 'maria@example.com', X'00', X'00')")
    connection.execute("INSERT INTO family_sessions (account_id, token_hash, created_at, expires_at) VALUES (1, 'abc', '', '2027-01-01T00:00:00')")
    connection.commit()
    connection.close()
    pictures = memories.pictures_dir()
    pictures.mkdir(parents=True, exist_ok=True)
    (pictures / "1.webp").write_bytes(b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24)
    (pictures / "photo-1.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 24)
    backup = Path(safe_test_setup).parent / "backup-20261029-120000.db"
    backup.write_bytes(b"old")
    return {"db": Path(safe_test_setup), "pictures": pictures, "backup": backup}


# ---------- Export everything ----------

def test_export_is_one_zip_with_her_database_and_pictures(client, her_data):
    answer = client.get("/api/data/export")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/zip"
    assert answer.headers["content-disposition"].startswith('attachment; filename="grandma-buddy-')
    with zipfile.ZipFile(io.BytesIO(answer.content)) as packed:
        names = set(packed.namelist())
        assert {"grandma-buddy.db", "memories/1.webp", "memories/photo-1.jpg", "README.txt"} <= names
        readme = packed.read("README.txt").decode("utf-8")
        assert "grandma-buddy.db" in readme and "SQLite" in readme
        # The database in the zip is a real copy with her rows.
        copy = Path(her_data["db"]).parent / "unpacked.db"
        copy.write_bytes(packed.read("grandma-buddy.db"))
    unpacked = sqlite3.connect(copy)
    assert unpacked.execute("SELECT description FROM symptoms").fetchone()[0] == "My knee is sore"
    assert unpacked.execute("SELECT preferred_name FROM profile").fetchone()[0] == "Rose"
    unpacked.close()


def test_export_never_takes_the_env_file_or_backups(client, her_data):
    (her_data["db"].parent / ".env").write_text("MODEL_API_KEY=not-really\n", encoding="utf-8")
    with zipfile.ZipFile(io.BytesIO(client.get("/api/data/export").content)) as packed:
        assert not any(".env" in name or "backup" in name for name in packed.namelist())


# ---------- Delete everything ----------

def test_delete_needs_the_word_delete_typed_exactly(client, her_data):
    for wrong in ({}, {"confirm": "delete"}, {"confirm": "DELETE EVERYTHING"}, {"confirm": ""}):
        refused = client.post("/api/data/delete", json=wrong)
        assert refused.status_code == 400, wrong
    connection = db.get_connection(str(her_data["db"]))
    assert connection.execute("SELECT COUNT(*) FROM symptoms").fetchone()[0] == 1, "nothing was deleted"
    connection.close()


def test_delete_everything_leaves_an_empty_app(client, her_data):
    answer = client.post("/api/data/delete", json={"confirm": "DELETE"})
    assert answer.status_code == 200 and answer.json() == {"ok": True}
    connection = db.get_connection(str(her_data["db"]))
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    assert tables, "the tables are still there, empty, so the app keeps working"
    for table in tables:
        assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert connection.execute("SELECT COUNT(*) FROM sqlite_sequence").fetchone()[0] == 0, "ids start from 1 again"
    connection.close()
    # Her pictures and photos, and old backups, are gone too.
    assert not any(her_data["pictures"].iterdir()) if her_data["pictures"].exists() else True
    assert not her_data["backup"].exists()
    # The app is as on the first day: no name, so it opens on the welcome.
    assert client.get("/api/profile").json()["preferred_name"] == ""
    assert client.get("/api/family/me").json() == {"signed_in": False}


def test_delete_shrinks_the_file(client, her_data):
    connection = db.get_connection(str(her_data["db"]))
    connection.executemany("INSERT INTO messages (conversation_id, created_at, role, content) VALUES ('d', '', 'user', ?)",
                           [("x" * 1000,) for _ in range(500)])
    connection.commit()
    connection.close()
    before = her_data["db"].stat().st_size
    client.post("/api/data/delete", json={"confirm": "DELETE"})
    assert her_data["db"].stat().st_size < before, "VACUUM gives the space back"


def test_another_website_cant_delete_or_export(client, her_data):
    cross = {"Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/data/delete", json={"confirm": "DELETE"}, headers=cross).status_code == 403
    assert client.get("/api/data/export", headers=cross).status_code == 403


# ---------- The installable app ----------

def test_the_service_worker_is_served_from_the_root_and_never_caches_api(client):
    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert worker.headers["content-type"].startswith("text/javascript")
    assert worker.headers["cache-control"] == "no-cache"
    assert 'NEVER_CACHED = "/api/"' in worker.text, "her data and the AI are never served from a cache"


def test_the_manifest_names_icons_that_exist(client):
    manifest = client.get("/static/manifest.webmanifest")
    assert manifest.status_code == 200
    listed = json.loads(manifest.text)
    assert listed["name"] == "Grandma Buddy" and listed["display"] == "standalone" and listed["start_url"] == "/"
    sizes = set()
    for icon in listed["icons"]:
        assert (STATIC_DIR / icon["src"].lstrip("/").removeprefix("static/")).is_file(), icon["src"]
        sizes.add(icon["sizes"])
    assert {"192x192", "512x512"} <= sizes
    assert any(icon.get("purpose") == "maskable" for icon in listed["icons"])


def test_the_page_installs_and_registers_the_worker():
    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert 'rel="manifest"' in index and 'rel="apple-touch-icon"' in index
    assert "serviceWorker" in (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert (STATIC_DIR / "offline.html").is_file()
