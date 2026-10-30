# Tests for the first-time welcome: a second family member in her profile,
# and the safety net on the words she says during the welcome ("Say it"),
# which never go to the AI. Made-up data only.

import pytest
from fastapi.testclient import TestClient

from app import db, meta_client
from app.main import app


@pytest.fixture
def client(monkeypatch):
    def no_ai(*args, **kwargs):
        raise AssertionError("The welcome must never ask the AI.")

    monkeypatch.setattr(meta_client, "chat", no_ai)
    return TestClient(app)


def test_a_second_family_member_is_saved(client):
    saved = client.put("/api/profile", json={"family2_name": "Daniel", "family2_phone": "555-0144"}).json()
    assert (saved["family2_name"], saved["family2_phone"]) == ("Daniel", "555-0144")


def test_a_bad_second_phone_number_is_refused_and_named(client):
    answer = client.put("/api/profile", json={"family2_phone": "call him"})
    assert answer.status_code == 400
    assert answer.json()["detail"]["field"] == "family2_phone"
    assert "second family member" in answer.json()["detail"]["message"]


def test_words_heard_in_the_welcome_go_through_the_safety_net(client, safe_test_setup):
    client.put("/api/profile", json={"family_name": "Maria", "family_phone": "555-0100"})
    answer = client.post("/api/check-words", json={"text": "my chest feels really tight"}).json()
    assert answer["show"] == "emergency"
    assert answer["reply"] == "This could be an emergency. If it is, please call 911 right now."
    assert {"label": "Call 911", "href": "tel:911"} in [{"label": a["label"], "href": a["href"]} for a in answer["actions"]]
    connection = db.get_connection(safe_test_setup)
    assert connection.execute("SELECT kind FROM safety_events").fetchone()[0] == "emergency"
    connection.close()


def test_crisis_words_heard_in_the_welcome_are_never_kept(client, safe_test_setup):
    answer = client.post("/api/check-words", json={"text": "I wish I wasn't here anymore"}).json()
    assert answer["show"] == "crisis"
    connection = db.get_connection(safe_test_setup)
    assert connection.execute("SELECT excerpt FROM safety_events").fetchone()[0] == ""
    connection.close()


def test_ordinary_words_heard_in_the_welcome_pass(client):
    assert client.post("/api/check-words", json={"text": "My name is Rose"}).json() == {"show": None}
