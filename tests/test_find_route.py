# Tests for "Find my things" as she uses it: POST /api/find (the safety net
# first, the photo checked and never kept) and Buddy's find_my_things tool
# for "Buddy, where are my glasses?". Every Meta call is faked.

import json

import pytest
from fastapi.testclient import TestClient

from app import db, finder, meta_client, tools
from app.main import app
from tests.test_companion import reply, tool_call, use_fake
from tests.test_finder import ONE_MATCH, PHOTO, FakeSpark


@pytest.fixture
def client():
    return TestClient(app)


class FakeSam:
    """Stands in for meta_client.segment: remembers each look."""

    def __init__(self, line="", error=None):
        self.line = line
        self.error = error
        self.calls = []

    def __call__(self, image, phrase):
        self.calls.append((image, phrase))
        if self.error:
            raise self.error
        return self.line


def test_finding_her_glasses_returns_the_box_and_what_buddy_says(client, monkeypatch):
    sam = FakeSam(ONE_MATCH)
    monkeypatch.setattr(meta_client, "segment", sam)
    monkeypatch.setattr(meta_client, "structured", FakeSpark("Your glasses are on the table, next to the lamp."))
    answer = client.post("/api/find", json={"thing": "Where are my glasses?", "image": PHOTO})
    assert answer.status_code == 200
    assert answer.json() == {
        "found": True,
        "thing": "glasses",
        "sentence": "Your glasses are on the table, next to the lamp.",
        "box": {"x1": 100, "y1": 200, "x2": 199, "y2": 259},
        "width": 1000,
        "height": 800,
    }
    assert sam.calls == [(PHOTO, "glasses")]  # SAM gets a short noun phrase


def test_nothing_found_is_said_kindly_without_asking_spark(client, monkeypatch):
    spark = FakeSpark("should not be used")
    monkeypatch.setattr(meta_client, "segment", FakeSam(""))
    monkeypatch.setattr(meta_client, "structured", spark)
    answer = client.post("/api/find", json={"thing": "umbrella", "image": PHOTO}).json()
    assert answer == {"found": False, "thing": "umbrella", "sentence": finder.not_found("umbrella")}
    assert spark.calls == []


def test_the_safety_net_runs_first_on_what_she_said(client, monkeypatch, safe_test_setup):
    sam = FakeSam(ONE_MATCH)
    monkeypatch.setattr(meta_client, "segment", sam)
    answer = client.post("/api/find", json={"thing": "my pills, I took my pills twice by accident", "image": PHOTO})
    assert answer.json()["show"] == "poison_control"
    assert "Poison Control" in answer.json()["reply"]
    assert sam.calls == []  # no AI at all
    connection = db.get_connection(safe_test_setup)
    assert connection.execute("SELECT kind FROM safety_events").fetchone()[0] == "poison_control"
    connection.close()


def test_looking_for_her_pills_is_not_a_safety_screen(client, monkeypatch):
    # A near miss: "pills" alone is just a thing she lost, not a mix-up.
    sam = FakeSam(ONE_MATCH)
    monkeypatch.setattr(meta_client, "segment", sam)
    monkeypatch.setattr(meta_client, "structured", FakeSpark("Your pill bottle is by the kettle."))
    answer = client.post("/api/find", json={"thing": "Where are my pills?", "image": PHOTO}).json()
    assert "show" not in answer
    assert (answer["thing"], answer["sentence"]) == ("pill bottle", "Your pill bottle is by the kettle.")
    assert sam.calls == [(PHOTO, "medicine bottle")]  # the words SAM knows (it finds nothing for "pill bottle")


@pytest.mark.parametrize("image", [
    "",
    "not a photo",
    "data:text/html;base64,PGgxPg==",
    "data:image/jpeg;base64," + "A" * 7_000_000,  # too big
], ids=["empty", "words", "a web page", "too big"])
def test_a_bad_photo_is_refused_kindly(client, monkeypatch, image):
    sam = FakeSam(ONE_MATCH)
    monkeypatch.setattr(meta_client, "segment", sam)
    answer = client.post("/api/find", json={"thing": "keys", "image": image})
    assert answer.status_code == 400
    assert "photo" in answer.json()["detail"]
    assert sam.calls == []


def test_she_has_to_say_what_she_is_looking_for(client, monkeypatch):
    monkeypatch.setattr(meta_client, "segment", FakeSam(ONE_MATCH))
    answer = client.post("/api/find", json={"thing": "where are my", "image": PHOTO})
    assert answer.status_code == 400
    assert "looking for" in answer.json()["detail"]


def test_when_meta_is_down_she_hears_a_kind_message(client, monkeypatch):
    monkeypatch.setattr(meta_client, "segment", FakeSam(error=meta_client.MetaError("down")))
    answer = client.post("/api/find", json={"thing": "keys", "image": PHOTO})
    assert answer.status_code == 503
    assert answer.json()["detail"] == finder.LOOK_FAILED


def test_her_photo_is_never_kept(client, monkeypatch, safe_test_setup, tmp_path):
    monkeypatch.setattr(meta_client, "segment", FakeSam(ONE_MATCH))
    monkeypatch.setattr(meta_client, "structured", FakeSpark("Your keys are by the fruit bowl."))
    client.post("/api/find", json={"thing": "keys", "image": PHOTO})
    connection = db.get_connection(safe_test_setup)
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    for table in tables:
        for row in connection.execute(f"SELECT * FROM {table}"):
            assert not any(isinstance(value, str) and "base64" in value for value in row), table
    connection.close()
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        path.name for path in tmp_path.iterdir() if path.name.startswith("test.db"))


# ---------- "Buddy, where are my glasses?" ----------

def tool_context(safe_test_setup):
    connection = db.get_connection(safe_test_setup)
    return {"connection": connection, "profile": db.get_profile(connection), "conversation_id": "day", "mode": "chat"}


def test_find_my_things_tool_shows_a_find_button(safe_test_setup):
    context = tool_context(safe_test_setup)
    result, actions = tools.run_tool("find_my_things", json.dumps({"thing": "my reading glasses"}), context)
    assert result["ok"] is True
    assert actions == [{"type": "find", "thing": "reading glasses", "label": "Find my reading glasses"}]
    context["connection"].close()


def test_find_my_things_tool_needs_a_thing(safe_test_setup):
    context = tool_context(safe_test_setup)
    result, actions = tools.run_tool("find_my_things", json.dumps({"thing": "  "}), context)
    assert result["ok"] is False and actions == []
    context["connection"].close()


def test_asking_buddy_where_her_glasses_are_gives_the_find_button(client, monkeypatch):
    use_fake(monkeypatch,
             tool_call("call-1", "find_my_things", {"thing": "glasses"}),
             reply("Let's look together! Tap the button and take a photo of the room."))
    answer = client.post("/api/chat", json={"text": "Buddy, where are my glasses?", "conversation_id": "find-1"}).json()
    assert answer["reply"].startswith("Let's look together!")
    assert {"type": "find", "thing": "glasses", "label": "Find my glasses"} in answer["actions"]
