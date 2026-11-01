# Tests for the demo week (app/demo.py): it is built relative to today, her
# daily pills keep repeating on the days after it was seeded, it can be
# reset from Settings in demo mode only, and a judge can try the family
# page as Maria in demo mode. Made-up data only; Meta is never called.

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import accounts, db, demo, reminders
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
    assert client.get("/api/demo").json() == {"demo": True, "seeded": True}
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
    assert client.get("/api/demo").json() == {"demo": True, "seeded": False}
