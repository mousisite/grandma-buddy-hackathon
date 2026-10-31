# Tests for Doctor notes (docs/SPEC.md feature 8): the facts come straight
# from the logs (plain code), the AI only groups her diary entries into
# topics, and every grouping is checked. Also the "Asked" button and the
# demo-data script. The AI is always FAKE here. Made-up data only.

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, meta_client, notes, reminders
from app.main import app

NOW = datetime(2026, 10, 28, 15, 0)  # Wednesday afternoon


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
    yield opened
    opened.close()


def add_entry(connection, when, words, where="", pain=None, since="", source="diary"):
    cursor = connection.execute(
        "INSERT INTO symptoms (created_at, description, body_area, pain_level, since, source) VALUES (?, ?, ?, ?, ?, ?)",
        (when, words, where, pain, since, source),
    )
    connection.commit()
    return cursor.lastrowid


def use_ai(monkeypatch, answer):
    calls = []

    def fake(messages, name, schema, reasoning="medium"):
        calls.append({"messages": messages, "name": name, "schema": schema, "reasoning": reasoning})
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(meta_client, "structured", fake)
    return calls


# ---------- The facts, straight from the logs ----------

def test_her_words_and_facts_are_kept_exactly(connection, clock):
    add_entry(connection, "2026-10-26T09:15:00", "My left knee is sore when I walk, about a 4", "left knee", 4, "since Sunday")
    entry = notes.gather(connection, 7)["symptoms"][0]
    assert entry["words"] == "My left knee is sore when I walk, about a 4"
    assert (entry["where"], entry["pain"], entry["since"]) == ("left knee", 4, "since Sunday")
    assert (entry["date"], entry["time"]) == ("Mon, Oct 26", "9:15 AM")


def test_only_the_chosen_days_are_included(connection, clock):
    add_entry(connection, "2026-10-21T10:00:00", "Too long ago")  # 8 days back
    add_entry(connection, "2026-10-22T10:00:00", "The first day of the week")
    facts = notes.gather(connection, 7)
    assert [e["words"] for e in facts["symptoms"]] == ["The first day of the week"]
    assert facts["period"] == "October 22 to 28"
    assert len(notes.gather(connection, 14)["symptoms"]) == 2


def test_a_period_across_two_months_names_both(connection, clock):
    assert notes.gather(connection, 30)["period"] == "September 29 to October 28"


def test_an_emergency_screen_entry_says_so_and_is_not_quoted(connection, clock):
    add_entry(connection, "2026-10-27T20:00:00", "my chest feels really tight", source="safety_net")
    entry = notes.gather(connection, 7)["symptoms"][0]
    assert entry["note"] == "Buddy showed the emergency screen."
    assert entry["quoted"] is True
    add_entry(connection, "2026-10-27T21:00:00", "Emergency warning signs (chest pain)", source="safety_net")
    assert notes.gather(connection, 7)["symptoms"][1]["quoted"] is False  # not her words


def test_crisis_events_are_never_on_the_page(connection, clock):
    db.add_safety_event(connection, "crisis", ["thoughts of dying or self-harm"], "")
    connection.commit()
    facts = notes.gather(connection, 7)
    assert "crisis" not in json.dumps(facts).lower()


def test_pills_count_taken_and_missed_with_the_label_exactly_as_typed(connection, clock):
    connection.execute("INSERT INTO medications (name, label_dose, times, active) VALUES (?, ?, ?, 1)",
                       ("Lisinopril", "10 mg tablet, take 1 by mouth daily", '["08:00"]'))
    pill = connection.execute("SELECT id FROM medications").fetchone()["id"]
    for day, status in [(26, "taken"), (27, "due"), (28, "taken")]:  # the 27th was never answered: missed
        connection.execute("INSERT INTO med_events (medication_id, due_at, status, acted_at) VALUES (?, ?, ?, ?)",
                           (pill, f"2026-10-{day}T08:00:00", status, f"2026-10-{day}T08:05:00" if status == "taken" else ""))
    connection.commit()
    [pills] = notes.gather(connection, 7)["pills"]
    assert (pills["name"], pills["label"]) == ("Lisinopril", "10 mg tablet, take 1 by mouth daily")
    assert (pills["taken"], pills["total"]) == (2, 3)
    assert pills["missed"] == ["Tue, Oct 27, 8:00 AM"]


