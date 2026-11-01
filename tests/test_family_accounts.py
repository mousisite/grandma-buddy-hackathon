# Tests for family accounts and the family page (docs/SPEC.md feature 18):
# an invite code from Rose's Settings, a password that is never stored,
# a session cookie, five tries then a 15-minute wait, and a dashboard that
# shows only what Rose shares, with safety screens as a kind and a time
# only, never her words. No Meta here at all. Made-up data only.

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import accounts, db, reminders
from app.main import app

NOW = datetime(2026, 10, 30, 19, 30)  # Friday evening
MARIA = {"name": "Maria", "email": "maria@example.com", "password": "rose-garden-2026"}


@pytest.fixture
def clock(monkeypatch):
    state = {"now": NOW}
    monkeypatch.setattr(reminders, "current_time", lambda: state["now"])
    accounts.forget_tries()  # wrong passwords from an earlier test
    return state


@pytest.fixture
def client(clock):
    return TestClient(app)


@pytest.fixture
def connection(safe_test_setup):
    opened = db.get_connection(safe_test_setup)
    db.get_profile(opened)  # the one profile row exists from here on
    opened.execute("UPDATE profile SET preferred_name = 'Rose', family_name = 'Maria' WHERE id = 1")
    opened.commit()
    yield opened
    opened.close()


def invite(client) -> str:
    return client.post("/api/family/invite").json()["code"]


def join(client, **changes) -> object:
    return client.post("/api/family/account", json={"code": invite(client), **MARIA, **changes})


# ---------- Invites ----------

def test_an_invite_code_is_six_easy_letters_good_for_a_day(client, connection):
    answer = client.post("/api/family/invite").json()
    assert len(answer["code"]) == 6 and set(answer["code"]) <= set(accounts.INVITE_LETTERS)
    assert not set(answer["code"]) & set("IO01"), "no letters that look like numbers"
    assert answer["expires_at"] == "2026-10-31T19:30:00"


def test_an_invite_code_works_once(client, connection):
    code = invite(client)
    assert client.post("/api/family/account", json={"code": code, **MARIA}).status_code == 200
    again = client.post("/api/family/account", json={"code": code, "name": "Daniel", "email": "daniel@example.com",
                                                     "password": "another-good-one"})
    assert again.status_code == 400 and "code" in again.json()["detail"]["message"].lower()


def test_an_old_invite_code_is_refused(client, clock, connection):
    code = invite(client)
    clock["now"] = NOW + timedelta(hours=25)
    assert client.post("/api/family/account", json={"code": code, **MARIA}).status_code == 400


def test_a_wrong_code_is_refused_kindly(client, connection):
    refused = client.post("/api/family/account", json={"code": "ABCDEF", **MARIA})
    assert refused.status_code == 400
    assert refused.json()["detail"] == {"field": "code", "message": "That code didn’t work. Ask for a new one in Buddy’s Settings."}


# ---------- Joining ----------

def test_joining_signs_her_in_with_a_cookie_only_the_server_can_read(client, connection):
    answer = join(client)
    assert answer.status_code == 200 and answer.json() == {"name": "Maria", "email": "maria@example.com"}
    cookie = answer.headers["set-cookie"]
    assert "buddy_family=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie.replace("Lax", "lax")
    assert client.get("/api/family/me").json() == {"signed_in": True, "name": "Maria", "email": "maria@example.com"}


def test_the_password_is_never_stored(client, connection):
    join(client)
    rows = [json.dumps([str(value) for value in row]) for row in connection.execute("SELECT * FROM family_accounts")]
    assert rows and all(MARIA["password"] not in row for row in rows)


@pytest.mark.parametrize("changes, field", [
    ({"password": "short"}, "password"),
    ({"email": "not-an-email"}, "email"),
    ({"name": ""}, "name"),
])
def test_a_bad_entry_is_named(client, connection, changes, field):
    refused = join(client, **changes)
    assert refused.status_code == 400 and refused.json()["detail"]["field"] == field


