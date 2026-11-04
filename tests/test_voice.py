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
    monkeypatch.setattr(voice, "_warm", True)
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
    monkeypatch.setattr(voice, "_warm", True)
    assert speak(client).status_code == 503


def test_the_voices_on_offer_are_listed_with_the_default_first(client, kokoro):
    status = client.get("/api/voice").json()
    assert status["available"] is True and status["default"] == "af_heart"
    assert status["voices"][0] == {"id": "af_heart", "name": "Heart"}
    assert {one["id"] for one in status["voices"]} == set(voice.VOICES)


# ---------- On a host: loading in the background, the cache, made ahead ----------

class SlowKokoro(FakeKokoro):
    """A beep that takes a moment, so two asks can overlap."""

    def create(self, text, voice, speed, lang):
        import time

        time.sleep(0.15)
        return super().create(text, voice, speed, lang)


def test_while_the_model_loads_the_page_is_told_and_uses_the_browser_voice(client, monkeypatch):
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_engine", None)
    status = client.get("/api/voice").json()
    assert status["available"] is False and status["loading"] is True
    assert speak(client).status_code == 503  # not ready yet: the browser's voice speaks meanwhile
    assert client.get("/api/ping").status_code == 200  # the health check never waits for the model


def test_warm_up_loads_the_model_and_makes_the_fixed_lines_ahead(monkeypatch, safe_test_setup):
    from app import companion, guard, safety

    fake = FakeKokoro()
    monkeypatch.setattr(voice, "load_engine", lambda: fake)
    monkeypatch.setattr(voice, "_engine", None)
    voice.speech.cache_clear()
    assert voice.ready() is False
    voice.warm_up()
    assert voice.ready() is True
    made = {call["text"] for call in fake.calls}
    for line in voice.fixed_lines(""):
        for sentence in voice.sentences_of(line):
            assert sentence in made, sentence
    assert safety.EMERGENCY_MESSAGE.split(". ")[0] + "." in made
    assert companion.TROUBLE_REPLY.split(". ")[0] + "." in made
    assert guard.NO_ADVICE_REPLY.split(". ")[0] + "." in made
    assert voice.is_fixed(safety.EMERGENCY_MESSAGE.split(". ")[0] + ".")
    assert not voice.is_fixed("Did Tom come by on Sunday?")
    before = len(fake.calls)
    voice.speech(safety.EMERGENCY_MESSAGE.split(". ")[0] + ".", voice.DEFAULT_VOICE, 0.9)
    assert len(fake.calls) == before  # already made: no work when she needs it


def test_the_fixed_lines_include_her_family_name_when_there_is_one():
    from app import safety

    lines = voice.fixed_lines("Maria")
    assert safety.fixed_message("crisis", "Maria") in lines
    assert safety.fixed_message("emergency", "Maria") in lines
    assert safety.fixed_message("poison_control", "Maria") in lines
    assert all(line.strip() for line in lines) and len(lines) == len(set(lines))