def test_a_pill_due_right_now_is_not_counted_yet(connection, clock):
    connection.execute("INSERT INTO medications (name, label_dose, times, active) VALUES ('Vitamin D', '1 softgel', '[\"14:00\"]', 1)")
    connection.execute("INSERT INTO med_events (medication_id, due_at, status) VALUES (1, '2026-10-28T14:00:00', 'due')")
    connection.commit()
    assert notes.gather(connection, 7)["pills"][0]["total"] == 0


def test_one_mood_per_day_the_last_one_said(connection, clock):
    for when, mood in [("2026-10-26T09:00:00", "good"), ("2026-10-26T19:00:00", "low"), ("2026-10-27T09:00:00", "very_low")]:
        connection.execute("INSERT INTO moods (created_at, mood, note) VALUES (?, ?, '')", (when, mood))
    connection.commit()
    assert notes.gather(connection, 7)["moods"] == [{"day": "Mon, Oct 26", "mood": "Low"}, {"day": "Tue, Oct 27", "mood": "Very low"}]


def test_questions_say_whether_they_were_asked_in_these_days(connection, clock):
    first = db.add_doctor_question(connection, "Is it okay to keep walking every day?")
    db.add_doctor_question(connection, "Can I take my pills with coffee?")
    long_ago = db.add_doctor_question(connection, "Should I bring my pill bottles?")
    before = db.add_doctor_question(connection, "Is the clinic open on Saturdays?")
    connection.execute("UPDATE doctor_questions SET resolved = 1, asked_at = '2026-10-27T10:00:00' WHERE id = ?", (first,))
    connection.execute("UPDATE doctor_questions SET resolved = 1, asked_at = '2026-10-01T10:00:00' WHERE id = ?", (long_ago,))
    # Asked before the app kept the day it was asked: it stays off the page.
    connection.execute("UPDATE doctor_questions SET resolved = 1 WHERE id = ?", (before,))
    connection.commit()
    assert [(q["question"], q["asked"]) for q in notes.gather(connection, 7)["questions"]] == [
        ("Is it okay to keep walking every day?", True),
        ("Can I take my pills with coffee?", False),
    ]


# ---------- The AI only groups, and every grouping is checked ----------

def two_knees_and_a_head(connection):
    knee1 = add_entry(connection, "2026-10-23T09:00:00", "My left knee is sore", "left knee", 4)
    head = add_entry(connection, "2026-10-24T15:00:00", "My head hurts, a headache since lunch", "head")
    knee2 = add_entry(connection, "2026-10-26T09:00:00", "The knee hurts going up the stairs", "left knee", 5)
    return knee1, head, knee2


def test_a_good_grouping_from_the_ai_is_used(connection, clock, monkeypatch):
    knee1, head, knee2 = two_knees_and_a_head(connection)
    calls = use_ai(monkeypatch, {"topics": [{"label": "Left knee", "entry_ids": [knee2, knee1]},
                                            {"label": "Headache", "entry_ids": [head]}]})
    topics = notes.notes(connection, 7)["topics"]
    assert [t["label"] for t in topics] == ["Left knee", "Headache"]
    assert [e["id"] for e in topics[0]["entries"]] == [knee1, knee2]  # by date
    assert calls[0]["name"] == "symptom_topics" and calls[0]["reasoning"] == "low"


