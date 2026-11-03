# Tests for the demo week (app/demo.py): it is built relative to today, her
# daily pills keep repeating on the days after it was seeded, it can be
# reset from Settings in demo mode only, and a judge can try the family
# page as Maria in demo mode. Made-up data only; Meta is never called.

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import accounts, db, demo, memories, reminders
from app.main import app

SEEDED = datetime(2026, 10, 31, 15, 0)
NEXT_DAY = datetime(2026, 11, 1, 15, 0)


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = SEEDED

    clock = Clock()
    monkeypatch.setattr(reminders, "current_time", lambda: clock.now)
    accounts.forget_tries()
    return clock


@pytest.fixture
def seeded(safe_test_setup, clock):
    connection = db.get_connection(safe_test_setup)
    demo.seed(connection, SEEDED)
    connection.commit()
    connection.close()
    return safe_test_setup


def test_the_demo_week_ends_today_with_this_mornings_pills_taken(seeded, clock):
    client = TestClient(app)
    today = client.get("/api/reminders").json()
    assert [(r["name"], r["due_at"][11:16], r["status"]) for r in today["reminders"]] == [
        ("Lisinopril", "08:00", "taken"), ("Metformin", "08:00", "taken"), ("Metformin", "18:00", "upcoming")]
    assert client.get("/api/check-in").json()["done"] is True
    assert any(entry["description"] == "My knee feels much better today" for entry in client.get("/api/diary?days=7").json())
    assert client.get("/api/messages").json()["unread"] == 1
    postcard = client.get("/api/postcard/today").json()["postcard"]
    assert postcard["sentence"].startswith("The tulips came up this morning") and postcard["shared"] is False


def test_the_day_after_the_seed_her_daily_pills_are_still_there(seeded, clock):
    # Nobody opened Buddy this morning: the 8 AM doses were never marked, so
    # they show as not taken, and tonight's is still to come.
    clock.now = NEXT_DAY
    client = TestClient(app)
    today = client.get("/api/reminders").json()
    assert [(r["name"], r["due_at"][11:16], r["status"]) for r in today["reminders"]] == [
        ("Lisinopril", "08:00", "missed"), ("Metformin", "08:00", "missed"), ("Metformin", "18:00", "upcoming")]
    update = client.get("/api/family/summary?date=2026-11-01").json()["text"]
    assert "Pills: 0 of 3 taken. Missed: Lisinopril at 8:00 AM, Metformin at 8:00 AM. Still to come: Metformin at 6:00 PM." in update


def test_a_pill_added_today_never_counts_as_not_taken_for_a_time_that_passed(seeded, clock):
    clock.now = NEXT_DAY
    client = TestClient(app)
    added = client.post("/api/meds", json={"name": "Vitamin D", "label_dose": "1 softgel daily", "times": ["08:00", "20:00"]})
    assert added.status_code == 200
    today = client.get("/api/reminders").json()
    assert [(r["name"], r["due_at"][11:16], r["status"]) for r in today["reminders"] if r["name"] == "Vitamin D"] == [
        ("Vitamin D", "20:00", "upcoming")]


def test_reset_starts_the_week_over_in_demo_mode_only(seeded, clock, monkeypatch):
    from app import memories
    monkeypatch.setattr(memories, "make_page", lambda page: None)  # the paintings: a background job, never here
    client = TestClient(app)
    assert client.get("/api/demo").json() == {"demo": True, "seeded": True, "public": False}
    client.post("/api/messages", json={"text": "A message that the reset will clear"})
    answer = client.post("/api/demo/reset")
    assert answer.status_code == 200 and answer.json()["backup"].startswith("backup-")
    assert client.get("/api/messages").json()["unread"] == 1  # the week again, Maria's message new
    assert "the reset will clear" not in str(client.get("/api/messages").json())
    # With a Stripe test key the app is not in demo mode: no reset, no demo sign-in.
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")  # settings are read fresh on every call
    assert client.get("/api/demo").json()["demo"] is False
    assert client.post("/api/demo/reset").status_code == 404
    assert client.post("/api/family/demo-sign-in").status_code == 404