def test_the_same_new_sentence_asked_three_times_at_once_is_made_once(monkeypatch):
    import threading

    fake = SlowKokoro()
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_engine", fake)
    voice.speech.cache_clear()
    results = []
    threads = [threading.Thread(target=lambda: results.append(voice.speech("Did Tom come by?", "af_heart", 0.9)))
               for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert len(results) == 3 and results[0] == results[1] == results[2]
    assert len(fake.calls) == 1
    voice.speech.cache_clear()


def test_the_first_sentence_of_a_reply_is_made_ahead_in_the_background(kokoro):
    assert voice.first_sentence("Lovely to hear, Rose. Did Tom come by?") == "Lovely to hear, Rose."
    assert voice.first_sentence("   ") == ""
    thread = voice.say_ahead("Lovely to hear, Rose. Did Tom come by?")
    assert thread is not None
    thread.join(5)
    assert [call["text"] for call in kokoro.calls] == ["Lovely to hear, Rose."]
    voice.speech("Lovely to hear, Rose.", voice.DEFAULT_VOICE, 0.9)
    assert len(kokoro.calls) == 1  # found ready


def test_nothing_is_made_ahead_before_the_model_is_loaded(monkeypatch):
    monkeypatch.setattr(voice, "_engine", None)
    assert voice.say_ahead("Lovely to hear, Rose.") is None


def test_onnx_threads_follow_the_setting(monkeypatch):
    monkeypatch.setenv("VOICE_THREADS", "2")
    assert voice.session_options().intra_op_num_threads == 2
    monkeypatch.delenv("VOICE_THREADS")
    assert voice.session_options().intra_op_num_threads == 0  # ONNX Runtime's own choice: every core


def test_ready_means_the_warm_up_is_done_so_nobody_queues_behind_it(monkeypatch):
    """Loaded but still making the fixed lines: the page keeps the browser
    voice (503) instead of waiting behind the warm-up."""
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_engine", FakeKokoro())
    monkeypatch.setattr(voice, "_warm", False)
    assert voice.ready() is False
    client = TestClient(app)
    assert client.get("/api/voice").json() | {"x": 0} == client.get("/api/voice").json() | {"x": 0}
    assert client.get("/api/voice").json()["loading"] is True
    assert speak(client).status_code == 503
    monkeypatch.setattr(voice, "_warm", True)
    assert voice.ready() is True and speak(client).status_code == 200


def test_a_small_host_keeps_the_browser_voice(monkeypatch, tmp_path):
    """On a 512 MB plan the model can't load (it needs about 550 MB): the
    voice stays off instead of crashing the server, and the page is told."""
    limit = tmp_path / "memory.max"
    monkeypatch.setattr(voice, "MEMORY_LIMIT_FILES", (str(limit),))
    assert voice.memory_limit_bytes() is None and voice.can_load() is True  # no limit known
    limit.write_text("536870912\n", encoding="utf-8")  # 512 MB
    assert voice.memory_limit_bytes() == 536870912 and voice.can_load() is False
    limit.write_text("max\n", encoding="utf-8")  # no limit (cgroup v2)
    assert voice.memory_limit_bytes() is None and voice.can_load() is True
    limit.write_text("4294967296\n", encoding="utf-8")  # 4 GB
    assert voice.can_load() is True
    limit.write_text("536870912\n", encoding="utf-8")
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_engine", None)
    client = TestClient(app)
    status = client.get("/api/voice").json()
    assert status["available"] is False and status["loading"] is False  # not coming: the browser's voice it is


def test_a_real_ask_goes_before_the_rest_of_the_warm_up(monkeypatch, safe_test_setup):
    """Ready once the safety lines are made; the stock lines still being made
    in the background give way to a real ask, so she never waits long."""
    import threading
    import time

    fake = SlowKokoro()  # 0.15 s a sentence; the warm-up has a dozen
    monkeypatch.setattr(voice, "load_engine", lambda: fake)
    monkeypatch.setattr(voice, "_engine", None)
    monkeypatch.setattr(voice, "_warm", False)
    voice.speech.cache_clear()
    warming = threading.Thread(target=voice.warm_up, daemon=True)
    warming.start()
    for _ in range(100):  # until the safety lines are made
        if voice.ready():
            break
        time.sleep(0.05)
    assert voice.ready() and not warming.is_alive() is False  # ready while the rest is still being made
    started = time.time()
    voice.speech("Did Tom come by on Sunday?", "af_heart", 0.9)
    assert time.time() - started < 1.0  # one sentence at most to wait for, not the whole warm-up
    warming.join(10)
    assert voice.is_fixed("Let me look that up.")  # the rest was still made afterwards


def test_the_voice_status_names_its_process_so_a_host_can_be_checked(client, kokoro):
    """One server process is what the cache and the head start need; the
    marker lets a live site be checked: the same value on every request."""
    first = client.get("/api/voice").json()["process"]
    assert isinstance(first, str) and len(first) == 6
    assert client.get("/api/voice").json()["process"] == first == voice.PROCESS
