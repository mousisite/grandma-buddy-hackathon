# Tests for Buddy as a friend: what it remembers about her life
# (remember_fact), the facts and recent talks in its prompt, the greeting
# that follows up, learning how she likes to talk over her first days, and
# the guards on its words. Every Meta call is FAKE here. Made-up data only.

import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import companion, db, guard, meta_client, reminders, tools
from app.main import app
from tests.test_companion import reply, tool_call, use_fake

NOW = datetime(2026, 10, 29, 14, 0)  # Thursday afternoon
TODAY = NOW.date()


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(reminders, "current_time", lambda: NOW)
    return NOW


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def connection(safe_test_setup):
    opened = db.get_connection(safe_test_setup)
    db.get_profile(opened)
    opened.execute("UPDATE profile SET preferred_name = 'Rose', family_name = 'Maria', family_phone = '555-0100', "
                   "doctor_name = 'Dr. Lee' WHERE id = 1")
    opened.commit()
    yield opened
    opened.close()


def remember(connection, **fact):
    """Run remember_fact the way the AI would."""
    context = {"connection": connection, "profile": db.get_profile(connection), "conversation_id": "day", "mode": "chat"}
    result, _ = tools.run_tool("remember_fact", json.dumps(fact), context)
    connection.commit()
    return result


TOM = {"kind": "event", "fact": "Her grandson Tom visits on Sunday", "follow_up": "Did Tom make it on Sunday?",
       "follow_up_on": "2026-11-02"}


def said_at(connection, conversation, role, words, when):
    db.save_message(connection, conversation, role, words, at=when)
    connection.commit()


def prompt_of(client, monkeypatch, text="Hello"):
    """Buddy's instructions for one reply (the AI is faked)."""
    ai = use_fake(monkeypatch, reply("Hello Rose!"))
    client.post("/api/chat", json={"conversation_id": "today", "text": text})
    return ai.calls[0][0]["content"]


# ---------- Remembering her life ----------

def test_remember_fact_saves_a_fact_with_its_follow_up(connection):
    assert remember(connection, **TOM) == {"ok": True}
    row = connection.execute("SELECT kind, fact, follow_up, follow_up_on, asked_at FROM facts").fetchone()
    assert tuple(row) == ("event", "Her grandson Tom visits on Sunday", "Did Tom make it on Sunday?", "2026-11-02", "")


def test_the_same_fact_again_updates_it(connection):
    remember(connection, **TOM)
    remember(connection, **dict(TOM, follow_up="How was Tom's visit?"))
    rows = connection.execute("SELECT follow_up FROM facts").fetchall()
    assert [row[0] for row in rows] == ["How was Tom's visit?"]


@pytest.mark.parametrize("change", [
    {"kind": "health"},                            # not a kind of fact
    {"fact": ""},                                  # nothing to remember
    {"fact": "x" * 201},                           # far too long
    {"follow_up_on": "next week"},                 # not a date
    {"follow_up_on": "2026-10-20"},                # in the past
    {"follow_up_on": "2027-06-01"},                # too far away
    {"fact": "She wishes she was dead"},           # crisis words are never kept
    {"fact": "Her knee pain is probably arthritis"},  # health guesses belong nowhere
    {"follow_up": "Did you rest your knee and take your pills?"},  # advice in the follow-up
])
def test_odd_or_unsafe_facts_are_refused(connection, change):
    result = remember(connection, **dict(TOM, **change))
    assert result["ok"] is False
    assert connection.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0


# ---------- What Buddy knows, in its prompt ----------

def test_saved_facts_and_recent_talks_are_in_the_prompt(client, monkeypatch, connection):
    remember(connection, kind="pet", fact="Her cat is called Biscuit", follow_up="", follow_up_on="")
    remember(connection, **TOM)
    connection.execute("INSERT INTO facts (created_at, updated_at, kind, fact, follow_up_on) "
                       "VALUES ('2026-10-01T09:00:00', '2026-10-01T09:00:00', 'event', 'A bake sale on October 10', '2026-10-10')")
    connection.execute("INSERT INTO talk_summaries (day, summary) VALUES ('2026-10-28', 'Rose talked about planting tulips.')")
    connection.commit()
    prompt = prompt_of(client, monkeypatch)
    assert "Her cat is called Biscuit" in prompt and "Her grandson Tom visits on Sunday" in prompt
    assert "Rose talked about planting tulips." in prompt
    assert "bake sale" not in prompt  # an event more than a week old


def test_at_most_30_facts_go_in_the_prompt(client, monkeypatch, connection):
    for number in range(35):
        remember(connection, kind="hobby", fact=f"She enjoys hobby number {number}", follow_up="", follow_up_on="")
    prompt = prompt_of(client, monkeypatch)
    assert prompt.count("\n- She enjoys hobby number") == 30


