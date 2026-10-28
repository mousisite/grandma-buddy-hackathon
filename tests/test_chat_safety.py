# Tests for /api/chat's first job: the safety net runs before anything else,
# in every mode, and an emergency, Poison Control, or crisis match returns
# the fixed screen without ever calling the AI. Also /api/profile.

import pytest
from fastapi.testclient import TestClient

from app import db, meta_client
from app.main import app


@pytest.fixture
def client(monkeypatch):
    # If anything tried to ask the AI, this would fail the test.
    def ai_must_not_run(*args, **kwargs):
        raise AssertionError("The AI was called, but the safety net should have answered.")

    monkeypatch.setattr(meta_client, "chat", ai_must_not_run, raising=False)
    return TestClient(app)


def set_family(client):
    client.put("/api/profile", json={"family_name": "Maria", "family_phone": "555-0100"})


@pytest.mark.parametrize("mode", ["chat", "check_in", "diary"])
def test_emergency_words_get_the_fixed_screen_in_every_mode(client, mode):
    set_family(client)
    response = client.post("/api/chat", json={"conversation_id": "t1", "text": "my chest feels really tight", "mode": mode})
    assert response.status_code == 200
    body = response.json()
    assert body["show"] == "emergency"
    assert body["reply"] == "This could be an emergency. If it is, please call 911 right now."
    assert [a["href"] for a in body["actions"]] == ["tel:911", "tel:555-0100"]


def test_emergency_is_saved_as_a_safety_event_and_a_diary_entry(client, safe_test_setup):
    client.post("/api/chat", json={"conversation_id": "t2", "text": "I fell and hit my head", "mode": "chat"})
    connection = db.get_connection(safe_test_setup)
    events = connection.execute("SELECT kind FROM safety_events").fetchall()
    diary = connection.execute("SELECT description, source FROM symptoms").fetchall()
    connection.close()
    assert [e["kind"] for e in events] == ["emergency"]
    assert diary[0]["description"] == "I fell and hit my head"
    assert diary[0]["source"] == "safety_net"


def test_crisis_gets_the_calm_screen_with_988(client):
    set_family(client)
    body = client.post("/api/chat", json={"conversation_id": "t3", "text": "I want to die", "mode": "chat"}).json()
    assert body["show"] == "crisis"
    assert body["reply"].endswith("Would you like to call Maria too?")
    assert "tel:988" in [a["href"] for a in body["actions"]]


def test_poison_control_screen(client):
    body = client.post("/api/chat", json={"conversation_id": "t4", "text": "I took my pills twice by accident", "mode": "chat"}).json()
    assert body["show"] == "poison_control"
    assert body["actions"][0]["href"] == "tel:18002221222"


def test_symptom_split_across_two_answers_still_shows_the_screen(client, monkeypatch):
    # "my chest" alone is not an emergency, so the AI may answer it ("How does it feel?").
    answers = [{"content": "How does it feel?", "tool_calls": [], "message": {"role": "assistant", "content": "How does it feel?"}}]

    def ai_answers_once(*args, **kwargs):
        if not answers:
            raise AssertionError("The AI was called, but the safety net should have answered.")
        return answers.pop(0)

    monkeypatch.setattr(meta_client, "chat", ai_answers_once)
    client.post("/api/chat", json={"conversation_id": "t5", "text": "my chest", "mode": "diary"})
    # "tight" completes it: the safety net answers, and the AI is not asked again.
    body = client.post("/api/chat", json={"conversation_id": "t5", "text": "tight", "mode": "diary"}).json()
    assert body["show"] == "emergency"


def test_a_very_long_message_is_still_checked(client):
    long_words = "I was telling you about my day. " * 80 + "and now my chest feels really tight"
    body = client.post("/api/chat", json={"conversation_id": "t7", "text": long_words, "mode": "chat"}).json()
    assert body["show"] == "emergency"


def test_the_safety_net_still_answers_when_the_database_is_broken(client, monkeypatch):
    import sqlite3

    def broken_database(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "get_connection", broken_database)
    body = client.post("/api/chat", json={"conversation_id": "t8", "text": "I can't breathe", "mode": "chat"}).json()
    assert body["show"] == "emergency"
    assert body["actions"][0]["href"] == "tel:911"


def test_a_pill_mix_up_with_crisis_words_also_offers_988(client):
    body = client.post("/api/chat", json={"conversation_id": "t9", "text": "I took too many pills, I want to die", "mode": "chat"}).json()
    assert body["show"] == "poison_control"
    assert "tel:988" in [a["href"] for a in body["actions"]]


def test_crisis_words_are_never_stored_in_the_diary(client, safe_test_setup):
    client.post("/api/chat", json={"conversation_id": "t10", "text": "I want to die and my chest feels tight", "mode": "chat"})
    connection = db.get_connection(safe_test_setup)
    diary = [row["description"] for row in connection.execute("SELECT description FROM symptoms")]
    excerpts = [row["excerpt"] for row in connection.execute("SELECT excerpt FROM safety_events")]
    connection.close()
    assert diary and all("die" not in text for text in diary)
    assert all("die" not in text for text in excerpts)


def test_empty_or_unknown_input_is_refused_kindly(client):
    assert client.post("/api/chat", json={"conversation_id": "t6", "text": "  ", "mode": "chat"}).status_code == 400
    assert client.post("/api/chat", json={"conversation_id": "t6", "text": "hi", "mode": "party"}).status_code == 400


def test_profile_starts_empty_and_saves_what_the_family_enters(client):
    assert client.get("/api/profile").json()["family_name"] == ""
    saved = client.put("/api/profile", json={"preferred_name": "Rose", "family_name": "Maria", "family_phone": "555-0100"}).json()
    assert saved["preferred_name"] == "Rose" and saved["family_phone"] == "555-0100"
    assert client.get("/api/profile").json()["family_name"] == "Maria"


def test_profile_rejects_odd_values(client):
    assert client.put("/api/profile", json={"family_phone": "call me maybe"}).status_code == 400
    assert client.put("/api/profile", json={"family_phone": "()"}).status_code == 400  # no digits
    assert client.put("/api/profile", json={"family_phone": ""}).status_code == 200    # clearing is fine
    assert client.put("/api/profile", json={"voice_rate": 9}).status_code == 400
    assert client.put("/api/profile", json={"preferred_name": "x" * 200}).status_code == 400
