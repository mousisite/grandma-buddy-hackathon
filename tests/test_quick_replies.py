# Tests for the quicker replies (Nov 1): Buddy starts talking sooner.
# - meta_client: chat asks Meta for "minimal" reasoning, and one connection
#   is reused instead of a new one per call
# - companion: a fixed bridge line while a slow tool runs; the nudge when
#   she asks for advice
# - /api/chat streams events when the page asks for them (Accept:
#   application/x-ndjson): the bridge line first, then the whole answer; a
#   safety screen comes at once, with no AI
# The AI is always FAKE here. No test ever reaches the real API.

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import briefing, meta_client, prompts
from tests.test_briefing import OpenMeteo
from app.main import app

original_client = meta_client._client  # the real one, kept before conftest replaces it


def reply(text):
    return {"content": text, "tool_calls": [], "message": {"role": "assistant", "content": text}}


def tool_call(call_id, name, args):
    call = {"id": call_id, "name": name, "arguments": json.dumps(args)}
    message = {"role": "assistant", "content": None,
               "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}
    return {"content": None, "tool_calls": [call], "message": message}


class FakeAI:
    """Scripted answers, in order (like tests/test_companion.py)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, messages, tools=None):
        self.calls.append([dict(m) for m in messages])
        return self.answers.pop(0)


@pytest.fixture
def client():
    return TestClient(app)


def chat(client, text, mode="chat"):
    return client.post("/api/chat", json={"conversation_id": "day1", "text": text, "mode": mode}).json()


def stream(client, text, mode="chat"):
    """The same route, asked for events: the lines it sends, as dictionaries."""
    with client.stream("POST", "/api/chat", json={"conversation_id": "day1", "text": text, "mode": mode},
                       headers={"Accept": "application/x-ndjson"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        return [json.loads(line) for line in response.iter_lines() if line.strip()]


# ---------- meta_client ----------

def test_chat_asks_meta_for_minimal_reasoning(monkeypatch):
    sent = []

    def fake_create(request):
        sent.append(request)
        message = SimpleNamespace(content="Hello.", tool_calls=None, model_dump=lambda **kw: {"role": "assistant", "content": "Hello."})
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])

    monkeypatch.setattr(meta_client, "_create", fake_create)
    assert meta_client.chat([{"role": "user", "content": "hi"}])["content"] == "Hello."
    assert sent[0]["reasoning_effort"] == "minimal"
    assert sent[0]["model"] == "muse-spark-1.3"


def test_one_chat_connection_is_reused_until_the_key_changes(monkeypatch):
    made = []

    class FakeOpenAI:
        def __init__(self, **options):
            made.append(options)

    monkeypatch.setattr(meta_client, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(meta_client, "_clients", {})
    monkeypatch.setattr(meta_client, "_client", original_client)
    first = meta_client._client()
    assert meta_client._client() is first
    assert len(made) == 1
    assert made[0]["api_key"] == "test-key" and made[0]["max_retries"] == 0
    monkeypatch.setenv("MODEL_API_KEY", "another-key")
    assert meta_client._client() is not first
    assert len(made) == 2


# ---------- The bridge line and the stream ----------

def test_a_bridge_line_is_said_while_the_weather_is_looked_up(client, monkeypatch):
    client.put("/api/profile", json={"preferred_name": "Rose", "city": "Portland, Oregon"})
    monkeypatch.setattr(briefing, "look_up", lambda connection, topic, town: {"text": "Showers, high near 59.", "sites": ["Open-Meteo.com"], "from": "Weather from"})
    monkeypatch.setattr(meta_client, "chat", FakeAI(tool_call("c1", "look_up_today", {"topic": "weather"}),
                                                   reply("Showers today, high near 59.")))
    events = stream(client, "What's the weather like?")
    assert [event["type"] for event in events] == ["bridge", "done"]
    assert events[0]["text"] == "Let me look that up."
    assert events[1]["reply"] == "Showers today, high near 59."
    assert {"type": "sources", "sites": ["Open-Meteo.com"], "from": "Weather from"} in events[1]["actions"]


def test_the_stream_shows_the_emergency_screen_at_once_without_the_ai(client, monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("the AI was asked")

    monkeypatch.setattr(meta_client, "chat", must_not_run)
    events = stream(client, "my chest hurts and I can't breathe")
    assert [event["type"] for event in events] == ["done"]
    assert events[0]["show"] == "emergency"
    assert events[0]["actions"][0]["href"] == "tel:911"


def test_the_streamed_answer_has_everything_the_plain_answer_has(client, monkeypatch):
    monkeypatch.setattr(meta_client, "chat", FakeAI(reply("Lovely."), reply("Lovely.")))
    plain = chat(client, "I went out to the garden")
    done = stream(client, "I went out to the garden")[-1]
    assert set(done) == set(plain) | {"type"}
    assert done["reply"] == "Lovely." and done["show"] is None


def test_the_stream_refuses_bad_requests_before_it_starts(client):
    response = client.post("/api/chat", json={"conversation_id": "day1", "text": "hi", "mode": "nope"},
                           headers={"Accept": "application/x-ndjson"})
    assert response.status_code == 400


# ---------- When she asks for advice ----------

def test_buddy_is_told_to_answer_an_advice_question_first(client, monkeypatch):
    fake = FakeAI(reply("I can't give medical advice, Rose. Dr. Lee is the right person."), reply("Lovely."))
    monkeypatch.setattr(meta_client, "chat", fake)
    chat(client, "Should I take something for my headache?")
    assert prompts.ADVICE_ASKED.strip() in fake.calls[0][0]["content"]
    chat(client, "The tulips came up this morning")
    assert prompts.ADVICE_ASKED.strip() not in fake.calls[1][0]["content"]


def test_buddy_is_told_to_look_up_the_weather_she_asks_about(client, monkeypatch):
    """Measured Nov 1: asked "What's the weather like?" right after a talk
    about her tulips, the model once chatted about the tulips instead of
    calling look_up_today."""
    fake = FakeAI(reply("Cloudy today, with a high of 48."), reply("Lovely."))
    monkeypatch.setattr(meta_client, "chat", fake)
    chat(client, "What's the weather like?")
    assert prompts.LOOK_UP_ASKED.strip() in fake.calls[0][0]["content"]
    chat(client, "The tulips came up this morning")
    assert prompts.LOOK_UP_ASKED.strip() not in fake.calls[1][0]["content"]


@pytest.mark.parametrize("words, asks", [
    ("What's the weather like?", True), ("Is it going to rain today", True), ("how cold is it out", True),
    ("anything happening in town this week", True), ("did the Blazers win last night", True),
    ("The tulips came up this morning", False), ("I feel so lonely today", False), ("my knee hurts", False),
])
def test_which_words_ask_about_today(words, asks):
    assert briefing.asks_about_today(words) is asks


# ---------- A weather question: the forecast is fetched first and put in the prompt ----------

def test_a_weather_question_gets_todays_forecast_put_in_the_prompt(client, monkeypatch):
    """Measured Nov 1: asked "What's the weather like?", the model sometimes
    answered without calling look_up_today ("I don't have today's weather in
    front of me"). So plain code fetches it first (Open-Meteo, free) and hands
    it to the model, with the source line added by plain code too."""
    OpenMeteo(monkeypatch)
    client.put("/api/profile", json={"preferred_name": "Rose", "city": "Portland, Oregon"})
    fake = FakeAI(reply("Cloudy today, Rose, with a high of 48 and a low of 41. A good day for tea by the window?"))
    monkeypatch.setattr(meta_client, "chat", fake)
    body = chat(client, "What's the weather like?")
    prompt = fake.calls[0][0]["content"]
    assert "Cloudy today, with a high of 48 and a low of 41." in prompt
    assert prompts.WEATHER_IN_HAND.split("{")[0].strip() in prompt
    assert prompts.LOOK_UP_ASKED.strip() not in prompt
    assert {"type": "sources", "sites": ["Open-Meteo.com"], "from": "Weather from"} in body["actions"]
    assert len(fake.calls) == 1  # one round: no tool needed


def test_without_her_town_a_weather_question_just_asks_to_look_it_up(client, monkeypatch):
    meteo = OpenMeteo(monkeypatch)
    fake = FakeAI(reply("I don't know your town yet, Rose."))
    monkeypatch.setattr(meta_client, "chat", fake)
    body = chat(client, "What's the weather like?")
    assert prompts.LOOK_UP_ASKED.strip() in fake.calls[0][0]["content"]
    assert meteo.calls == [] and not any(a.get("type") == "sources" for a in body["actions"])


def test_when_open_meteo_is_down_the_model_is_still_asked_to_look_it_up(client, monkeypatch):
    OpenMeteo(monkeypatch, fail=True)
    client.put("/api/profile", json={"preferred_name": "Rose", "city": "Portland, Oregon"})
    fake = FakeAI(reply("I couldn't get the weather just now, Rose."))
    monkeypatch.setattr(meta_client, "chat", fake)
    chat(client, "Is it going to rain today?")
    assert prompts.LOOK_UP_ASKED.strip() in fake.calls[0][0]["content"]


@pytest.mark.parametrize("words, asks", [
    ("What's the weather like?", True), ("Is it going to rain today", True), ("how cold is it out", True),
    ("what's the forecast for tomorrow", True),
    ("anything happening in town this week", False), ("did the Blazers win last night", False),
    ("It rained all day yesterday", False), ("The tulips came up this morning", False),
])
def test_which_words_ask_about_the_weather(words, asks):
    assert briefing.asks_about_weather(words) is asks


# ---------- Where Meta's API is (a setting, so a check can point at a dead address) ----------

def test_metas_address_is_a_setting_with_the_real_one_as_default(monkeypatch):
    assert meta_client.base_url() == "https://api.meta.ai/v1"
    assert meta_client.realtime_url() == "wss://api.meta.ai/v1/asr/realtime"
    monkeypatch.setenv("META_API_URL", "http://127.0.0.1:9/v1")
    assert meta_client.base_url() == "http://127.0.0.1:9/v1"
    assert meta_client.realtime_url() == "ws://127.0.0.1:9/v1/asr/realtime"
    made = []

    class FakeOpenAI:
        def __init__(self, **options):
            made.append(options)

    monkeypatch.setattr(meta_client, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(meta_client, "_clients", {})
    monkeypatch.setattr(meta_client, "_client", original_client)
    meta_client._client()
    assert made[0]["base_url"] == "http://127.0.0.1:9/v1"
    sent = []

    def fake_post(url, **kwargs):
        sent.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {"transcript": "hi"})

    monkeypatch.setattr(meta_client._http, "post", fake_post)
    meta_client.transcribe(b"RIFF", [])
    assert sent == ["http://127.0.0.1:9/v1/asr/transcribe"]


def test_a_talk_call_gives_up_after_twenty_seconds(monkeypatch):
    """One real call took 29 s on Meta's side (Nov 1). Talk waits 20 s at
    most, then Buddy says it is having trouble; a scam check or doctor notes
    can take the usual minute."""
    sent = []

    def fake_create(request):
        sent.append(request)
        message = SimpleNamespace(content='{"verdict": "looks_safe", "red_flags": [], "explanation": "Fine."}',
                                  tool_calls=None, model_dump=lambda **kw: {"role": "assistant", "content": "Fine."})
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])

    monkeypatch.setattr(meta_client, "_create", fake_create)
    meta_client.chat([{"role": "user", "content": "hi"}])
    assert sent[0]["timeout"] == meta_client.TALK_TIMEOUT_SECONDS == 20
    meta_client.structured([{"role": "user", "content": "hi"}], "scam_result", {"type": "object"})
    assert "timeout" not in sent[1]  # the connection's usual 60 seconds


# ---------- When she tells a scam story ----------

def test_buddy_is_told_to_warn_her_about_a_scam_story(client, monkeypatch):
    fake = FakeAI(reply("That sounds like a scam, Rose. Please don't send anything. Shall we call Maria?"),
                  reply("Lovely."))
    monkeypatch.setattr(meta_client, "chat", fake)
    client.put("/api/profile", json={"preferred_name": "Rose", "family_name": "Maria", "family_phone": "555-0100"})
    chat(client, "A man rang saying my grandson is in jail and needs money for bail.")
    prompt = fake.calls[0][0]["content"]
    assert prompts.SCAM_STORY_TOLD.split("{")[0].strip() in prompt
    assert "or to call Maria" in prompt
    chat(client, "The tulips came up this morning")
    assert prompts.SCAM_STORY_TOLD.split("{")[0].strip() not in fake.calls[1][0]["content"]