def test_an_email_can_join_only_once(client, connection):
    join(client)
    again = join(client)
    assert again.status_code == 400 and again.json()["detail"]["field"] == "email"


# ---------- Signing in ----------

def test_signing_in_and_out(client, connection):
    join(client)
    client.post("/api/family/sign-out")
    # "Am I signed in?" is a plain question, not an error (so the browser logs nothing).
    assert client.get("/api/family/me").json()["signed_in"] is False
    signed_in = client.post("/api/family/sign-in", json={"email": MARIA["email"], "password": MARIA["password"]})
    assert signed_in.status_code == 200 and signed_in.json()["name"] == "Maria"
    assert client.get("/api/family/me").json()["signed_in"] is True


def test_a_wrong_password_is_refused_and_five_tries_lock_for_fifteen_minutes(client, clock, connection):
    join(client)
    client.post("/api/family/sign-out")
    for _ in range(5):
        wrong = client.post("/api/family/sign-in", json={"email": MARIA["email"], "password": "not-it"})
        assert wrong.status_code == 401
    locked = client.post("/api/family/sign-in", json={"email": MARIA["email"], "password": MARIA["password"]})
    assert locked.status_code == 429 and "15 minutes" in locked.json()["detail"]
    clock["now"] = NOW + timedelta(minutes=16)
    assert client.post("/api/family/sign-in", json={"email": MARIA["email"], "password": MARIA["password"]}).status_code == 200


def test_a_session_ends_after_thirty_days(client, clock, connection):
    join(client)
    clock["now"] = NOW + timedelta(days=31)
    assert client.get("/api/family/me").json()["signed_in"] is False


def test_removing_an_account_from_roses_settings_ends_its_session(client, connection):
    join(client)
    listed = client.get("/api/family/accounts").json()
    assert [account["name"] for account in listed] == ["Maria"]
    assert client.delete(f"/api/family/accounts/{listed[0]['id']}").status_code == 200
    assert client.get("/api/family/me").json()["signed_in"] is False
    assert client.get("/api/family/accounts").json() == []


def test_another_website_cant_sign_in_or_ask_for_her_day(client, connection):
    join(client)
    cross = {"Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/family/sign-in", json=MARIA, headers=cross).status_code == 403
    assert client.get("/api/family/dashboard", headers=cross).status_code == 403


# ---------- Her day, as she shares it ----------

def add_day(connection, clock):
    """A made-up Friday: a check-in, two pills (one taken, one missed), a
    diary note, and an emergency screen whose words must never be shown."""
    day = clock["now"].date().isoformat()
    connection.execute("INSERT INTO moods (created_at, mood, note) VALUES (?, 'good', 'pretty good')", (f"{day}T09:00:00",))
    connection.execute("INSERT INTO medications (name, label_dose, times, created_at, active) VALUES "
                       "('Metformin', '500 mg tablet', '[\"08:00\", \"18:00\"]', ?, 1)", (f"{day}T07:00:00",))
    pill = connection.execute("SELECT id FROM medications").fetchone()["id"]
    connection.execute("INSERT INTO med_events (medication_id, due_at, status, acted_at) VALUES (?, ?, 'taken', ?)",
                       (pill, f"{day}T08:00:00", f"{day}T08:05:00"))
    connection.execute("INSERT INTO med_events (medication_id, due_at, status) VALUES (?, ?, 'pending')",
                       (pill, f"{day}T16:00:00"))  # 3.5 hours ago with no answer: missed
    connection.execute("INSERT INTO symptoms (created_at, description, body_area, source) VALUES "
                       "(?, 'My knee is stiff this morning', 'knee', 'check_in')", (f"{day}T09:10:00",))
    db.add_safety_event(connection, "emergency", ["chest"], "my chest feels tight")
    connection.execute("UPDATE safety_events SET created_at = ?", (f"{day}T14:00:00",))
    connection.execute("INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, 'user', 'Hello Buddy', ?)",
                       (day, f"{day}T09:00:00"))
    connection.commit()


def test_the_dashboard_needs_a_signed_in_family_member(client, connection):
    assert client.get("/api/family/dashboard").status_code == 401


