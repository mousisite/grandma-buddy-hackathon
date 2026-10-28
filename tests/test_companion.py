# Tests for Buddy's replies (app/companion.py and /api/chat after the
# safety net). The AI is always FAKE here: scripted answers, checked as
# strictly as Meta checks real ones. No test ever reaches the real API.

import json

import pytest
from fastapi.testclient import TestClient

from app import companion, db, meta_client, prompts
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

    # No tool_choice here, like the real meta_client.chat(): Meta only
    # supports "auto" and answers anything else with HTTP 400.
    def __call__(self, messages, tools=None):
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
    assert row["description"] == "my knee hurts when I walk. about a 5, since Tuesday."
    assert "gonalgia" not in row["description"]
    assert (row["body_area"], row["pain_level"], row["since"], row["source"]) == ("knee", 5, "Tuesday", "diary")


def test_a_something_hurts_talk_saves_all_her_answers_and_only_those(client, monkeypatch, safe_test_setup):
    # Each "Something hurts" talk has its own conversation id (talk.js), so
    # the entry holds every answer in it, and nothing she said before.
    use_fake(
        monkeypatch,
        reply("How lovely!"),
        reply("I'm sorry it hurts. Where is it?"),
        reply("How bad is it, from 0 to 10?"),
        reply("Since when?"),
        tool_call("c1", "log_symptom", {"body_area": "knee", "pain_level": 5, "since": "Tuesday"}),
        reply("I've written that down for your doctor."),
    )
    client.put("/api/profile", json={"family_name": "Maria", "family_phone": "555-0100", "doctor_phone": "555-0199"})
    client.post("/api/chat", json={"conversation_id": "2026-10-27", "text": "Maria is coming Sunday", "mode": "chat"})
    answers = []
    for words in ["something hurts", "my knee", "about a 5", "since Tuesday"]:
        answers.append(
            client.post("/api/chat", json={"conversation_id": "2026-10-27-diary-1", "text": words, "mode": "diary"}).json()
        )

    # The page leaves diary mode once the entry is saved.
    assert [a["diary_saved"] for a in answers] == [False, False, False, True]
    assert [a["diary_done"] for a in answers] == [False, False, False, True]
    # Call doctor and Call family always follow a saved entry, even when the
    # AI forgets show_call_buttons (the real model did, once).
    assert [a["href"] for a in answers[-1]["actions"]] == ["tel:555-0199", "tel:555-0100"]
    connection = db.get_connection(safe_test_setup)
    row = connection.execute("SELECT description FROM symptoms").fetchone()
    connection.close()
    assert row["description"] == "something hurts. my knee. about a 5. since Tuesday."


def test_saving_early_in_a_talk_updates_the_same_entry(client, monkeypatch, safe_test_setup):
    # The real model once saved on her first answer and kept asking. Her
    # later answers then update that same entry instead of making a second one.
    use_fake(
        monkeypatch,
        tool_call("c1", "log_symptom", {"body_area": "back"}),
        reply("How bad is it, from 0 to 10?"),
        tool_call("c2", "log_symptom", {"pain_level": 6}),
        reply("I've written that down for your doctor."),
    )
    chat(client, "my back is sore today", mode="diary")
    chat(client, "about a 6", mode="diary")
    connection = db.get_connection(safe_test_setup)
    rows = connection.execute("SELECT description, body_area, pain_level FROM symptoms").fetchall()
    connection.close()
    assert [tuple(row) for row in rows] == [("my back is sore today. about a 6.", "back", 6)]


def saved_facts(path):
    connection = db.get_connection(path)
    row = connection.execute("SELECT body_area, pain_level, since FROM symptoms").fetchone()
    connection.close()
    return row["body_area"], row["pain_level"], row["since"]


def test_diary_facts_the_ai_made_up_are_not_saved(client, monkeypatch, safe_test_setup):
    # SAFETY.md section 6: her own words, never medical terms. A fact the AI
    # filled in is kept only if she actually said those words.
    use_fake(
        monkeypatch,
        tool_call("c1", "log_symptom", {"body_area": "patella (possible sprain)", "pain_level": 7, "since": "3 days"}),
        reply("I've written that down for your doctor."),
    )
    chat(client, "my knee hurts, about a 5, since Tuesday", mode="diary")
    assert saved_facts(safe_test_setup) == ("", None, "")


def test_diary_facts_in_her_own_words_are_kept(client, monkeypatch, safe_test_setup):
    use_fake(
        monkeypatch,
        tool_call("c1", "log_symptom", {"body_area": "her left knee", "pain_level": 5, "since": "since Tuesday"}),
        reply("I've written that down for your doctor."),
    )
    chat(client, "my left knee hurts. It's about five. Since Tuesday.", mode="diary")
    # Small words the AI adds in front ("her", "since") are left out on the screen.
    assert saved_facts(safe_test_setup) == ("left knee", 5, "Tuesday")


