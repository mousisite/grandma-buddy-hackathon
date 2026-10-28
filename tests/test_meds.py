# Tests for her pills: /api/meds (a family member sets them up),
# /api/reminders (the banner and the Pills screen), and the two pill tools
# the AI can use. A clock the test moves stands in for real time.
# Made-up pills only.

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import db, reminders, tools
from app.main import app

LABEL = "10 mg tablet, take 1 by mouth daily"


@pytest.fixture
def clock(monkeypatch):
    """The time the app sees. clock.set(8, 30) moves it to 8:30 AM, October 27."""

    class Clock:
        now = datetime(2026, 10, 27, 7, 0)

        def set(self, hour, minute=0, day=27):
            self.now = datetime(2026, 10, day, hour, minute)

    test_clock = Clock()
    monkeypatch.setattr(reminders, "current_time", lambda: test_clock.now)
    return test_clock


@pytest.fixture
def client():
    return TestClient(app)


def add_pill(client, name="Lisinopril", label=LABEL, times=("08:00",)):
    return client.post("/api/meds", json={"name": name, "label_dose": label, "times": list(times)})


def statuses(client):
    return [(r["name"], r["due_at"][11:16], r["status"]) for r in client.get("/api/reminders").json()["reminders"]]


# ---------- Setting up pills ----------

def test_a_family_member_adds_a_pill_exactly_as_on_the_label(client, clock):
    assert add_pill(client).status_code == 200
    pills = client.get("/api/meds").json()
    assert [(p["name"], p["label_dose"], p["times"]) for p in pills] == [("Lisinopril", LABEL, ["08:00"])]


def test_times_are_tidied(client, clock):
    add_pill(client, times=["20:00", "08:00", "08:00"])
    assert client.get("/api/meds").json()[0]["times"] == ["08:00", "20:00"]