def test_the_dashboard_shows_her_day_as_she_shares_it(client, clock, connection):
    add_day(connection, clock)
    join(client)
    day = client.get("/api/family/dashboard").json()
    assert day["her_name"] == "Rose" and day["day_words"] == "Friday, October 30"
    assert day["shares"] == {"mood": True, "pills": True, "diary": False, "safety": True}
    assert day["mood"] == {"words": "Good", "time": "9:00 AM"}
    assert day["pills"] == {"taken": 1, "total": 2,
                            "not_taken": [{"name": "Metformin", "time": "4:00 PM", "state": "Missed"}]}
    assert day["diary"] is None, "her diary is hers until she shares it"
    assert day["talked"] == {"yes": True, "last_time": "9:00 AM"}
    # A safety screen: its kind and time with a fixed sentence, never her words.
    assert day["safety"] == [{"time": "2:00 PM", "words": "Buddy showed the emergency screen (call 911). Please call her."}]
    assert "chest" not in json.dumps(day)
    assert [alert["words"] for alert in day["alerts"]] == [
        "Buddy showed the emergency screen (call 911). Please call her.",
        "Missed: Metformin at 4:00 PM",
    ]


def test_rose_can_share_her_diary_and_hide_her_mood(client, clock, connection):
    add_day(connection, clock)
    join(client)
    assert client.put("/api/profile", json={"share_diary": True, "share_mood": False}).status_code == 200
    day = client.get("/api/family/dashboard").json()
    assert day["mood"] is None
    assert day["diary"] == [{"time": "9:10 AM", "words": "My knee is stiff this morning", "quoted": True, "note": "From the daily check-in."}]


def test_an_emergency_entry_in_her_diary_reaches_the_family_as_the_fixed_sentence(client, clock, connection):
    # The words that showed an emergency screen go in her diary (for her
    # doctor), but a safety screen is never her words on the family page.
    add_day(connection, clock)
    day = clock["now"].date().isoformat()
    connection.execute("INSERT INTO symptoms (created_at, description, body_area, source) VALUES (?, 'my chest feels tight', '', 'safety_net')",
                       (f"{day}T14:00:00",))
    connection.commit()
    join(client)
    client.put("/api/profile", json={"share_diary": True})
    facts = client.get("/api/family/dashboard").json()
    assert facts["diary"][-1] == {"time": "2:00 PM", "words": "Buddy showed the emergency screen.", "quoted": False, "note": ""}
    assert "chest" not in json.dumps(facts)


def test_memory_book_titles_are_shared_with_her_diary(client, clock, connection):
    day = clock["now"].date().isoformat()
    connection.execute("INSERT INTO memories (created_at, updated_at, conversation_id, her_words, talk, title, story, scene, status) "
                       "VALUES (?, ?, 'demo', 'the farm', '[]', 'Summers at the farm', '[]', '', 'ready')",
                       (f"{day}T15:00:00", f"{day}T15:00:00"))
    connection.commit()
    join(client)
    assert client.get("/api/family/dashboard").json()["memories"] is None, "her stories are hers, like her diary"
    client.put("/api/profile", json={"share_diary": True})
    assert client.get("/api/family/dashboard").json()["memories"] == ["Summers at the farm"]


def test_yesterday_and_an_empty_day(client, clock, connection):
    add_day(connection, clock)
    join(client)
    yesterday = client.get("/api/family/dashboard?date=2026-10-29").json()
    assert yesterday["day_words"] == "Thursday, October 29"
    assert yesterday["mood"] is None and yesterday["pills"]["total"] == 0 and yesterday["alerts"] == []
    assert yesterday["talked"] == {"yes": False, "last_time": ""}
    assert client.get("/api/family/dashboard?date=2026-12-01").status_code == 400  # not yet
    assert client.get("/api/family/dashboard?date=2026-09-01").status_code == 400  # too long ago


def test_the_family_page_is_served(client):
    page = client.get("/family")
    assert page.status_code == 200 and "<title>" in page.text and page.headers["cache-control"] == "no-cache"
