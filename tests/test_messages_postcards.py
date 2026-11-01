# Tests for "Message Maria" and the daily postcard (docs/SPEC.md feature
# 22): a message in her own words goes through the safety net first and is
# never sent when it needs a safety screen; it reaches the family page. A
# postcard is one cheerful sentence of hers from today, picked by Muse
# Spark but kept word for word, checked by plain code (never about health),
# painted like the memory book, and shown to the family only once she
# sends it. Meta is always FAKE here. Made-up words only.

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import accounts, db, meta_client, postcards, reminders, tools
from app.main import app
from tests.test_companion import FakeAI, reply
from tests.test_memories import WEBP, FakePainter, FakeWriter

NOW = datetime(2026, 10, 31, 15, 0)
MARIA = {"name": "Maria", "email": "maria@example.com", "password": "rose-garden-2026"}


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(reminders, "current_time", lambda: NOW)
    accounts.forget_tries()
    return NOW


@pytest.fixture
def client(clock):
    return TestClient(app)


@pytest.fixture
def connection(safe_test_setup):
    opened = db.get_connection(safe_test_setup)
    db.get_profile(opened)
    opened.execute("UPDATE profile SET preferred_name = 'Rose', family_name = 'Maria', family_phone = '555-0100' WHERE id = 1")
    opened.commit()
    yield opened
    opened.close()


def maria(client):
    code = client.post("/api/family/invite").json()["code"]
    assert client.post("/api/family/account", json={"code": code, **MARIA}).status_code == 200
    return client


# ---------- Messages to the family ----------

def test_her_message_is_kept_word_for_word_and_reaches_the_family_page(client, connection):
    sent = client.post("/api/messages", json={"text": "The tulips came up this morning, come and see them Sunday"})
    assert sent.status_code == 200
    assert sent.json()["message"] == {"id": 1, "time": "3:00 PM", "text": "The tulips came up this morning, come and see them Sunday",
                                      "from": "her", "name": "", "unread": False, "voice": ""}
    assert client.get("/api/messages").json()["messages"] == [sent.json()["message"]]
    day = maria(client).get("/api/family/dashboard").json()
    assert day["messages"] == [{"time": "3:00 PM", "text": "The tulips came up this morning, come and see them Sunday",
                                "from": "her", "name": "", "voice": ""}]


def test_a_message_that_needs_a_safety_screen_is_never_sent(client, connection):
    answer = client.post("/api/messages", json={"text": "Maria my chest feels tight today"})
    assert answer.status_code == 200 and answer.json()["show"] == "emergency"
    assert answer.json()["actions"][0]["href"] == "tel:911"
    assert client.get("/api/messages").json()["messages"] == []
    # Crisis words: the calm crisis screen, and nothing kept anywhere, not even the event's words.
    answer = client.post("/api/messages", json={"text": "tell Maria I don't want to be here anymore"})
    assert answer.json()["show"] == "crisis"
    assert client.get("/api/messages").json()["messages"] == []
    assert connection.execute("SELECT excerpt FROM safety_events WHERE kind = 'crisis'").fetchone()["excerpt"] == ""


def test_an_empty_or_very_long_message_is_refused(client, connection):
    assert client.post("/api/messages", json={"text": "   "}).status_code == 400
    assert client.post("/api/messages", json={"text": "x" * 1001}).status_code == 400


def test_buddy_offers_to_send_her_words_never_its_own(connection):
    db.save_message(connection, "day", "user", "Tell Maria the tulips came up and I'd love a visit Sunday")
    context = {"connection": connection, "profile": db.get_profile(connection), "conversation_id": "day", "mode": "chat"}
    # The AI picks out the message from what she said: those words are hers.
    result, actions = tools.run_tool("offer_family_message", '{"message": "The tulips came up and I\'d love a visit Sunday"}', context)
    assert result == {"ok": True}
    assert actions == [{"type": "message", "label": "Send this to Maria", "text": "The tulips came up and I'd love a visit Sunday"}]
    # Words she never said: her whole last message is offered instead.
    result, actions = tools.run_tool("offer_family_message", '{"message": "Mom says the roses are blooming"}', context)
    assert actions[0]["text"] == "Tell Maria the tulips came up and I'd love a visit Sunday"
    # Her words, but not in her order (a dropped "not"): her whole message again.
    db.save_message(connection, "day", "user", "Tell Maria I do not love the new tulips")
    result, actions = tools.run_tool("offer_family_message", '{"message": "I love the new tulips"}', context)
    assert actions[0]["text"] == "Tell Maria I do not love the new tulips"