@pytest.mark.parametrize("bad", [
    "invented label",  # "Arthritis": she never said it
    "long label",  # a label is a short topic, never a sentence built from her words

    "made-up id",
    "entry left out",
    "entry twice",
    "ai down",
])
def test_a_bad_grouping_falls_back_to_where_she_said_it_hurts(connection, clock, monkeypatch, bad):
    knee1, head, knee2 = two_knees_and_a_head(connection)
    answers = {
        "invented label": {"topics": [{"label": "Arthritis", "entry_ids": [knee1, knee2]}, {"label": "Headache", "entry_ids": [head]}]},
        "long label": {"topics": [{"label": "The knee hurts going up the stairs", "entry_ids": [knee1, knee2]},
                                  {"label": "Headache", "entry_ids": [head]}]},
        "made-up id": {"topics": [{"label": "Left knee", "entry_ids": [knee1, knee2, 999]}, {"label": "Headache", "entry_ids": [head]}]},
        "entry left out": {"topics": [{"label": "Left knee", "entry_ids": [knee1, knee2]}]},
        "entry twice": {"topics": [{"label": "Left knee", "entry_ids": [knee1, knee2, head]}, {"label": "Headache", "entry_ids": [head]}]},
        "ai down": meta_client.MetaError("down"),
    }
    use_ai(monkeypatch, answers[bad])
    topics = notes.notes(connection, 7)["topics"]
    assert [(t["label"], [e["id"] for e in t["entries"]]) for t in topics] == [("Left knee", [knee1, knee2]), ("Head", [head])]


def test_entries_with_no_place_go_under_other_things(connection, clock, monkeypatch):
    use_ai(monkeypatch, meta_client.MetaError("down"))
    add_entry(connection, "2026-10-25T09:00:00", "I felt dizzy when I stood up")
    assert notes.notes(connection, 7)["topics"][0]["label"] == "Other things"


def test_no_entries_means_no_ai_call(connection, clock, monkeypatch):
    calls = use_ai(monkeypatch, {"topics": []})
    assert notes.notes(connection, 7)["topics"] == []
    assert calls == []


def test_the_page_knows_her_name_and_her_doctor(client, clock, monkeypatch):
    client.put("/api/profile", json={"preferred_name": "Rose", "doctor_name": "Dr. Lee"})
    use_ai(monkeypatch, {"topics": []})
    page = client.get("/api/doctor-notes?days=7").json()
    assert (page["her_name"], page["doctor_name"], page["period"]) == ("Rose", "Dr. Lee", "October 22 to 28")


# ---------- The routes ----------

@pytest.mark.parametrize("days", [0, 3, 31, 365])
def test_only_7_14_or_30_days_can_be_asked_for(client, days):
    assert client.get(f"/api/doctor-notes?days={days}").status_code == 400


def test_mark_as_asked_keeps_it_on_the_page_with_a_check_and_undo_takes_it_back(client, clock, monkeypatch):
    use_ai(monkeypatch, {"topics": []})
    question = client.post("/api/doctor-questions", json={"question": "Can I take my pills with coffee?"}).json()
    shown = {"id": question["id"], "question": "Can I take my pills with coffee?"}
    assert client.post(f"/api/doctor-questions/{question['id']}/asked").status_code == 200
    assert client.get("/api/doctor-notes?days=7").json()["questions"] == [{**shown, "asked": True}]
    assert client.post(f"/api/doctor-questions/{question['id']}/reopen").status_code == 200
    assert client.get("/api/doctor-notes?days=7").json()["questions"] == [{**shown, "asked": False}]


def test_home_can_ask_how_many_questions_are_still_to_ask(client, safe_test_setup):
    # Home's "Questions for your next doctor visit" row says "2 to ask".
    assert client.get("/api/doctor-questions").json() == {"to_ask": 0}
    first = client.post("/api/doctor-questions", json={"question": "Can I keep walking every day?"}).json()
    client.post("/api/doctor-questions", json={"question": "Is my knee okay to swim with?"})
    assert client.get("/api/doctor-questions").json() == {"to_ask": 2}
    client.post(f"/api/doctor-questions/{first['id']}/asked")
    assert client.get("/api/doctor-questions").json() == {"to_ask": 1}


