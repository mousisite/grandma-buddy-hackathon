# Tests for the family update (docs/SPEC.md feature 9): a plain-words
# summary of one day, written by plain code from the logs (no AI), and a
# mailto: link so she sends it from her own email app. Made-up data only.

from datetime import date, datetime
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from fastapi.testclient import TestClient

from app import db, family, reminders
from app.main import app

NOW = datetime(2026, 10, 28, 20, 0)  # Wednesday evening
TODAY = date(2026, 10, 28)


@pytest.fixture
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
    opened.execute("UPDATE profile SET preferred_name = 'Rose', family_name = 'Maria', "
                   "family_email = 'maria@example.com' WHERE id = 1")
    opened.commit()
    yield opened
    opened.close()


def lines(connection, day=TODAY):
    return family.summary(connection, day)["text"].splitlines()


def line_starting(connection, start, day=TODAY):
    found = [line for line in lines(connection, day) if line.startswith(start)]
    assert found, f"no line starting {start!r} in {lines(connection, day)}"
    return found[0]


def add_pill(connection, name="Metformin", times=('"08:00"', '"18:00"')):
    connection.execute("INSERT INTO medications (name, label_dose, times, active) VALUES (?, '500 mg tablet', ?, 1)",
                       (name, "[" + ", ".join(times) + "]"))
    return connection.execute("SELECT MAX(id) FROM medications").fetchone()[0]


def add_reminder(connection, pill, due, status):
    connection.execute("INSERT INTO med_events (medication_id, due_at, status) VALUES (?, ?, ?)", (pill, due, status))
    connection.commit()


# ---------- What the update says ----------

def test_it_greets_the_family_member_and_names_the_day(connection, clock):
    text = lines(connection)
    assert text[0] == "Hi Maria,"
    assert text[2] == "Here is Rose's day, Wednesday, October 28, from Grandma Buddy."
    assert text[-1] == "Grandma Buddy is an AI helper. It doesn't give medical advice."


def test_without_names_it_still_reads_well(connection, clock):
    connection.execute("UPDATE profile SET preferred_name = '', name = '', family_name = '' WHERE id = 1")
    connection.commit()
    text = lines(connection)
    assert text[0] == "Hi,"
    assert text[2] == "Here is her day, Wednesday, October 28, from Grandma Buddy."


def test_her_mood_is_the_last_she_said_that_day(connection, clock):
    for when, mood in [("2026-10-28T09:00:00", "okay"), ("2026-10-28T16:30:00", "good"), ("2026-10-27T09:00:00", "low")]:
        connection.execute("INSERT INTO moods (created_at, mood, note) VALUES (?, ?, '')", (when, mood))
    connection.commit()
    assert line_starting(connection, "Mood:") == "Mood: Good (at 4:30 PM)"


def test_no_check_in_says_so(connection, clock):
    assert line_starting(connection, "Mood:") == "Mood: No check-in that day."  # right for Yesterday too


def test_pills_count_that_day_only_and_name_what_was_missed(connection, clock):
    pill = add_pill(connection)
    add_reminder(connection, pill, "2026-10-27T18:00:00", "due")  # yesterday: not today's news
    add_reminder(connection, pill, "2026-10-28T08:00:00", "taken")
    add_reminder(connection, pill, "2026-10-28T18:00:00", "due")  # 2 hours ago, no answer: missed
    assert line_starting(connection, "Pills:") == "Pills: 1 of 2 taken. Missed: Metformin at 6:00 PM."


def test_a_day_with_every_pill_taken(connection, clock):
    pill = add_pill(connection)
    add_reminder(connection, pill, "2026-10-28T08:00:00", "taken")
    assert line_starting(connection, "Pills:") == "Pills: 1 of 1 taken."


def test_no_pills_says_so(connection, clock):
    assert line_starting(connection, "Pills:") == "Pills: No pills set up."


def test_a_past_day_counts_up_to_its_midnight(connection, clock):
    pill = add_pill(connection)
    add_reminder(connection, pill, "2026-10-27T08:00:00", "taken")
    add_reminder(connection, pill, "2026-10-27T18:00:00", "due")
    add_reminder(connection, pill, "2026-10-28T08:00:00", "taken")
    assert line_starting(connection, "Pills:", date(2026, 10, 27)) == "Pills: 1 of 2 taken. Missed: Metformin at 6:00 PM."


def at_time(monkeypatch, hour, minute=0):
    """The app's clock: Wednesday, October 28, at this time."""
    monkeypatch.setattr(reminders, "current_time", lambda: datetime(2026, 10, 28, hour, minute))


def test_pills_still_to_come_count_like_the_pills_screen(client, connection, monkeypatch):
    # Mid-afternoon: both morning pills taken, the evening Metformin still to
    # come. The Pills screen's ring says "2 of 3", so the update must too (it
    # said "2 of 2" while it only counted reminders up to now).
    at_time(monkeypatch, 14)
    lisinopril = add_pill(connection, "Lisinopril", times=('"08:00"',))
    metformin = add_pill(connection)
    add_reminder(connection, lisinopril, "2026-10-28T08:00:00", "taken")
    add_reminder(connection, metformin, "2026-10-28T08:00:00", "taken")
    add_reminder(connection, metformin, "2026-10-28T18:00:00", "due")
    ring = client.get("/api/reminders").json()["reminders"]
    assert (sum(r["status"] == "taken" for r in ring), len(ring)) == (2, 3)
    assert line_starting(connection, "Pills:") == "Pills: 2 of 3 taken. Still to come: Metformin at 6:00 PM."