@pytest.mark.parametrize("said, message", [
    ("Tell Maria the tulips came up, come and see them Sunday", "The tulips came up, come and see them Sunday"),
    ("Please tell Maria that I'd love a visit on Sunday", "I'd love a visit on Sunday"),
    ("Buddy, can you let Maria know the tulips are up", "The tulips are up"),
    ("Send Maria a message: come for tea on Sunday", "Come for tea on Sunday"),
    ("Text my daughter that the roses are blooming", "The roses are blooming"),
    ("Maria called yesterday and we talked about the garden", ""),  # not asking to pass anything on
    ("Tell Maria", ""),  # nothing to send yet
])
def test_the_message_she_asked_buddy_to_pass_on(said, message):
    assert tools.message_she_asked_for(said, "Maria") == message


def test_the_button_appears_even_when_the_ai_forgot_its_tool(client, connection, monkeypatch):
    # The real AI once said "I've got your note ready" without calling the
    # tool. Plain code adds the button with her words when she clearly asked.
    monkeypatch.setattr(meta_client, "chat", FakeAI(reply("I've got your note ready, Rose. Tap the button to send it.")))
    answer = client.post("/api/chat", json={"conversation_id": "day", "text": "Tell Maria the tulips came up, come and see them Sunday",
                                             "mode": "chat"}).json()
    assert answer["actions"] == [{"type": "message", "label": "Send this to Maria",
                                  "text": "The tulips came up, come and see them Sunday"}]
    # Not in a "Something hurts" talk, and not when she didn't ask.
    monkeypatch.setattr(meta_client, "chat", FakeAI(reply("How lovely. Did she enjoy it?")))
    answer = client.post("/api/chat", json={"conversation_id": "day", "text": "Maria came by with the children", "mode": "chat"}).json()
    assert answer["actions"] == []


def test_messages_are_not_in_the_day_with_no_family_name(client, connection):
    connection.execute("UPDATE profile SET family_name = '' WHERE id = 1")
    connection.commit()
    sent = client.post("/api/messages", json={"text": "Hello"})
    assert sent.status_code == 200  # still kept: the family page shows it to whoever signs in


# ---------- Maria writes back ----------

def test_a_family_member_can_write_back_and_she_sees_it_as_their_words(client, connection):
    family = maria(client)
    sent = family.post("/api/family/reply", json={"text": "Can't wait to see them, I'll bring Leo on Sunday"})
    assert sent.status_code == 200
    assert sent.json()["message"] == {"id": 1, "time": "3:00 PM", "text": "Can't wait to see them, I'll bring Leo on Sunday",
                                      "from": "family", "name": "Maria", "unread": True, "voice": ""}
    # Her Family screen: new until she has seen it, and Home knows one is waiting.
    shown = client.get("/api/messages").json()
    assert shown["messages"] == [sent.json()["message"]] and shown["unread"] == 1
    assert shown["latest_unread"] == {"name": "Maria", "text": "Can't wait to see them, I'll bring Leo on Sunday", "voice": ""}
    assert client.post("/api/messages/1/read").status_code == 200
    shown = client.get("/api/messages").json()
    assert shown["unread"] == 0 and shown["messages"][0]["unread"] is False and shown["latest_unread"] is None
    # Her own reply: hers, never "new" to her, and on Maria's page as the thread.
    hers = client.post("/api/messages", json={"text": "Lovely, I'll make a pie"}).json()["message"]
    assert hers["from"] == "her" and hers["name"] == "" and hers["unread"] is False
    day = family.get("/api/family/dashboard").json()
    assert day["messages"] == [{"time": "3:00 PM", "text": "Can't wait to see them, I'll bring Leo on Sunday", "from": "family",
                                "name": "Maria", "voice": ""},
                               {"time": "3:00 PM", "text": "Lovely, I'll make a pie", "from": "her", "name": "", "voice": ""}]


