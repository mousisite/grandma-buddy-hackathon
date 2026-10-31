# Tests for the daily check-in (docs/SPEC.md feature 5): /api/check-in
# says whether today's check-in is still to do, /start gives Buddy's fixed
# opening question, /skip is "Not today", and a whole check-in saves her
# mood, a diary entry, and a pill taken. The AI is always FAKE here.
# Made-up people and pills only.

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import db, prompts, reminders
from app.main import app
from tests.test_companion import reply, tool_call, use_fake

TALK = "2026-10-27-check-in"


@pytest.fixture
def clock(monkeypatch):
    """The time the app sees. clock.set(9) moves it to 9:00 AM, October 27."""

    class Clock:
        now = datetime(2026, 10, 27, 9, 0)

        def set(self, hour, minute=0, day=27):
            self.now = datetime(2026, 10, day, hour, minute)

    test_clock = Clock()
    monkeypatch.setattr(reminders, "current_time", lambda: test_clock.now)
    return test_clock


@pytest.fixture
def client():
    return TestClient(app)


def start(client, talk=TALK):
    return client.post("/api/check-in/start", json={"conversation_id": talk})


# ---------- Once a day ----------

def test_the_check_in_is_due_on_the_first_visit_of_the_day(client, clock):
    assert client.get("/api/check-in").json() == {"due": True, "done": False, "skipped": False, "mood": None}


def add_mood(hour, minute=0):
    """She told Buddy how she feels, at this time on October 27."""
    connection = db.get_connection()
    connection.execute("INSERT INTO moods (created_at, mood, note) VALUES (?, 'good', '')",
                       (datetime(2026, 10, 27, hour, minute).isoformat(timespec="seconds"),))
    connection.commit()
    connection.close()


# ---------- Done (Home shows a check instead of "Start") ----------

def test_it_is_done_once_she_has_said_how_she_feels(client, clock):
    start(client)
    assert client.get("/api/check-in").json()["done"] is False  # started, no answer yet
    add_mood(9, 1)
    assert client.get("/api/check-in").json()["done"] is True


def test_a_mood_from_before_the_check_in_does_not_finish_it(client, clock):
    add_mood(8, 30)  # an ordinary talk earlier
    start(client)
    assert client.get("/api/check-in").json()["done"] is False


def test_not_today_is_skipped_not_done(client, clock):
    client.post("/api/check-in/skip")
    body = client.get("/api/check-in").json()
    assert (body["done"], body["skipped"]) == (False, True)


def test_starting_after_not_today_counts_as_started(client, clock):
    client.post("/api/check-in/skip")
    clock.set(11)
    start(client)
    add_mood(11, 1)
    body = client.get("/api/check-in").json()
    assert (body["done"], body["skipped"]) == (True, False)


def test_starting_it_means_it_is_not_asked_again_today(client, clock):
    assert start(client).status_code == 200
    assert client.get("/api/check-in").json()["due"] is False
    clock.set(18)
    assert client.get("/api/check-in").json()["due"] is False


def test_not_today_means_it_is_not_asked_again_today(client, clock):
    assert client.post("/api/check-in/skip").status_code == 200
    assert client.get("/api/check-in").json()["due"] is False


def test_it_is_due_again_the_next_day(client, clock):
    start(client)
    clock.set(8, day=28)
    assert client.get("/api/check-in").json()["due"] is True


def test_starting_twice_in_a_day_is_fine(client, clock):
    start(client)
    assert start(client).status_code == 200  # "Start" in the Today list, again


def test_a_very_long_talk_id_is_refused(client, clock):
    assert start(client, talk="x" * 81).status_code == 400


# ---------- Buddy's opening question ----------

@pytest.mark.parametrize("hour, greeting", [(9, "Good morning"), (14, "Good afternoon"), (19, "Good evening"), (23, "Good evening")])
def test_the_opening_greets_her_by_name_for_the_time_of_day(client, clock, hour, greeting):
    client.put("/api/profile", json={"preferred_name": "Rose"})
    clock.set(hour)
    assert start(client).json()["opening"] == f"{greeting}, Rose. How are you feeling today?"


def test_without_a_name_the_opening_still_works(client, clock):
    assert start(client).json()["opening"] == "Good morning. How are you feeling today?"