def test_asking_about_a_question_that_is_not_there(client):
    assert client.post("/api/doctor-questions/999/asked").status_code == 404


# ---------- The demo week (scripts/seed_demo.py) ----------

def load_seed_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location("seed_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEEDED = ("symptoms", "medications", "med_events", "moods", "check_ins", "doctor_questions", "scam_checks",
          "memories", "facts", "style_notes", "talk_summaries")


def counts(path):
    connection = db.get_connection(path)
    found = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in SEEDED}
    connection.close()
    return found


def test_the_demo_week_fills_every_screen(safe_test_setup):
    assert load_seed_script().main(["--no-paint"]) == 0
    found = counts(safe_test_setup)
    assert found == dict(found, medications=2, moods=5, check_ins=5, symptoms=5, doctor_questions=2, scam_checks=1,
                         memories=2, style_notes=3, talk_summaries=3)
    connection = db.get_connection(safe_test_setup)
    taken = connection.execute("SELECT COUNT(*) FROM med_events WHERE status = 'taken'").fetchone()[0]
    moods = {row[0] for row in connection.execute("SELECT mood FROM moods")}
    knee = [row[0] for row in connection.execute("SELECT description FROM symptoms")]
    facts = " ".join(row[0] for row in connection.execute("SELECT fact FROM facts"))
    scam = connection.execute("SELECT verdict, excerpt FROM scam_checks").fetchone()
    profile = db.get_profile(connection)
    connection.close()
    assert taken >= 6 and len(moods) >= 3  # some pills taken; mixed moods
    assert all("knee" in words.lower() for words in knee)  # the knee pain that comes and goes, in her words
    assert "Leo" in facts and "gardening" in facts
    assert scam["verdict"] == "likely_scam" and not any(ch.isdigit() for ch in scam["excerpt"].replace("2,000", ""))
    assert (profile["preferred_name"], profile["family_name"], profile["family2_name"]) == ("Rose", "Maria", "Daniel")


def test_the_demo_week_is_made_up(safe_test_setup):
    load_seed_script().main(["--no-paint"])
    connection = db.get_connection(safe_test_setup)
    profile = db.get_profile(connection)
    connection.close()
    for field in ("family_phone", "family2_phone", "doctor_phone"):
        assert profile[field].startswith("555-"), field  # 555 numbers are reserved for fiction
    assert profile["family_email"].endswith("@example.com")


def test_the_memory_pages_are_painted_unless_told_not_to(safe_test_setup, monkeypatch):
    from app import meta_client
    painted = []
    monkeypatch.setattr(meta_client, "paint", lambda prompt: painted.append(prompt) or b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24)
    assert load_seed_script().main([]) == 0
    assert len(painted) == 2
    connection = db.get_connection(safe_test_setup)
    assert [row[0] for row in connection.execute("SELECT status FROM memories")] == ["ready", "ready"]
    connection.close()


def test_the_demo_week_never_overwrites_data_without_reset(safe_test_setup):
    seed = load_seed_script()
    seed.main(["--no-paint"])
    before = counts(safe_test_setup)
    assert seed.main(["--no-paint"]) == 1  # refuses: there is data already
    assert counts(safe_test_setup) == before


def test_reset_keeps_a_backup_then_starts_from_an_empty_database(safe_test_setup):
    seed = load_seed_script()
    seed.main(["--no-paint"])
    connection = db.get_connection(safe_test_setup)
    db.add_symptom(connection, "An extra entry from before", "chat")
    connection.commit()
    connection.close()
    assert seed.main(["--reset", "--no-paint"]) == 0
    backups = list(Path(safe_test_setup).parent.glob("backup-*.db"))
    assert len(backups) == 1
    assert counts(str(backups[0]))["symptoms"] == 6  # the old data, kept in the backup
    assert counts(safe_test_setup)["symptoms"] == 5  # wiped, then the demo week again