def test_a_judge_can_try_the_family_page_as_maria_in_demo_mode(seeded, clock):
    client = TestClient(app)
    me = client.get("/api/family/me").json()
    assert me == {"signed_in": False, "demo": True, "demo_account": True}
    answer = client.post("/api/family/demo-sign-in")
    assert answer.status_code == 200 and answer.json() == {"name": "Maria", "email": "maria@example.com"}
    assert client.get("/api/family/me").json()["signed_in"] is True
    day = client.get("/api/family/dashboard").json()
    assert day["her_name"] == "Rose" and day["messages"]


def test_without_the_demo_account_there_is_nothing_to_try(safe_test_setup, clock):
    client = TestClient(app)
    assert client.get("/api/family/me").json() == {"signed_in": False, "demo": True, "demo_account": False}
    assert client.post("/api/family/demo-sign-in").status_code == 404
    assert client.get("/api/demo").json() == {"demo": True, "seeded": False, "public": False}


def test_the_demo_week_comes_with_its_pictures(safe_test_setup, clock):
    """The three Memory book paintings are bundled (scripts/demo_pictures/),
    so a fresh install or a public demo never paints: nothing to paint comes
    back, every page is ready, and its picture file is there."""
    connection = db.get_connection(safe_test_setup)
    to_paint = demo.seed(connection, clock.now)
    connection.commit()
    pages = connection.execute("SELECT id, status, picture FROM memories ORDER BY id").fetchall()
    assert to_paint == []
    assert [page["status"] for page in pages] == ["ready", "ready", "ready"]
    for page in pages:
        assert page["picture"] == f"{page['id']}.webp"
        assert (memories.pictures_dir() / page["picture"]).stat().st_size > 10_000
    connection.close()


def test_the_demo_week_can_be_painted_fresh_instead(safe_test_setup, clock):
    connection = db.get_connection(safe_test_setup)
    to_paint = demo.seed(connection, clock.now, pictures=False)
    connection.commit()
    assert len(to_paint) == 3
    assert [row["status"] for row in connection.execute("SELECT status FROM memories")] == ["no_picture"] * 3
    connection.close()


# ---------- The first start: the demo week, or a real person ----------

def test_the_first_start_choice_is_kept_next_to_the_database(safe_test_setup):
    from pathlib import Path

    from app.config import get_settings

    assert demo.start_choice() is None
    demo.remember_choice("F")
    assert demo.start_choice() == "F"
    assert demo.choice_path() == Path(get_settings().database_path).parent / "start-choice"
    demo.remember_choice("D")
    assert demo.start_choice() == "D"


def test_start_fresh_for_a_real_person_backs_up_wipes_and_remembers(seeded, clock):
    from pathlib import Path

    client = TestClient(app)
    assert client.get("/api/demo").json()["seeded"] is True
    answer = client.post("/api/demo/fresh")
    assert answer.status_code == 200 and answer.json()["backup"].startswith("backup-")
    assert (Path(seeded).parent / answer.json()["backup"]).exists()
    assert client.get("/api/demo").json()["seeded"] is False  # Rose is gone: the welcome flow opens
    connection = db.get_connection(seeded)
    assert not demo.has_data(connection)
    connection.close()
    assert demo.start_choice() == "F"  # start.bat never loads the demo week by itself again


def test_start_fresh_is_demo_mode_only_and_never_on_the_public_demo(seeded, clock, monkeypatch):
    from app import public_demo

    client = TestClient(app)
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    refused = client.post("/api/demo/fresh")
    assert refused.status_code == 403 and refused.json()["detail"] == public_demo.NO_DATA_CHANGES
    assert client.get("/api/demo").json()["seeded"] is True  # the week stays
    monkeypatch.delenv("PUBLIC_DEMO")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")  # not demo mode: nothing to clear
    assert client.post("/api/demo/fresh").status_code == 404


def test_reset_remembers_that_the_demo_week_was_chosen(seeded, clock, monkeypatch):
    monkeypatch.setattr(memories, "make_page", lambda page: None)
    demo.remember_choice("F")
    assert TestClient(app).post("/api/demo/reset").status_code == 200
    assert demo.start_choice() == "D"