def test_writing_back_needs_a_signed_in_family_member_and_some_words(client, connection):
    assert client.post("/api/family/reply", json={"text": "Hello"}).status_code == 401
    family = maria(client)
    assert family.post("/api/family/reply", json={"text": "   "}).status_code == 400
    assert family.post("/api/family/reply", json={"text": "x" * 1001}).status_code == 400
    assert client.post("/api/messages/9/read").status_code == 404


def test_an_unread_message_from_yesterday_waits_until_she_sees_it(client, connection):
    connection.execute("INSERT INTO family_messages (created_at, text, sender, sender_name) VALUES "
                       "('2026-10-30T18:00:00', 'Sleep well, Mom', 'family', 'Maria')")
    connection.execute("INSERT INTO family_messages (created_at, text, sender, sender_name, read_at) VALUES "
                       "('2026-10-29T18:00:00', 'Old news', 'family', 'Maria', '2026-10-29T19:00:00')")
    connection.commit()
    shown = client.get("/api/messages").json()
    assert [m["text"] for m in shown["messages"]] == ["Sleep well, Mom"] and shown["unread"] == 1


def test_the_greeting_says_a_message_is_waiting_without_reading_it(client, connection):
    maria(client).post("/api/family/reply", json={"text": "Call me when you're up"})
    greeting = client.post("/api/greeting", json={"conversation_id": "day"}).json()["greeting"]
    assert "Maria sent you a message. It’s on your Family screen." in greeting
    assert "Call me" not in greeting, "the screen reads it, in her words; the greeting only says one is waiting"


# ---------- The postcard ----------

def today_she_said(connection, *lines):
    for index, line in enumerate(lines):
        connection.execute("INSERT INTO messages (conversation_id, created_at, role, content) VALUES ('day', ?, 'user', ?)",
                           (f"2026-10-31T{10 + index}:00:00", line))
    connection.commit()


def fake_postcard_meta(monkeypatch, pick: dict, picture=WEBP):
    writer, painter = FakeWriter(pick), FakePainter(picture)
    monkeypatch.setattr(meta_client, "structured", writer)
    monkeypatch.setattr(meta_client, "paint", painter)
    return writer, painter


def test_a_postcard_is_one_sentence_of_hers_painted_once_a_day(client, connection, monkeypatch):
    today_she_said(connection, "My knee is sore again", "The tulips came up this morning, red ones", "Leo is coming Sunday")
    writer, painter = fake_postcard_meta(monkeypatch, {"number": 1, "scene": "Red tulips in a garden bed in morning light."})
    card = client.get("/api/postcard/today").json()
    assert card["postcard"]["sentence"] == "The tulips came up this morning, red ones"
    assert card["postcard"]["status"] == "ready" and card["postcard"]["shared"] is False
    assert card["postcard"]["picture"].startswith("/api/postcard/1/picture")
    assert len(painter.prompts) == 1 and postcards.STYLE_WORDS in painter.prompts[0] and "Red tulips" in painter.prompts[0]
    # Only her own words were shown to the picker, numbered, and her exact
    # sentence is kept. A line about her health never reaches the picker.
    shown = writer.calls[0][1]["content"]
    assert "1. The tulips came up this morning, red ones" in shown and "2. Leo is coming Sunday" in shown
    assert "knee" not in shown
    again = client.get("/api/postcard/today").json()
    assert again["postcard"]["id"] == card["postcard"]["id"] and len(painter.prompts) == 1, "one painting a day"


