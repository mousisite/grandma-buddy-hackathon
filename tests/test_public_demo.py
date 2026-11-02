# Tests for the public demo (PUBLIC_DEMO=1 on a host, docs/DEPLOY.md): Rose's
# made-up week, loaded at start and put back once a night; a share of Meta's
# calls for each visitor and a cap for the day, with kind words when reached
# and never for the safety net; no invites, sign-ups, exports, or deletes;
# and none of this when Buddy runs at home. Meta is always FAKE here.

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import db, demo, meta_client, public_demo
from app.config import get_settings
from app.main import app
from tests.test_companion import reply

JUDGE = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}  # a visitor, as the host's proxy reports them
OTHER = {"x-forwarded-for": "198.51.100.7"}
HELLO = {"conversation_id": "day", "text": "hello Buddy"}


@pytest.fixture
def public(monkeypatch, safe_test_setup):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setattr(public_demo, "_visitors", {})  # the hour's counts start fresh
    return TestClient(app)


def fake_chat(monkeypatch):
    monkeypatch.setattr(meta_client, "chat", lambda messages, tools=None: reply("Lovely."))


def test_the_public_demo_is_off_unless_the_host_says_so(monkeypatch):
    assert get_settings().public_demo is False
    assert public_demo.ai_call_allowed(JUDGE, "10.0.0.2") is None  # at home nothing is counted or refused
    assert public_demo.refused("POST", "/api/family/invite") is None
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    assert get_settings().public_demo is True
    settings = get_settings()
    assert (settings.ai_calls_per_visitor_hour, settings.ai_calls_per_day, settings.demo_reset_hour) == (40, 600, 3)


def test_the_visitor_is_the_first_forwarded_address():
    assert public_demo.visitor_of(JUDGE, "10.0.0.2") == "203.0.113.5"
    assert public_demo.visitor_of({}, "10.0.0.2") == "10.0.0.2"


def test_each_visitor_gets_a_share_of_metas_calls_an_hour(public, monkeypatch):
    monkeypatch.setenv("AI_CALLS_PER_VISITOR_HOUR", "2")
    fake_chat(monkeypatch)
    for _ in range(2):
        assert public.post("/api/chat", json=HELLO, headers=JUDGE).json()["reply"] == "Lovely."
    third = public.post("/api/chat", json=HELLO, headers=JUDGE).json()
    assert third["reply"] == public_demo.VISITOR_LIMIT and third["show"] is None and third["actions"] == []
    assert public.post("/api/chat", json=HELLO, headers=OTHER).json()["reply"] == "Lovely."  # another visitor


def test_the_day_has_a_cap_for_everyone(public, monkeypatch):
    monkeypatch.setenv("AI_CALLS_PER_DAY", "1")
    fake_chat(monkeypatch)
    assert public.post("/api/chat", json=HELLO, headers=JUDGE).json()["reply"] == "Lovely."
    photo = {"thing": "my glasses", "image": "data:image/jpeg;base64,QUJD", "width": 10, "height": 10}
    answer = public.post("/api/find", json=photo, headers=OTHER)
    assert (answer.status_code, answer.json()["detail"]) == (429, public_demo.DAILY_LIMIT)


def test_the_safety_net_is_never_capped(public, monkeypatch):
    monkeypatch.setenv("AI_CALLS_PER_DAY", "0")
    answer = public.post("/api/chat", json={"conversation_id": "day", "text": "my chest feels really tight"}, headers=JUDGE).json()
    assert answer["show"] == "emergency"


def test_pages_that_need_no_ai_are_never_counted(public, monkeypatch):
    monkeypatch.setenv("AI_CALLS_PER_DAY", "0")
    assert public.get("/api/meds").status_code == 200
    assert public.get("/api/memories").status_code == 200
    assert public.get("/api/briefing/weather").status_code == 200  # Open-Meteo, not Meta


def test_the_kind_words_have_nothing_technical():
    for words in (public_demo.VISITOR_LIMIT, public_demo.DAILY_LIMIT, public_demo.NO_SIGN_UP, public_demo.NO_DATA_CHANGES):
        assert not re.search(r"error|limit|rate|quota|api|\d{3}", words, re.IGNORECASE), words


def test_no_invites_or_sign_ups_in_the_public_demo(public):
    refused = public.post("/api/family/invite", json={})
    assert (refused.status_code, refused.json()["detail"]) == (403, public_demo.NO_SIGN_UP)
    joined = public.post("/api/family/account", json={"code": "ABCDEF", "name": "X", "email": "x@example.com", "password": "secret-words"})
    assert joined.status_code == 403


def test_her_data_cant_be_taken_or_wiped_in_the_public_demo(public):
    assert public.get("/api/data/export").status_code == 403
    assert public.post("/api/data/delete", json={"confirm": "DELETE"}).status_code == 403
    assert public.get("/api/demo").json()["public"] is True


def test_the_demo_week_is_loaded_at_start_and_put_back_once_a_night(public, monkeypatch, safe_test_setup):
    resets = []
    monkeypatch.setattr(demo, "reset", lambda now=None: resets.append(now) or {"backup": "", "pages": []})
    assert public_demo.reset_if_due(datetime(2026, 11, 2, 1, 0)) is True  # an empty database: the week is loaded
    connection = db.get_connection(safe_test_setup)
    demo.seed(connection, datetime(2026, 11, 2, 1, 0))
    connection.commit()
    connection.close()
    assert public_demo.reset_if_due(datetime(2026, 11, 2, 3, 0)) is False  # done today already
    assert public_demo.reset_if_due(datetime(2026, 11, 3, 2, 59)) is False  # not yet
    assert public_demo.reset_if_due(datetime(2026, 11, 3, 3, 0)) is True  # the nightly reset
    assert public_demo.reset_if_due(datetime(2026, 11, 3, 23, 0)) is False  # once a day
    assert len(resets) == 2


def test_at_home_nothing_is_refused_or_counted(safe_test_setup, monkeypatch):
    monkeypatch.setenv("AI_CALLS_PER_DAY", "0")
    client = TestClient(app)
    assert client.get("/api/demo").json()["public"] is False
    assert client.get("/api/data/export").status_code == 200
    assert public_demo.reset_if_due(datetime(2026, 11, 2, 3, 0)) is False  # no nightly reset at home
