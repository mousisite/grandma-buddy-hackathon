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
    # In ordinary chat, "my chest" alone is not an emergency, so the AI may
    # answer it ("How does it feel?"). (In a "Something hurts" talk it would
    # already be one: see the tests at the end of this file.)
    answers = [{"content": "How does it feel?", "tool_calls": [], "message": {"role": "assistant", "content": "How does it feel?"}}]

    def ai_answers_once(*args, **kwargs):
        if not answers:
            raise AssertionError("The AI was called, but the safety net should have answered.")
        return answers.pop(0)

    monkeypatch.setattr(meta_client, "chat", ai_answers_once)
    client.post("/api/chat", json={"conversation_id": "t5", "text": "my chest", "mode": "chat"})
    # "tight" completes it: the safety net answers, and the AI is not asked again.
    body = client.post("/api/chat", json={"conversation_id": "t5", "text": "tight", "mode": "chat"}).json()
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


def test_a_refused_profile_entry_is_named_so_the_form_can_point_to_it(client):
    refused = client.put("/api/profile", json={"family_name": "Maria", "doctor_phone": "soon"})
    assert refused.status_code == 400
    assert refused.json()["detail"] == {
        "field": "doctor_phone",
        "message": "Please check the doctor’s phone number. Use numbers, like 555‑0123.",
    }
    email = client.put("/api/profile", json={"family_email": "maria at home"}).json()["detail"]
    assert email["message"] == "Please check the family email address. It looks like name@example.com."
    # Nothing is half-saved: Maria was refused along with the bad number.
    assert client.get("/api/profile").json()["family_name"] == ""


# ---------- Pain told as a place ("my chest"), and words told across talks ----------

def ai_says(monkeypatch, *texts):
    """A fake AI that may answer only these times; any other call fails the test."""
    answers = [{"content": t, "tool_calls": [], "message": {"role": "assistant", "content": t}} for t in texts]

    def fake(*args, **kwargs):
        if not answers:
            raise AssertionError("The AI was called, but the safety net should have answered.")
        return answers.pop(0)

    monkeypatch.setattr(meta_client, "chat", fake)


def post(client, text, mode="chat", conversation="t20"):
    return client.post("/api/chat", json={"conversation_id": conversation, "text": text, "mode": mode}).json()


def test_in_a_something_hurts_talk_naming_the_chest_is_enough(client):
    # She tapped "Something hurts", so "my chest" means her chest hurts.
    assert post(client, "my chest", mode="diary")["show"] == "emergency"


def test_pain_spreading_named_as_places_in_a_something_hurts_talk(client, monkeypatch):
    ai_says(monkeypatch, "I'm sorry. Is anything else different?")
    assert post(client, "my left arm and my jaw", mode="diary")["show"] is None
    assert post(client, "I feel sweaty and sick to my stomach", mode="diary")["show"] == "emergency"


def test_a_knee_in_a_something_hurts_talk_is_not_an_emergency(client, monkeypatch):
    ai_says(monkeypatch, "I'm sorry your knee hurts. How bad is it, from 0 to 10?")
    assert post(client, "my knee", mode="diary")["show"] is None


def test_after_buddy_asks_where_it_hurts_my_chest_shows_the_screen(client, monkeypatch):
    ai_says(monkeypatch, "I'm sorry you're not well. Where does it hurt?")
    post(client, "I don't feel well")
    assert post(client, "my chest")["show"] == "emergency"


def test_my_chest_in_ordinary_chat_is_not_an_emergency(client, monkeypatch):
    ai_says(monkeypatch, "Oh, what did you find?")
    assert post(client, "I found my chest of old photos")["show"] is None


def test_a_symptom_told_across_the_something_hurts_tap_still_shows_the_screen(client, monkeypatch):
    ai_says(monkeypatch, "Oh no. Tell me more?")
    post(client, "my chest", conversation="2026-10-27")
    assert post(client, "it feels tight", mode="diary", conversation="2026-10-27-diary-1")["show"] == "emergency"


def test_words_from_long_ago_are_not_joined(client, monkeypatch, safe_test_setup):
    ai_says(monkeypatch, "Oh, a new chest?", "Tight? Tell me more.")
    post(client, "I'm looking at my chest")
    connection = db.get_connection(safe_test_setup)
    connection.execute("UPDATE messages SET created_at = '2026-01-01T09:00:00'")
    connection.commit()
    connection.close()
    assert post(client, "my shoes are tight")["show"] is None


def test_crisis_words_are_never_kept_in_the_conversation_either(client, safe_test_setup):
    post(client, "I want to die")
    connection = db.get_connection(safe_test_setup)
    said = [row["content"] for row in connection.execute("SELECT content FROM messages WHERE role = 'user'")]
    connection.close()
    assert said and all("die" not in text for text in said)