def test_the_family_sees_the_postcard_only_once_she_sends_it(client, connection, monkeypatch):
    today_she_said(connection, "The tulips came up this morning, red ones")
    fake_postcard_meta(monkeypatch, {"number": 1, "scene": "Red tulips in a garden bed."})
    client.get("/api/postcard/today")
    family = maria(client)
    assert family.get("/api/family/dashboard").json()["postcard"] is None
    sent = client.post("/api/postcard/today/send").json()
    assert sent["postcard"]["shared"] is True
    shown = family.get("/api/family/dashboard").json()["postcard"]
    assert shown["sentence"] == "The tulips came up this morning, red ones" and shown["picture"].startswith("/api/postcard/1/picture")
    assert family.get(shown["picture"]).status_code == 200


@pytest.mark.parametrize("pick", [
    {"number": 1, "scene": "A bottle of pills on a table."},        # health in the scene
    {"number": 1, "scene": "A garden, good for a sore knee."},      # health in the scene, said softly
    {"number": 0, "scene": ""},                                     # nothing nice today, the AI says
    {"number": 9, "scene": "A garden."},                            # a number that isn't there
    {"number": 1, "scene": "Rose and Leo in the garden in 1962."},  # names and numbers nobody said
])
def test_a_postcard_that_breaks_a_rule_is_not_made(client, connection, monkeypatch, pick):
    today_she_said(connection, "The tulips came up this morning, red ones", "My knee is sore again")
    writer, painter = fake_postcard_meta(monkeypatch, pick)
    card = client.get("/api/postcard/today").json()
    assert card["postcard"] is None and painter.prompts == []
    assert "tulips" in card["why"] or "nice" in card["why"].lower()


@pytest.mark.parametrize("line", [
    "My knee is about a 5 today", "I was dizzy this morning", "I fell in the garden but I am fine",
    "I had a fall yesterday", "I threw up after lunch", "I have a headache since yesterday", "My blood sugar was high",
    "I could not sleep last night", "my hands are shaking", "I cried all morning", "I have been feeling down",
    "I miss my husband so much", "Dr. Lee wants to see me Thursday", "My back is bad again",
    "I took my pills with breakfast", "I feel so lonely in the evenings", "My chest felt tight on the stairs",
])
def test_a_line_about_her_health_or_hard_feelings_never_reaches_the_picker(client, connection, monkeypatch, line):
    today_she_said(connection, line, "The tulips came up this morning, red ones")
    writer, painter = fake_postcard_meta(monkeypatch, {"number": 1, "scene": "Red tulips by a gate."})
    client.get("/api/postcard/today")
    shown = writer.calls[0][1]["content"]
    assert line not in shown and "1. The tulips came up this morning, red ones" in shown
    assert painter.prompts and "Red tulips" in painter.prompts[0]


@pytest.mark.parametrize("line", [
    "Leo rode his bike all the way to the corner and back, I clapped",
    "I walked down to the mailbox in the sunshine",
    "I made sugar cookies with Maria this afternoon",
    "We watched the parade on the television",
    "Leo gave me a hand with the garden and we planted the bulbs",
])
def test_a_cheerful_line_with_an_everyday_word_still_counts(client, connection, monkeypatch, line):
    today_she_said(connection, line)
    writer, _ = fake_postcard_meta(monkeypatch, {"number": 1, "scene": "A sunny garden path."})
    client.get("/api/postcard/today")
    assert "1. " + line in writer.calls[0][1]["content"]


def test_what_she_said_in_a_check_in_or_a_something_hurts_talk_never_counts(client, connection, monkeypatch):
    for talk, line in (("day-check-in", "I feel wonderful today, the sun is out"),
                       ("day-diary-1700000000", "It is a lovely morning")):
        connection.execute("INSERT INTO messages (conversation_id, created_at, role, content) VALUES (?, ?, 'user', ?)",
                           (talk, "2026-10-31T09:00:00", line))
    connection.commit()
    writer, painter = fake_postcard_meta(monkeypatch, {"number": 1, "scene": "A garden."})
    card = client.get("/api/postcard/today").json()
    assert card["postcard"] is None and writer.calls == [] and painter.prompts == []


