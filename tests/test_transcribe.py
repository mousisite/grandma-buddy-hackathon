# Tests for voice in: POST /api/transcribe and meta_client.transcribe().
# The real Meta API is never called. Fakes stand in for it.
# All names here are made up.

import io
import json
import wave

import pytest
import requests
from fastapi.testclient import TestClient

from app import db, meta_client
from app.main import app


def make_wav(seconds: float = 0.1) -> bytes:
    """A short silent 16 kHz mono 16-bit WAV, like the browser sends."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buffer.getvalue()


def add_demo_names(db_path: str) -> None:
    """A made-up family member, doctor, and two pills (one no longer taken)."""
    connection = db.get_connection(db_path)
    connection.execute(
        "INSERT INTO profile (id, preferred_name, family_name, doctor_name) "
        "VALUES (1, 'Rose', 'Maria', 'Dr. Lee')"
    )
    connection.execute("INSERT INTO medications (name, active) VALUES ('Vitamin D', 1)")
    connection.execute("INSERT INTO medications (name, active) VALUES ('Old Pill', 0)")
    connection.commit()
    connection.close()


class FakeResponse:
    """Stands in for what requests.post returns."""

    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


# ---------- The /api/transcribe route ----------


def test_transcribe_returns_what_she_said(safe_test_setup, monkeypatch):
    add_demo_names(safe_test_setup)
    calls = []

    def fake_transcribe(wav_bytes, keywords):
        calls.append((wav_bytes, keywords))
        return "Maria is coming on Sunday"

    monkeypatch.setattr(meta_client, "transcribe", fake_transcribe)
    wav = make_wav()

    response = TestClient(app).post(
        "/api/transcribe", files={"audio": ("speech.wav", wav, "audio/wav")}
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "Maria is coming on Sunday"}
    # The recording reaches Meta unchanged, with names she is likely to say
    # as hints. Pills she no longer takes are left out.
    assert calls == [(wav, ["Maria", "Dr. Lee", "Vitamin D"])]


def test_transcribe_rejects_files_that_are_not_wav(monkeypatch):
    def must_not_run(wav_bytes, keywords):
        raise AssertionError("Meta should not be called for a bad file")

    monkeypatch.setattr(meta_client, "transcribe", must_not_run)

    response = TestClient(app).post(
        "/api/transcribe", files={"audio": ("speech.wav", b"not a recording", "audio/wav")}
    )

    assert response.status_code == 400


def test_transcribe_gives_a_kind_message_when_meta_fails(monkeypatch):
    def broken_transcribe(wav_bytes, keywords):
        raise meta_client.MetaError("transcribe failed with HTTP 500")

    monkeypatch.setattr(meta_client, "transcribe", broken_transcribe)

    response = TestClient(app).post(
        "/api/transcribe", files={"audio": ("speech.wav", make_wav(), "audio/wav")}
    )

    assert response.status_code == 502
    message = response.json()["detail"]
    # Plain, kind words only. Never "error", "HTTP", or numbers like 500.
    assert "try again" in message
    for scary in ("error", "HTTP", "500", "API", "server"):
        assert scary not in message


# ---------- meta_client.transcribe() ----------


def test_meta_client_sends_the_request_meta_expects(monkeypatch):
    sent = []

    def fake_post(url, **kwargs):
        sent.append((url, kwargs))
        return FakeResponse(200, {"transcript": "  Hello there.  ", "turns": []})

    monkeypatch.setattr(requests, "post", fake_post)

    transcript = meta_client.transcribe(b"RIFF-wav-bytes", ["Maria", "Vitamin D"])

    assert transcript == "Hello there."
    url, kwargs = sent[0]
    assert url == "https://api.meta.ai/v1/asr/transcribe"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["headers"]["Accept"] == "application/json"
    assert kwargs["timeout"] == 60
    # Two form parts: the settings as JSON, and the WAV file itself.
    request_part = kwargs["files"]["request"]
    assert request_part[2] == "application/json"
    settings = json.loads(request_part[1])
    assert settings["model"] == "muse-voice-transcribe-1.0"
    assert "contributor" not in settings["model"]
    assert settings["audioEncoding"] == "WAV"
    assert settings["languageBias"] == ["English"]
    assert settings["keywords"] == ["Maria", "Vitamin D"]
    assert kwargs["files"]["audio"] == ("speech.wav", b"RIFF-wav-bytes", "audio/wav")


def test_meta_client_waits_and_retries_when_meta_is_busy(monkeypatch):
    replies = [FakeResponse(429), FakeResponse(429), FakeResponse(200, {"transcript": "Hi"})]
    sent = []

    def fake_post(url, **kwargs):
        sent.append(kwargs)
        return replies.pop(0)

    waits = []
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(meta_client.time, "sleep", waits.append)

    assert meta_client.transcribe(b"RIFF", []) == "Hi"
    assert len(sent) == 3
    assert waits == [1, 2]
    # With no names to hint, no keywords are sent at all.
    assert "keywords" not in json.loads(sent[0]["files"]["request"][1])


def test_meta_client_raises_meta_error_when_meta_fails(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda url, **kwargs: FakeResponse(500))

    with pytest.raises(meta_client.MetaError):
        meta_client.transcribe(b"RIFF", [])