def test_todays_later_pills_count_before_the_app_has_asked_for_them(connection, monkeypatch):
    # No reminder rows yet today (the app wasn't open): the evening pill still
    # counts, as on the Pills screen. 8 AM passed long ago, so it gets none.
    at_time(monkeypatch, 14)
    add_pill(connection)
    assert line_starting(connection, "Pills:") == "Pills: 0 of 1 taken. Still to come: Metformin at 6:00 PM."


def test_a_pill_waiting_for_her_answer_is_due_now(connection, monkeypatch):
    at_time(monkeypatch, 18, 30)
    pill = add_pill(connection)
    add_reminder(connection, pill, "2026-10-28T08:00:00", "taken")
    add_reminder(connection, pill, "2026-10-28T18:00:00", "due")
    assert line_starting(connection, "Pills:") == "Pills: 1 of 2 taken. Due now: Metformin at 6:00 PM."


def test_a_day_without_reminders_says_so(connection, clock):
    add_pill(connection)  # set up, but the app made no reminders that day
    assert line_starting(connection, "Pills:", date(2026, 10, 26)) == "Pills: No reminders that day."


def test_the_diary_lists_that_days_entries_in_her_words(connection, clock):
    db.add_symptom(connection, "The knee is a little better today, about a 2", "check_in")
    connection.execute("UPDATE symptoms SET created_at = '2026-10-28T09:30:00'")
    db.add_symptom(connection, "Something from yesterday", "diary")
    connection.execute("UPDATE symptoms SET created_at = '2026-10-27T09:30:00' WHERE id = 2")
    connection.commit()
    text = lines(connection)
    assert "Diary: 1 new entry" in text
    assert '  - 9:30 AM: "The knee is a little better today, about a 2"' in text
    assert not any("yesterday" in line for line in text)


def test_an_empty_diary_says_so(connection, clock):
    assert "Diary: Nothing new in her diary." in lines(connection)


def test_safety_screens_are_listed_with_fixed_words(connection, clock):
    for when, kind in [("2026-10-28T13:05:00", "poison_control"), ("2026-10-28T20:05:00", "emergency")]:
        connection.execute("INSERT INTO safety_events (created_at, kind, matched, excerpt) VALUES (?, ?, '[]', '')", (when, kind))
    connection.commit()
    text = lines(connection)
    assert "Safety screens:" in text
    assert "  - 1:05 PM: Buddy showed the Poison Control screen." in text
    assert "  - 8:05 PM: Buddy showed the emergency screen (call 911). Please call her." in text


def test_a_crisis_screen_is_listed_but_never_with_her_words(connection, clock):
    connection.execute(
        "INSERT INTO safety_events (created_at, kind, matched, excerpt) VALUES "
        "('2026-10-28T15:10:00', 'crisis', '[\"thoughts of dying or self-harm\"]', 'should never show')"
    )
    connection.commit()
    text = family.summary(connection, TODAY)["text"]
    assert "  - 3:10 PM: Buddy showed her the 988 Suicide & Crisis Lifeline. Please call her today." in text
    assert "dying" not in text and "should never show" not in text


def test_no_safety_screens_says_none(connection, clock):
    assert "Safety screens: none that day." in lines(connection)


def test_no_advice_words_ever(connection, clock):
    text = family.summary(connection, TODAY)["text"].lower()
    for advice in ("should take", "seems", "probably", "worse", "better off", "you should"):
        assert advice not in text


# ---------- The email ----------

def test_the_email_opens_written_and_addressed(connection, clock):
    update = family.summary(connection, TODAY)
    link = urlsplit(update["mailto"])
    assert link.scheme == "mailto" and unquote(link.path) == "maria@example.com"
    fields = parse_qs(link.query)
    assert fields["subject"] == ["Rose's day: Wednesday, October 28"]
    assert fields["body"][0].replace("\r\n", "\n") == update["text"]
    assert "%0D%0A" in update["mailto"] and "+" not in update["mailto"]


def test_with_no_email_the_email_app_asks_who_to_send_to(connection, clock):
    connection.execute("UPDATE profile SET family_email = '' WHERE id = 1")
    connection.commit()
    update = family.summary(connection, TODAY)
    assert update["mailto"].startswith("mailto:?subject=")
    assert update["to"] == ""


# ---------- The route ----------

def test_the_route_gives_today_by_default(client, clock):
    assert client.get("/api/family/summary").json()["date"] == "2026-10-28"


def test_the_route_gives_an_earlier_day(client, clock):
    assert client.get("/api/family/summary?date=2026-10-27").json()["subject"].endswith("Tuesday, October 27")


@pytest.mark.parametrize("day", ["tomorrow", "2026-13-01", "2026-10-29", "2026-09-27"])
def test_a_strange_or_far_away_day_is_refused(client, clock, day):
    assert client.get(f"/api/family/summary?date={day}").status_code == 400
