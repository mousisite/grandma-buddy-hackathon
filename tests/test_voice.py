# Tests for Buddy's natural voice (app/voice.py, /api/voice, /api/speak).
# The voice model is FAKE here: a test never loads the real one (it is big
# and slow); tests/conftest.py makes sure of that.

import io
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import voice
from app.main import app


class FakeKokoro:
    """Stands in for kokoro_onnx.Kokoro: a short beep for any words."""

    def __init__(self, fails=False):
        self.calls = []
        self.fails = fails

    def create(self, text, voice, speed, lang):
        self.calls.append({"text": text, "voice": voice, "speed": speed, "lang": lang})
        if self.fails:
            raise RuntimeError("the voice model broke")
        return np.full(2400, 0.25, dtype=np.float32), 24000  # 0.1 second


@pytest.fixture
def kokoro(monkeypatch):
    fake = FakeKokoro()
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_engine", fake)
    voice.speech.cache_clear()
    yield fake
    voice.speech.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


def speak(client, text="Good afternoon, Rose.", voice_id="af_heart", speed=0.9):
    return client.post("/api/speak", json={"text": text, "voice": voice_id, "speed": speed})


def test_a_wav_is_16_bit_mono_and_loud_sounds_are_kept_in_range():
    data = voice.wav_bytes(np.array([0.0, 0.5, -1.0, 1.7], dtype=np.float32), 24000)
    with wave.open(io.BytesIO(data)) as sound:
        assert (sound.getnchannels(), sound.getsampwidth(), sound.getframerate(), sound.getnframes()) == (1, 2, 24000, 4)
        values = np.frombuffer(sound.readframes(4), dtype="<i2").tolist()
    assert values == [0, 16383, -32767, 32767]


def test_buddy_speaks_her_words_as_a_wav_in_the_chosen_voice_and_speed(client, kokoro):
    reply = speak(client, voice_id="af_bella", speed=0.75)
    assert reply.status_code == 200 and reply.headers["content-type"] == "audio/wav"
    assert reply.content[:4] == b"RIFF" and reply.content[8:12] == b"WAVE"
    assert kokoro.calls == [{"text": "Good afternoon, Rose.", "voice": "af_bella", "speed": 0.75, "lang": "en-us"}]


def test_a_british_voice_speaks_british_english(client, kokoro):
    speak(client, voice_id="bf_emma")
    assert kokoro.calls[-1]["lang"] == "en-gb"


def test_the_same_words_are_made_only_once(client, kokoro):
    speak(client)
    speak(client)
    assert len(kokoro.calls) == 1


@pytest.mark.parametrize("text, voice_id, speed", [
    ("", "af_heart", 0.9),             # nothing to say
    ("word " * 200, "af_heart", 0.9),  # far longer than a sentence
    ("Hello.", "somebody", 0.9),       # not one of Buddy's voices
    ("Hello.", "af_heart", 3),         # far too fast
])
def test_odd_requests_are_refused(client, kokoro, text, voice_id, speed):
    assert speak(client, text, voice_id, speed).status_code == 400
    assert kokoro.calls == []


def test_without_the_voice_files_the_page_is_told_to_use_the_browser_voice(client, monkeypatch):
    monkeypatch.setattr(voice, "available", lambda: False)
    assert speak(client).status_code == 503
    assert client.get("/api/voice").json()["available"] is False


def test_a_broken_voice_model_answers_503_so_the_page_uses_the_browser_voice(client, monkeypatch, kokoro):
    monkeypatch.setattr(voice, "_engine", FakeKokoro(fails=True))
    assert speak(client).status_code == 503


def test_the_voices_on_offer_are_listed_with_the_default_first(client, kokoro):
    status = client.get("/api/voice").json()
    assert status["available"] is True and status["default"] == "af_heart"
    assert status["voices"][0] == {"id": "af_heart", "name": "Heart"}
    assert {one["id"] for one in status["voices"]} == set(voice.VOICES)
