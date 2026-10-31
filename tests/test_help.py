# Tests for Help, "How Buddy works": every feature with the Meta model
# behind it, read from the app's own settings, so the page always says what
# really runs. Only standard models (never "-contributor", where Meta may
# train on what she says). And Buddy can open Help when she asks.

import json

import pytest
from fastapi.testclient import TestClient

from app import config, db, guard, tools
from app.main import app


@pytest.fixture
def how():
    return TestClient(app).get("/api/how").json()


def test_every_meta_model_the_app_uses_is_listed_once(how):
    assert [model["id"] for model in how["models"]] == [
        "muse-spark-1.3", "muse-voice-transcribe-1.0", "muse-image-1.0", "sam-3.1"]
    assert all(model["name"] and model["does"] for model in how["models"])


def test_the_page_follows_the_settings(how, monkeypatch):
    monkeypatch.setenv("CHAT_MODEL", "muse-spark-1.2")
    changed = TestClient(app).get("/api/how").json()
    assert changed["models"][0]["id"] == "muse-spark-1.2"
    talking = next(feature for feature in changed["features"] if feature["name"] == "Talking with Buddy")
    assert "muse-spark-1.2" in talking["models"]


def test_each_feature_names_only_models_the_app_uses(how):
    used = {model["id"] for model in how["models"]}
    assert len(how["features"]) >= 9
    for feature in how["features"]:
        assert feature["what"], feature
        assert set(feature["models"]) <= used, feature
        # A feature with no Meta model runs on this computer, and says so.
        assert feature["models"] or feature["here"], feature


def test_every_sentence_on_the_page_passes_the_advice_guard(how):
    # The page describes health features: it must never read as advice.
    texts = [model["does"] for model in how["models"]]
    texts += [text for feature in how["features"] for text in (feature["what"], feature["here"]) if text]
    flagged = [text for text in texts if guard.check_reply(text)]
    assert flagged == []


def test_the_safety_net_runs_without_any_ai(how):
    safety_net = next(feature for feature in how["features"] if feature["name"] == "The safety net")
    assert safety_net["models"] == []


@pytest.mark.parametrize("setting", ["CHAT_MODEL", "TRANSCRIBE_MODEL", "IMAGE_MODEL", "SAM_MODEL"])
def test_a_contributor_model_is_refused(monkeypatch, setting):
    # Contributor mode lets Meta train on what she says, and this app holds
    # her health information: the app refuses to start with one.
    monkeypatch.setenv(setting, "muse-spark-1.3-contributor")
    with pytest.raises(ValueError, match="standard"):
        config.get_settings()


def test_buddy_can_open_help_when_she_asks(safe_test_setup):
    connection = db.get_connection(safe_test_setup)
    context = {"connection": connection, "profile": db.get_profile(connection), "conversation_id": "day", "mode": "chat"}
    result, actions = tools.run_tool("open_screen", json.dumps({"screen": "help"}), context)
    connection.close()
    assert result == {"ok": True}
    assert actions == [{"type": "open", "screen": "help", "label": "Open Help"}]