def test_buddy_is_told_to_start_differently_than_last_time(client, monkeypatch, connection):
    said_at(connection, "today", "assistant", "Oh, that sounds lovely! What did you plant?", NOW - timedelta(minutes=5))
    assert 'began "Oh, that sounds lovely"' in prompt_of(client, monkeypatch)


# ---------- The greeting ----------

def greet(client):
    return client.post("/api/greeting", json={"conversation_id": "today"}).json()["greeting"]


def test_the_first_talk_of_the_day_starts_with_a_greeting_with_her_name(client, connection):
    words = greet(client)
    assert words.startswith("Good afternoon, Rose!")
    saved = connection.execute("SELECT role, content FROM messages WHERE conversation_id = 'today'").fetchone()
    assert tuple(saved) == ("assistant", words)  # so the AI knows what it asked


def test_a_due_follow_up_is_in_the_greeting_and_asked_only_once(client, monkeypatch, connection):
    remember(connection, **dict(TOM, follow_up_on=TODAY.isoformat()))
    assert greet(client) == "Good afternoon, Rose! Did Tom make it on Sunday?"
    monkeypatch.setattr(reminders, "current_time", lambda: NOW + timedelta(hours=3))
    later = greet(client)
    assert later.startswith("Good evening, Rose!") and "Tom" not in later


def test_no_greeting_within_two_hours_of_the_last_talk(client, connection):
    said_at(connection, "today", "user", "I just watered the plants", NOW - timedelta(hours=1))
    assert greet(client) == ""


# ---------- Learning about her over the first days ----------

