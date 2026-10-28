# Tests for Buddy's replies (app/companion.py and /api/chat after the
# safety net). The AI is always FAKE here: scripted answers, checked as
# strictly as Meta checks real ones. No test ever reaches the real API.

import json

import pytest
from fastapi.testclient import TestClient

from app import companion, db, meta_client
from app.main import app


def reply(text):
    """A fake AI answer with words and no tool calls."""
    return {"content": text, "tool_calls": [], "message": {"role": "assistant", "content": text}}


def tool_call(call_id, name, args):
    """A fake AI answer that asks to run one tool."""
    call = {"id": call_id, "name": name, "arguments": json.dumps(args)}
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}],
    }
    return {"content": None, "tool_calls": [call], "message": message}


class FakeAI:
    """Plays back scripted answers and checks message order like Meta does."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, messages, tools=None, tool_choice=None):
        self.calls.append([dict(m) for m in messages])
        # Meta's rule: an assistant message with tool_calls must be followed
        # by one tool message per call id before anything else.
        for i, message in enumerate(messages):
            for call in message.get("tool_calls") or []:
                assert any(
                    m.get("role") == "tool" and m.get("tool_call_id") == call["id"] for m in messages[i + 1:]
                ), "a tool call was not answered"
        return self.answers.pop(0)


@pytest.fixture
def client():
    return TestClient(app)


def use_fake(monkeypatch, *answers):
    fake = FakeAI(*answers)
    monkeypatch.setattr(meta_client, "chat", fake)
    return fake


def chat(client, text, mode="chat"):
    return client.post("/api/chat", json={"conversation_id": "day1", "text": text, "mode": mode}).json()


def test_a_normal_reply_is_returned_and_remembered(client, monkeypatch, safe_test_setup):
    use_fake(monkeypatch, reply("That sounds like a lovely day. What did you do?"))
    body = chat(client, "I went to the garden")
    assert body["reply"] == "That sounds like a lovely day. What did you do?"
    assert body["show"] is None
    connection = db.get_connection(safe_test_setup)
    roles = [r["role"] for r in connection.execute("SELECT role FROM messages ORDER BY id")]
    connection.close()
    assert roles == ["user", "assistant"]


def test_the_prompt_forbids_advice_and_knows_her_people(client, monkeypatch):
    client.put("/api/profile", json={"preferred_name": "Rose", "family_name": "Maria", "doctor_name": "Dr. Lee"})
    fake = use_fake(monkeypatch, reply("Hello Rose!"))
    chat(client, "hello")
    prompt = fake.calls[0][0]
    assert prompt["role"] == "developer"
    for must_say in ["medical advice", "Rose", "Maria", "Dr. Lee", "AI helper", "one question"]:
        assert must_say in prompt["content"], must_say


def test_advice_from_the_ai_is_swapped_for_the_fixed_reply(client, monkeypatch):
    client.put("/api/profile", json={"doctor_name": "Dr. Lee", "doctor_phone": "555-0199"})
    use_fake(monkeypatch, reply("You could take 200 mg of ibuprofen."))
    body = chat(client, "my back hurts, can I take something?")
    assert body["reply"].startswith("I'm sorry, I can't give medical advice.")
    hrefs = [a.get("href") for a in body["actions"]]
    assert "tel:555-0199" in hrefs
    assert any(a["type"] == "add_question" for a in body["actions"])


def test_asking_for_advice_always_offers_doctor_family_and_notes(client, monkeypatch):
    client.put("/api/profile", json={"family_name": "Maria", "family_phone": "555-0100", "doctor_phone": "555-0199"})
    use_fake(monkeypatch, reply("I'm sorry, I can't give medical advice. Your doctor is the right person for that."))
    body = chat(client, "should I go to the doctor?")
    hrefs = [a.get("href") for a in body["actions"]]
    assert "tel:555-0199" in hrefs and "tel:555-0100" in hrefs
    assert body["actions"][-1]["type"] == "add_question"


def test_side_effects_add_the_fixed_line_and_a_diary_entry(client, monkeypatch, safe_test_setup):
    use_fake(monkeypatch, reply("I'm sorry, I can't give medical advice."))
    body = chat(client, "should I stop my blood pressure pills? they make me dizzy")
    assert "Please call your doctor or pharmacist today and tell them." in body["reply"]
    connection = db.get_connection(safe_test_setup)
    diary = connection.execute("SELECT description FROM symptoms").fetchall()
    connection.close()
    assert diary[0]["description"] == "should I stop my blood pressure pills? they make me dizzy"


def test_log_symptom_saves_her_own_words_not_the_ais(client, monkeypatch, safe_test_setup):
    use_fake(
        monkeypatch,
        reply("I'm sorry it hurts. Where is it?"),
        tool_call("c1", "log_symptom", {"body_area": "knee", "pain_level": 5, "since": "Tuesday", "summary": "Patient reports gonalgia"}),
        reply("I've written that down for your doctor."),
    )
    chat(client, "my knee hurts when I walk", mode="diary")
    body = chat(client, "about a 5, since Tuesday", mode="diary")
    assert body["reply"] == "I've written that down for your doctor."
    connection = db.get_connection(safe_test_setup)
    row = connection.execute("SELECT description, body_area, pain_level, since, source FROM symptoms").fetchone()
    connection.close()
    assert row["description"] == "my knee hurts when I walk. about a 5, since Tuesday"
    assert "gonalgia" not in row["description"]
    assert (row["body_area"], row["pain_level"], row["since"], row["source"]) == ("knee", 5, "Tuesday", "diary")


def test_bad_tool_calls_are_still_answered_and_the_loop_stops(client, monkeypatch):
    use_fake(
        monkeypatch,
        tool_call("a", "no_such_tool", {}),
        tool_call("b", "log_mood", {"mood": "fantastic"}),  # not an allowed mood
        tool_call("c", "log_mood", {"mood": "good"}),
        reply("Glad to hear it!"),  # the forced final answer after 3 rounds
    )
    body = chat(client, "I feel good")
    assert body["reply"] == "Glad to hear it!"


def test_call_buttons_tool_only_uses_numbers_that_exist(client, monkeypatch):
    client.put("/api/profile", json={"family_name": "Maria", "family_phone": "555-0100"})
    use_fake(monkeypatch, tool_call("c1", "show_call_buttons", {"who": "both"}), reply("Here are the buttons."))
    body = chat(client, "I'd like to talk to someone")
    assert [a["href"] for a in body["actions"] if a["type"] == "call"] == ["tel:555-0100"]


def test_after_a_crisis_buddy_stays_gentle_and_988_stays_visible(client, monkeypatch):
    client.put("/api/profile", json={"family_name": "Maria", "family_phone": "555-0100"})
    chat(client, "I want to die")  # the safety net answers; no AI
    fake = use_fake(monkeypatch, reply("I'm here with you."))
    body = chat(client, "thank you")
    assert "gentle" in fake.calls[0][0]["content"].lower()
    hrefs = [a.get("href") for a in body["actions"]]
    assert "tel:988" in hrefs and "tel:555-0100" in hrefs


def test_a_repeated_crisis_phrase_is_never_suppressed(client, monkeypatch):
    chat(client, "I want to die")
    use_fake(monkeypatch)  # any AI call would fail: no answers scripted
    assert chat(client, "I still want to die")["show"] == "crisis"


def test_buddy_remembers_earlier_days(client, monkeypatch):
    fake = use_fake(monkeypatch, reply("What a lovely name."), reply("I remember Lily!"))
    client.post("/api/chat", json={"conversation_id": "yesterday", "text": "my granddaughter is Lily", "mode": "chat"})
    chat(client, "do you remember her name?")  # a new day's conversation
    contents = [m.get("content") for m in fake.calls[1]]
    assert "my granddaughter is Lily" in contents


def test_when_the_ai_fails_she_gets_a_kind_message(client, monkeypatch):
    def broken(*args, **kwargs):
        raise meta_client.MetaError("chat failed with HTTP 500")

    monkeypatch.setattr(meta_client, "chat", broken)
    body = chat(client, "hello")
    assert body["reply"] and "error" not in body["reply"].lower()


def test_doctor_questions_are_saved(client, safe_test_setup):
    saved = client.post("/api/doctor-questions", json={"question": "Should I take something for my knee?"})
    assert saved.status_code == 200
    connection = db.get_connection(safe_test_setup)
    row = connection.execute("SELECT question FROM doctor_questions").fetchone()
    connection.close()
    assert row["question"] == "Should I take something for my knee?"
    assert client.post("/api/doctor-questions", json={"question": " "}).status_code == 400


def test_a_reply_with_no_words_is_asked_again_then_gets_a_gentle_fallback(monkeypatch):
    # First: empty, then the retry has words.
    monkeypatch.setattr(meta_client, "chat", FakeAI(reply(""), reply("I'm here with you.")))
    connection = db.get_connection()
    profile = db.get_profile(connection)
    db.save_message(connection, "x", "user", "hello")
    assert companion.answer(connection, profile, "x", "hello", "chat")["reply"] == "I'm here with you."
    # Both empty: a gentle fixed line instead of silence.
    monkeypatch.setattr(meta_client, "chat", FakeAI(reply(""), reply("")))
    assert companion.answer(connection, profile, "x", "hello", "chat")["reply"] == companion.EMPTY_REPLY
    connection.close()