def test_the_opening_is_remembered_as_buddy_asking(client, clock, safe_test_setup):
    opening = start(client).json()["opening"]
    connection = db.get_connection(safe_test_setup)
    rows = [dict(r) for r in connection.execute("SELECT conversation_id, role, content FROM messages")]
    connection.close()
    assert rows == [{"conversation_id": TALK, "role": "assistant", "content": opening}]


def test_the_check_in_prompt_knows_the_first_question_was_asked():
    profile = {"preferred_name": "Rose", "name": "", "family_name": "Maria", "doctor_name": "Dr. Lee"}
    prompt = prompts.companion_prompt(profile, "check_in", False)
    assert "already asked how she is feeling" in prompt
    assert "no pills" in prompt
    # The real AI once called Dr. Lee "him": it should use names, not guess.
    assert "by name, never as he or she" in prompt


# ---------- Her mood on Home ----------

def test_todays_mood_is_shown_after_she_says_how_she_feels(client, monkeypatch):
    # The real clock: moods are saved with the real time.
    use_fake(monkeypatch, tool_call("m", "log_mood", {"mood": "good", "note": "pretty good"}),
             reply("I'm glad. Does anything hurt or feel different today?"))
    client.post("/api/chat", json={"conversation_id": "today-check-in", "text": "I'm feeling pretty good", "mode": "check_in"})
    mood = client.get("/api/check-in").json()["mood"]
    assert mood["mood"] == "good"
    assert mood["at"][:10] == datetime.now().strftime("%Y-%m-%d")


# ---------- Clean records (found with the real AI, scripts/check_checkin.py) ----------

def say_in_check_in(client, text):
    return client.post("/api/chat", json={"conversation_id": TALK, "text": text, "mode": "check_in"}).json()


def test_her_mood_is_saved_once_per_talk_even_if_the_ai_saves_it_again(client, clock, monkeypatch, safe_test_setup):
    start(client)
    use_fake(
        monkeypatch,
        tool_call("m1", "log_mood", {"mood": "good", "note": "pretty good"}),
        reply("I'm glad. Does anything hurt or feel different today?"),
        tool_call("m2", "log_mood", {"mood": "okay", "note": "a bit tired"}),
        reply("Thank you for telling me. Did you take your morning pills?"),
    )
    say_in_check_in(client, "I'm feeling pretty good")
    say_in_check_in(client, "Actually I'm a bit tired")
    connection = db.get_connection(safe_test_setup)
    moods = [(r["mood"], r["note"]) for r in connection.execute("SELECT mood, note FROM moods")]
    connection.close()
    assert moods == [("okay", "a bit tired")]  # one per talk, and her latest words win


def test_the_check_in_diary_entry_keeps_only_what_she_said_about_what_hurts(client, clock, monkeypatch, safe_test_setup):
    start(client)
    use_fake(
        monkeypatch,
        reply("I'm glad. Does anything hurt or feel different today?"),
        reply("I'm sorry. Since when has your knee been sore?"),
        reply("Thank you. Did you take your morning pills?"),
        tool_call("s", "log_symptom", {"body_area": "knee", "pain_level": None, "since": "yesterday"}),
        reply("I've written that down for your doctor."),
    )
    for words in ["I'm feeling pretty good", "My knee is sore", "Since yesterday", "Yes I took them"]:
        say_in_check_in(client, words)
    connection = db.get_connection(safe_test_setup)
    diary = [r["description"] for r in connection.execute("SELECT description FROM symptoms")]
    connection.close()
    assert diary == ["My knee is sore. Since yesterday."]


def test_a_check_in_keeps_one_diary_entry_even_if_the_ai_saves_on_every_turn(client, clock, monkeypatch, safe_test_setup):
    start(client)
    use_fake(
        monkeypatch,
        reply("I'm glad. Does anything hurt or feel different today?"),
        tool_call("s1", "log_symptom", {"body_area": "knee", "pain_level": None, "since": "yesterday"}),
        reply("I'm sorry. Is it your left knee or your right knee?"),
        tool_call("s2", "log_symptom", {"body_area": "", "pain_level": None, "since": ""}),
        reply("Thank you. Did you take your morning pills?"),
    )
    for words in ["I'm feeling pretty good", "My knee is sore since yesterday", "The left one"]:
        say_in_check_in(client, words)
    connection = db.get_connection(safe_test_setup)
    diary = [dict(r) for r in connection.execute("SELECT description, body_area, since, source FROM symptoms")]
    connection.close()
    assert diary == [{"description": "My knee is sore since yesterday. The left one.", "body_area": "knee",
                      "since": "yesterday", "source": "check_in"}]