def test_two_requests_at_once_never_paint_twice_or_fail(client, connection, monkeypatch):
    # The other request's claim lands between this one's look and its own
    # claim: this one sees "painting", never an error, and paints nothing.
    today_she_said(connection, "The tulips came up this morning, red ones")
    _, painter = fake_postcard_meta(monkeypatch, {"number": 1, "scene": "Red tulips."})
    connection.execute("INSERT INTO postcards (day, created_at, updated_at, status, said_until) VALUES "
                       "('2026-10-31', ?, ?, 'painting', '2026-10-31T10:00:00')", (db.now(), db.now()))
    connection.commit()
    real_look, looks = postcards.today_row, []

    def stale_look(connection, day):
        looks.append(day)
        return None if len(looks) == 1 else real_look(connection, day)

    monkeypatch.setattr(postcards, "today_row", stale_look)
    answer = client.get("/api/postcard/today")
    assert answer.status_code == 200 and answer.json()["status"] == "painting"
    assert painter.prompts == [] and connection.execute("SELECT COUNT(*) FROM postcards").fetchone()[0] == 1


def test_a_failure_that_is_not_metas_still_clears_the_claim(client, connection, monkeypatch):
    today_she_said(connection, "The tulips came up this morning, red ones")
    fake_postcard_meta(monkeypatch, {"number": 1, "scene": "Red tulips."})

    def cannot_write(scene):
        raise OSError("disk full")

    monkeypatch.setattr(postcards, "painted", cannot_write)
    card = client.get("/api/postcard/today").json()
    assert card["postcard"] is None and card["status"] == "failed"
    assert connection.execute("SELECT COUNT(*) FROM postcards").fetchone()[0] == 0, "nothing stays stuck at painting"


def test_a_claim_left_behind_by_a_restart_is_tried_again_after_a_while(client, connection, monkeypatch):
    today_she_said(connection, "The tulips came up this morning, red ones")
    connection.execute("INSERT INTO postcards (day, created_at, updated_at, status, said_until) VALUES "
                       "('2026-10-31', '2026-10-31T10:00:00', '2026-10-31T10:00:00', 'painting', '2026-10-31T10:00:00')")
    connection.commit()
    fake_postcard_meta(monkeypatch, {"number": 1, "scene": "Red tulips."})
    card = client.get("/api/postcard/today").json()
    assert card["postcard"]["status"] == "ready", "an old claim (over 15 minutes) is painted again"


def test_only_what_she_said_today_counts(client, connection, monkeypatch):
    # A minute before midnight yesterday is yesterday; the first second of today is today.
    connection.execute("INSERT INTO messages (conversation_id, created_at, role, content) VALUES ('day', ?, 'user', ?)",
                       ("2026-10-30T23:59:59", "The lake was like glass this evening"))
    connection.execute("INSERT INTO messages (conversation_id, created_at, role, content) VALUES ('day', ?, 'user', ?)",
                       ("2026-10-31T00:00:00", "The tulips came up this morning, red ones"))
    connection.commit()
    writer, _ = fake_postcard_meta(monkeypatch, {"number": 1, "scene": "Red tulips by a gate."})
    client.get("/api/postcard/today")
    shown = writer.calls[0][1]["content"]
    assert "lake" not in shown and "1. The tulips came up this morning, red ones" in shown


def test_no_talk_today_means_no_postcard_and_no_meta_call(client, connection, monkeypatch):
    writer, painter = fake_postcard_meta(monkeypatch, {"number": 1, "scene": "A garden."})
    card = client.get("/api/postcard/today").json()
    assert card["postcard"] is None and writer.calls == [] and painter.prompts == []


def test_when_painting_fails_the_postcard_can_be_tried_again_tomorrow(client, connection, monkeypatch):
    today_she_said(connection, "The tulips came up this morning, red ones")
    fake_postcard_meta(monkeypatch, {"number": 1, "scene": "Red tulips."}, picture=meta_client.MetaError("paint failed with HTTP 503"))
    card = client.get("/api/postcard/today").json()
    assert card["postcard"] is None and "just now" in card["why"]
    assert connection.execute("SELECT COUNT(*) FROM postcards").fetchone()[0] == 0, "nothing half-made is kept"