class FakeLearner:
    """Stands in for Muse Spark's structured answer when learning a day."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, messages, name, schema, reasoning="medium", max_tokens=3000):
        self.calls.append(messages)
        return self.answers.pop(0)


def two_past_days(connection):
    said_at(connection, "2026-10-27", "user", "I planted tulips, ha, the squirrels will have a feast", datetime(2026, 10, 27, 10, 0))
    said_at(connection, "2026-10-27", "assistant", "Ha! Cheeky squirrels. What color tulips?", datetime(2026, 10, 27, 10, 1))
    said_at(connection, "2026-10-28", "user", db.NOT_KEPT, datetime(2026, 10, 28, 9, 0))
    said_at(connection, "2026-10-28", "safety", "I'm really glad you told me. You matter.", datetime(2026, 10, 28, 9, 0))
    said_at(connection, "2026-10-28", "user", "Red ones, like my mother grew", datetime(2026, 10, 28, 11, 0))
    said_at(connection, NOW.date().isoformat(), "user", "Good afternoon", NOW - timedelta(hours=3))  # today: not yet


def test_each_earlier_day_is_learned_once_without_lines_that_were_not_kept(monkeypatch, connection):
    two_past_days(connection)
    learner = FakeLearner({"summary": "Rose planted tulips and joked about squirrels.", "notes": ["Loves a joke"]},
                          {"summary": "Rose talked about red tulips like her mother grew.", "notes": ["Loves a joke"]})
    monkeypatch.setattr(meta_client, "structured", learner)
    companion.learn_from_past_days()
    companion.learn_from_past_days()  # nothing left to learn
    assert len(learner.calls) == 2
    second = json.dumps(learner.calls[1])
    assert "Red ones" in second and "Not kept" not in second and "You matter" not in second
    days = [row[0] for row in connection.execute("SELECT day FROM talk_summaries ORDER BY day")]
    assert days == ["2026-10-27", "2026-10-28"]


def test_a_summary_with_advice_is_dropped(monkeypatch, connection):
    said_at(connection, "2026-10-28", "user", "My knee is sore today", datetime(2026, 10, 28, 9, 0))
    monkeypatch.setattr(meta_client, "structured", FakeLearner({"summary": "She should rest her knee and try ice.", "notes": []}))
    companion.learn_from_past_days()
    assert connection.execute("SELECT summary FROM talk_summaries").fetchone()[0] == ""


def test_notes_keep_at_most_8_and_never_health_moods_or_her_mind(monkeypatch, connection):
    said_at(connection, "2026-10-28", "user", "Hello", datetime(2026, 10, 28, 9, 0))
    notes = ["Seems depressed lately", "Talks about her knee pain", "Gets confused easily"] + [
        f"Enjoys topic {number}" for number in range(10)]
    monkeypatch.setattr(meta_client, "structured", FakeLearner({"summary": "A quiet chat.", "notes": notes}))
    companion.learn_from_past_days()
    kept = [row[0] for row in connection.execute("SELECT note FROM style_notes")]
    assert kept == [f"Enjoys topic {number}" for number in range(8)]


def test_buddy_gets_to_know_her_first_then_follows_what_it_learned(client, monkeypatch, connection):
    assert "getting to know Rose" in prompt_of(client, monkeypatch)
    connection.executemany("INSERT INTO talk_summaries (day, summary) VALUES (?, ?)",
                           [("2026-10-27", "Tulips."), ("2026-10-28", "Squirrels.")])
    connection.execute("INSERT INTO style_notes (created_at, note) VALUES ('2026-10-28T20:00:00', 'Loves puns')")
    connection.commit()
    prompt = prompt_of(client, monkeypatch)
    assert "How Rose likes to talk (learned over 2 days)" in prompt and "Loves puns" in prompt
    assert "getting to know Rose" not in prompt


def test_a_forgotten_note_is_never_learned_again(client, monkeypatch, connection):
    said_at(connection, "2026-10-28", "user", "Hello", datetime(2026, 10, 28, 9, 0))
    connection.execute("INSERT INTO style_notes (created_at, note) VALUES ('2026-10-27T20:00:00', 'Likes being called Rosie')")
    connection.commit()
    note_id = client.get("/api/learned").json()["notes"][0]["id"]
    client.post(f"/api/learned/notes/{note_id}/forget")
    monkeypatch.setattr(meta_client, "structured", FakeLearner({"summary": "Hi.", "notes": ["Likes being called Rosie"]}))
    companion.learn_from_past_days()
    assert client.get("/api/learned").json()["notes"] == []


# ---------- What Buddy has learned, in Settings ----------

def test_she_can_see_forget_and_bring_back_what_buddy_learned(client, monkeypatch, connection):
    remember(connection, kind="pet", fact="Her cat is called Biscuit", follow_up="", follow_up_on="")
    learned = client.get("/api/learned").json()
    assert [fact["fact"] for fact in learned["facts"]] == ["Her cat is called Biscuit"]
    fact_id = learned["facts"][0]["id"]
    client.post(f"/api/learned/facts/{fact_id}/forget")
    assert client.get("/api/learned").json()["facts"] == []
    assert "Biscuit" not in prompt_of(client, monkeypatch)
    client.post(f"/api/learned/facts/{fact_id}/restore")
    assert client.get("/api/learned").json()["facts"][0]["fact"] == "Her cat is called Biscuit"


def test_forgetting_something_unknown_is_refused(client):
    assert client.post("/api/learned/moods/1/forget").status_code == 404
    assert client.post("/api/learned/facts/99/forget").status_code == 404


# ---------- The guards on Buddy's words ----------

def test_replies_are_spoken_words_only():
    assert companion.spoken("**Oh**, that's lovely! 😊\n- tulips\n- roses\n## Tell me more") == \
        "Oh, that's lovely! tulips roses Tell me more"


def test_im_all_you_need_is_swapped_for_the_gentle_reply(client, monkeypatch, connection):
    use_fake(monkeypatch, reply("Don't worry, Rose, I'm all you need."))
    body = client.post("/api/chat", json={"conversation_id": "today", "text": "Nobody calls me anymore"}).json()
    assert body["reply"] == guard.gentle_reply("Maria")


def test_buddy_remembers_through_its_tool_in_a_real_talk(client, monkeypatch, connection):
    use_fake(monkeypatch, tool_call("c1", "remember_fact", TOM), reply("Oh, how lovely! What will you two do?"))
    client.post("/api/chat", json={"conversation_id": "today", "text": "My grandson Tom visits on Sunday"})
    assert connection.execute("SELECT fact FROM facts").fetchone()[0] == TOM["fact"]


def test_the_safety_net_still_comes_first_and_nothing_is_remembered(client, monkeypatch, connection):
    use_fake(monkeypatch)  # no answers: the AI must not be asked
    body = client.post("/api/chat", json={"conversation_id": "today", "text": "my chest feels really tight"}).json()
    assert body["show"] == "emergency"
    assert connection.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0


def test_a_chat_learns_from_earlier_days_afterward(client, monkeypatch, connection):
    said_at(connection, "2026-10-28", "user", "I baked bread", datetime(2026, 10, 28, 9, 0))
    learner = FakeLearner({"summary": "Rose baked bread.", "notes": ["Loves baking"]})
    monkeypatch.setattr(meta_client, "structured", learner)
    use_fake(monkeypatch, reply("Hello Rose!"))
    client.post("/api/chat", json={"conversation_id": "today", "text": "Hello"})
    assert len(learner.calls) == 1
    assert connection.execute("SELECT summary FROM talk_summaries").fetchone()[0] == "Rose baked bread."