def test_buddy_asking_about_a_pill_by_name_ends_her_words_about_what_hurts(client, clock, monkeypatch, safe_test_setup):
    client.post("/api/meds", json={"name": "Lisinopril", "label_dose": "10 mg tablet", "times": ["08:00"]})
    start(client)
    use_fake(
        monkeypatch,
        reply("I'm glad. Does anything hurt or feel different today?"),
        reply("Thank you. Did you take your Lisinopril this morning?"),
        tool_call("s", "log_symptom", {"body_area": "knee", "pain_level": None, "since": ""}),
        reply("I've written that down for your doctor."),
    )
    for words in ["I'm feeling pretty good", "My knee is sore", "Yes I took it"]:
        say_in_check_in(client, words)
    connection = db.get_connection(safe_test_setup)
    diary = [r["description"] for r in connection.execute("SELECT description FROM symptoms")]
    connection.close()
    assert diary == ["My knee is sore."]


# ---------- The safety net in a check-in ----------

def test_after_buddy_asks_what_hurts_my_chest_alone_shows_the_emergency_screen(client, clock, monkeypatch):
    start(client)
    use_fake(monkeypatch, reply("I'm glad. Does anything hurt or feel different today?"))
    say_in_check_in(client, "I'm okay I guess")
    fake = use_fake(monkeypatch)  # no answers: the AI must not be asked
    body = say_in_check_in(client, "my chest")
    assert body["show"] == "emergency"
    assert body["reply"] == "This could be an emergency. If it is, please call 911 right now."
    assert fake.calls == []


# ---------- Done when (docs/SPEC.md feature 5) ----------

def test_a_whole_check_in_saves_her_mood_a_diary_entry_and_her_pill(client, clock, monkeypatch, safe_test_setup):
    client.put("/api/profile", json={"preferred_name": "Rose", "family_name": "Maria", "family_phone": "555-0100",
                                     "doctor_name": "Dr. Lee", "doctor_phone": "555-0199"})
    client.post("/api/meds", json={"name": "Lisinopril", "label_dose": "10 mg tablet", "times": ["08:00"]})
    client.get("/api/reminders")  # 8:00 AM is due now (9:00 AM)
    start(client)
    use_fake(
        monkeypatch,
        tool_call("m", "log_mood", {"mood": "good", "note": "pretty good"}),
        reply("I'm glad. Does anything hurt or feel different today?"),
        tool_call("s", "log_symptom", {"body_area": "knee", "pain_level": None, "since": "since yesterday"}),
        reply("I've written that down for your doctor. Did you take your morning pills?"),
        tool_call("p", "mark_pill_taken", {"medication_name": "all"}),
        reply("Thank you, I wrote that down. Have a lovely day, Rose."),
    )

    def say(text):
        return client.post("/api/chat", json={"conversation_id": TALK, "text": text, "mode": "check_in"}).json()

    say("I'm feeling pretty good")
    knee = say("My knee is a bit sore since yesterday")
    say("Yes I took them")

    # A diary entry is always followed by Call doctor and Call family.
    assert knee["diary_saved"] is True
    assert {a["href"] for a in knee["actions"]} == {"tel:555-0199", "tel:555-0100"}

    connection = db.get_connection(safe_test_setup)
    moods = [r["mood"] for r in connection.execute("SELECT mood FROM moods")]
    diary = [dict(r) for r in connection.execute("SELECT description, body_area, since, source FROM symptoms")]
    connection.close()
    assert moods == ["good"]
    assert len(diary) == 1
    assert "My knee is a bit sore since yesterday" in diary[0]["description"]
    assert (diary[0]["body_area"], diary[0]["since"], diary[0]["source"]) == ("knee", "yesterday", "check_in")
    assert [r["status"] for r in client.get("/api/reminders").json()["reminders"]] == ["taken"]