def test_bad_tool_calls_are_still_answered_and_the_loop_stops(client, monkeypatch):
    fake = use_fake(
        monkeypatch,
        tool_call("a", "no_such_tool", {}),
        tool_call("b", "log_mood", {"mood": "fantastic"}),  # not an allowed mood
        tool_call("c", "log_mood", {"mood": "good"}),
        reply("Glad to hear it!"),  # the final answer after 3 rounds
    )
    body = chat(client, "I feel good")
    assert body["reply"] == "Glad to hear it!"
    # After 3 rounds, words are asked for with an instruction (Meta has no tool_choice "none").
    assert fake.calls[-1][-1] == {"role": "developer", "content": companion.WORDS_NOW}


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
    # The real model sometimes spends its whole token allowance thinking and
    # sends nothing. It is asked again the same way.
    fake = FakeAI(reply(""), reply("I'm here with you."))
    monkeypatch.setattr(meta_client, "chat", fake)
    connection = db.get_connection()
    profile = db.get_profile(connection)
    db.save_message(connection, "x", "user", "hello")
    assert companion.answer(connection, profile, "x", "hello", "chat")["reply"] == "I'm here with you."
    assert fake.calls[1] == fake.calls[0]
    # Nothing, every time: a gentle fixed line instead of silence.
    monkeypatch.setattr(meta_client, "chat", FakeAI(*[reply("")] * 4))
    assert companion.answer(connection, profile, "x", "hello", "chat")["reply"] == companion.EMPTY_REPLY
    connection.close()


def test_after_an_empty_reply_buddy_can_still_save_the_entry(client, monkeypatch):
    # What the real model did: no words first, then the save. Asking again
    # must still allow the save, or Buddy would only SAY it saved it.
    use_fake(
        monkeypatch,
        reply(""),
        tool_call("c1", "log_symptom", {"pain_level": 6}),
        reply("I've written that down for your doctor."),
    )
    body = chat(client, "my back is sore, about a 6", mode="diary")
    assert body["diary_saved"] is True
    assert body["reply"] == "I've written that down for your doctor."


def test_her_answers_are_joined_without_doubled_punctuation():
    from app import tools

    joined = tools.joined(["my back is sore today", "should I put heat or ice on it?", "about a 6"])
    assert joined == "my back is sore today. should I put heat or ice on it? about a 6."


def symptom_rows(path):
    connection = db.get_connection(path)
    rows = connection.execute("SELECT description, body_area, pain_level FROM symptoms").fetchall()
    connection.close()
    return [tuple(row) for row in rows]


def test_side_effects_in_a_something_hurts_talk_stay_one_entry(client, monkeypatch, safe_test_setup):
    use_fake(monkeypatch, tool_call("c1", "log_symptom", {}), reply("I've written that down for your doctor."))
    chat(client, "my new pills make me dizzy since Monday", mode="diary")
    assert len(symptom_rows(safe_test_setup)) == 1


def test_saving_twice_in_one_reply_keeps_one_entry(client, monkeypatch, safe_test_setup):
    use_fake(monkeypatch, tool_call("c1", "log_symptom", {}), tool_call("c2", "log_symptom", {}), reply("Written down."))
    chat(client, "my knee hurts")
    assert len(symptom_rows(safe_test_setup)) == 1


def test_the_talk_is_not_done_while_buddy_still_asks_even_with_a_note_added(client, monkeypatch):
    # The fixed side-effect line is added AFTER Buddy's question; the talk goes on.
    use_fake(monkeypatch, tool_call("c1", "log_symptom", {}), reply("I'm sorry. How bad is it, from 0 to 10?"))
    body = chat(client, "they make me dizzy", mode="diary")
    assert body["reply"].endswith("Please call your doctor or pharmacist today and tell them.")
    assert body["diary_saved"] is True and body["diary_done"] is False


def test_her_last_answer_in_a_talk_tells_buddy_to_save_now(client, monkeypatch):
    fake = use_fake(monkeypatch, *[reply("And how bad is it?")] * 4)
    answers = [chat(client, words, mode="diary") for words in ["my hip", "it aches", "since Sunday", "and my foot"]]
    assert [a["diary_done"] for a in answers] == [False, False, False, True]
    assert prompts.LAST_DIARY_ANSWER in fake.calls[3][0]["content"]
    assert prompts.LAST_DIARY_ANSWER not in fake.calls[2][0]["content"]


def test_in_ordinary_chat_the_first_message_naming_the_place_is_kept(client, monkeypatch, safe_test_setup):
    use_fake(
        monkeypatch,
        reply("Oh no. How bad, from 0 to 10?"),
        reply("Since when?"),
        reply("Anything new?"),
        tool_call("c1", "log_symptom", {"body_area": "knee", "pain_level": 5}),
        reply("I've written that down for your doctor."),
    )
    for words in ["my knee hurts when I walk", "about a 5", "since Tuesday", "no, nothing new"]:
        chat(client, words)
    assert symptom_rows(safe_test_setup) == [
        ("my knee hurts when I walk. about a 5. since Tuesday. no, nothing new.", "knee", 5)
    ]


def test_a_number_that_is_a_time_is_not_a_pain_level(client, monkeypatch, safe_test_setup):
    use_fake(monkeypatch, tool_call("c1", "log_symptom", {"pain_level": 2}), reply("Written down."))
    chat(client, "my hip has been sore for 2 days", mode="diary")
    assert symptom_rows(safe_test_setup)[0][2] is None


def test_a_pain_level_of_zero_is_kept(client, monkeypatch, safe_test_setup):
    use_fake(monkeypatch, tool_call("c1", "log_symptom", {"pain_level": 0}), reply("Written down."))
    chat(client, "my wrist, it's a 0 now", mode="diary")
    assert symptom_rows(safe_test_setup)[0][2] == 0