@pytest.mark.parametrize("changes, field", [
    ({"name": " "}, "name"),
    ({"name": "x" * 81}, "name"),
    ({"times": []}, "times"),
    ({"times": ["25:00"]}, "times"),
    ({"times": ["8 in the morning"]}, "times"),
    ({"times": "08:00"}, "times"),
    ({"times": ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00"]}, "times"),
    ({"label_dose": "x" * 201}, "label_dose"),
])
def test_odd_pill_entries_are_refused_and_named(client, clock, changes, field):
    pill = {"name": "Lisinopril", "label_dose": LABEL, "times": ["08:00"], **changes}
    refused = client.post("/api/meds", json=pill)
    assert refused.status_code == 400
    assert refused.json()["detail"]["field"] == field


# ---------- Reminders through the day ----------

def test_a_reminder_is_due_at_its_time_and_repeats_the_label_exactly(client, clock):
    add_pill(client)
    assert statuses(client) == [("Lisinopril", "08:00", "upcoming")]
    assert client.get("/api/reminders").json()["due_words"] == ""
    clock.set(8, 0)
    body = client.get("/api/reminders").json()
    assert [r["status"] for r in body["reminders"]] == ["due"]
    assert body["due_words"] == "It’s time for your morning pill: Lisinopril, 10 mg tablet, take 1 by mouth daily."


def test_remind_me_later_then_i_took_it(client, clock):
    add_pill(client)
    clock.set(8, 0)
    ids = [r["id"] for r in client.get("/api/reminders").json()["reminders"]]
    assert client.post("/api/reminders/snooze", json={"ids": ids}).status_code == 200
    assert statuses(client) == [("Lisinopril", "08:00", "snoozed")]
    clock.set(8, 10)
    assert statuses(client) == [("Lisinopril", "08:00", "due")]
    client.post("/api/reminders/taken", json={"ids": ids})
    assert statuses(client) == [("Lisinopril", "08:00", "taken")]
    assert client.get("/api/reminders").json()["due_words"] == ""


def test_no_answer_for_two_hours_is_missed_and_taking_it_late_still_counts(client, clock):
    add_pill(client)
    statuses(client)  # the open page checks (every 30 seconds), so the 8 AM reminder exists
    clock.set(10, 0)
    assert statuses(client) == [("Lisinopril", "08:00", "missed")]
    ids = [r["id"] for r in client.get("/api/reminders").json()["reminders"]]
    client.post("/api/reminders/taken", json={"ids": ids})
    assert statuses(client) == [("Lisinopril", "08:00", "taken")]


def test_checking_every_30_seconds_never_makes_copies(client, clock, safe_test_setup):
    add_pill(client, times=["08:00", "20:00"])
    for _ in range(3):
        client.get("/api/reminders")
    connection = db.get_connection(safe_test_setup)
    count = connection.execute("SELECT COUNT(*) FROM med_events").fetchone()[0]
    connection.close()
    assert count == 2


def test_a_reminder_is_only_missed_if_buddy_could_show_it(client, clock):
    # The tablet was off from 7 to 10 AM: Buddy never reminded her, so it
    # doesn't tell her family she missed it.
    add_pill(client)
    clock.set(10, 0)
    assert statuses(client) == []


def test_a_pill_added_at_noon_has_no_missed_morning_reminder(client, clock):
    clock.set(12, 0)
    add_pill(client, times=["08:00", "20:00"])
    assert statuses(client) == [("Lisinopril", "20:00", "upcoming")]


def test_removing_a_pill_stops_its_reminders_and_undo_brings_them_back(client, clock):
    pill_id = add_pill(client).json()["id"]
    clock.set(8, 0)
    assert client.delete(f"/api/meds/{pill_id}").status_code == 200
    assert client.get("/api/meds").json() == []
    assert statuses(client) == []
    assert client.post(f"/api/meds/{pill_id}/restore").status_code == 200
    assert statuses(client) == [("Lisinopril", "08:00", "due")]


def test_changing_a_pills_time_moves_todays_reminder(client, clock):
    pill_id = add_pill(client).json()["id"]
    clock.set(8, 30)
    assert statuses(client) == [("Lisinopril", "08:00", "due")]
    client.put(f"/api/meds/{pill_id}", json={"name": "Lisinopril", "label_dose": LABEL, "times": ["09:00"]})
    assert statuses(client) == [("Lisinopril", "09:00", "upcoming")]


def test_last_nights_late_reminder_still_shows_just_after_midnight(client, clock):
    clock.set(23, 0)
    add_pill(client, times=["23:30"])
    statuses(client)  # the open page checks
    clock.set(0, 15, day=28)
    assert statuses(client) == [("Lisinopril", "23:30", "due"), ("Lisinopril", "23:30", "upcoming")]


def test_the_page_knows_when_no_pills_are_set_up(client, clock):
    assert client.get("/api/reminders").json()["has_pills"] is False
    add_pill(client)
    assert client.get("/api/reminders").json()["has_pills"] is True


@pytest.mark.parametrize("body", [{"ids": "1"}, {"ids": ["a"]}, {"ids": list(range(25))}, {}])
def test_odd_reminder_answers_are_refused(client, clock, body):
    assert client.post("/api/reminders/taken", json=body).status_code == 400


# ---------- The AI's pill tools ----------

def run(tool_name, args, path):
    connection = db.get_connection(path)
    context = {"connection": connection, "profile": db.get_profile(connection), "conversation_id": "d", "mode": "chat"}
    result, buttons = tools.run_tool(tool_name, json.dumps(args), context)
    connection.commit()
    connection.close()
    return result


def test_buddy_hears_pill_names_and_times_but_never_the_label(client, clock, safe_test_setup):
    add_pill(client)
    result = run("get_pills_due", {}, safe_test_setup)
    assert result["pills"] == [{"name": "Lisinopril", "time": "8:00 AM", "status": "upcoming"}]
    assert "10 mg" not in json.dumps(result)


def test_buddy_marks_pills_taken_when_she_says_so(client, clock, safe_test_setup):
    add_pill(client)
    add_pill(client, name="Vitamin D", label="1 softgel daily")
    clock.set(8, 5)
    assert run("mark_pill_taken", {"medication_name": "lisinopril"}, safe_test_setup)["marked"] == ["Lisinopril"]
    assert run("mark_pill_taken", {"medication_name": "all"}, safe_test_setup)["marked"] == ["Vitamin D"]
    assert statuses(client) == [("Lisinopril", "08:00", "taken"), ("Vitamin D", "08:00", "taken")]


def test_taking_a_pill_a_little_early_counts(client, clock, safe_test_setup):
    add_pill(client, times=["20:00"])
    clock.set(19, 30)
    assert run("mark_pill_taken", {"medication_name": "all"}, safe_test_setup)["marked"] == ["Lisinopril"]


def test_marking_a_pill_that_isnt_due_says_so_kindly(client, clock, safe_test_setup):
    add_pill(client, times=["20:00"])
    clock.set(9, 0)
    result = run("mark_pill_taken", {"medication_name": "all"}, safe_test_setup)
    assert result["ok"] is False
    assert run("mark_pill_taken", {"medication_name": "aspirin"}, safe_test_setup)["ok"] is False


# ---------- Changing and removing pills keeps the record right ----------

def test_moving_a_taken_pill_later_does_not_remind_her_again(client, clock):
    pill_id = add_pill(client).json()["id"]
    statuses(client)
    clock.set(8, 5)
    ids = [r["id"] for r in client.get("/api/reminders").json()["reminders"]]
    client.post("/api/reminders/taken", json={"ids": ids})
    clock.set(8, 30)
    client.put(f"/api/meds/{pill_id}", json={"name": "Lisinopril", "label_dose": LABEL, "times": ["09:00"]})
    clock.set(9, 0)
    assert statuses(client) == [("Lisinopril", "08:00", "taken")]


def test_a_label_only_change_keeps_her_snooze(client, clock):
    pill_id = add_pill(client).json()["id"]
    clock.set(9, 55)
    statuses(client)
    ids = [r["id"] for r in client.get("/api/reminders").json()["reminders"]]
    client.post("/api/reminders/snooze", json={"ids": ids})
    clock.set(10, 0)
    client.put(f"/api/meds/{pill_id}", json={"name": "Lisinopril", "label_dose": "10 mg tablet", "times": ["08:00"]})
    assert statuses(client) == [("Lisinopril", "08:00", "snoozed")]


def test_removing_a_pill_drops_its_waiting_reminder_but_keeps_a_missed_one(client, clock, safe_test_setup):
    pill_id = add_pill(client, times=["08:00", "20:00"]).json()["id"]
    statuses(client)  # 7 AM: both reminders exist
    clock.set(10, 0)
    client.delete(f"/api/meds/{pill_id}")
    connection = db.get_connection(safe_test_setup)
    left = [row["due_at"][11:16] for row in connection.execute("SELECT due_at FROM med_events")]
    connection.close()
    assert left == ["08:00"]
    client.post(f"/api/meds/{pill_id}/restore")
    assert statuses(client) == [("Lisinopril", "08:00", "missed"), ("Lisinopril", "20:00", "upcoming")]


def test_a_missed_reminder_survives_a_change_of_time(client, clock):
    pill_id = add_pill(client).json()["id"]
    statuses(client)
    clock.set(10, 0)
    client.put(f"/api/meds/{pill_id}", json={"name": "Lisinopril", "label_dose": LABEL, "times": ["12:00"]})
    assert statuses(client) == [("Lisinopril", "08:00", "missed")]


# ---------- After a Poison Control screen ----------

def test_after_a_poison_control_screen_the_page_is_told(client, clock):
    add_pill(client)
    assert client.get("/api/reminders").json()["after_poison_control"] is False
    client.post("/api/chat", json={"conversation_id": "t", "text": "I took my pills twice by accident", "mode": "chat"})
    body = client.get("/api/reminders").json()
    assert body["after_poison_control"] is True
    # The banner shows the fixed Poison Control message, word for word (SAFETY.md section 3).
    assert body["poison_control_words"] == (
        "Please call Poison Control now at 1-800-222-1222. It's free. "
        "If you feel very sleepy, confused, or have trouble breathing, call 911."
    )


# ---------- What the AI hears ----------

def test_the_ai_hears_a_pill_name_without_its_strength(client, clock, safe_test_setup):
    add_pill(client, name="Lisinopril 10 mg")
    assert run("get_pills_due", {}, safe_test_setup)["pills"][0]["name"] == "Lisinopril"
