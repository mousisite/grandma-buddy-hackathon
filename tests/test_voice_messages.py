# Tests for a voice message from the family (docs/SPEC.md feature 22): a
# family member records a few words on the family page; the recording is
# kept on this computer, Muse Voice Transcribe writes down what it heard
# (so the words show too), and she hears her daughter's own voice on her
# Family screen. Meta is always FAKE here. Made-up words only.

import io
import zipfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import accounts, db, meta_client, reminders, voice_messages
from app.main import app

NOW = datetime(2026, 10, 31, 16, 30)
MARIA = {"name": "Maria", "email": "maria@example.com", "password": "rose-garden-2026"}
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 24  # the start of a real WAV file


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(reminders, "current_time", lambda: NOW)
    accounts.forget_tries()
    return NOW


@pytest.fixture
def client(clock):
    return TestClient(app)


@pytest.fixture
def connection(safe_test_setup):
    opened = db.get_connection(safe_test_setup)
    db.get_profile(opened)
    opened.execute("UPDATE profile SET preferred_name = 'Rose', family_name = 'Maria', family_phone = '555-0100' WHERE id = 1")
    opened.commit()
    yield opened
    opened.close()


def maria(client):
    code = client.post("/api/family/invite").json()["code"]
    assert client.post("/api/family/account", json={"code": code, **MARIA}).status_code == 200
    return client


def heard(monkeypatch, words):
    """A fake Voice Transcribe: what it heard, or a problem."""
    calls = []

    def fake(wav_bytes, keywords):
        calls.append((wav_bytes, keywords))
        if isinstance(words, Exception):
            raise words
        return words

    monkeypatch.setattr(meta_client, "transcribe", fake)
    return calls


def send_voice(client, wav=WAV):
    return client.post("/api/family/voice", files={"audio": ("voice.wav", wav, "audio/wav")})


def test_a_voice_message_is_kept_with_what_it_said(client, connection, monkeypatch):
    calls = heard(monkeypatch, "Hi Mom, I'll bring Leo on Sunday")
    family = maria(client)
    sent = send_voice(family)
    assert sent.status_code == 200
    assert sent.json()["message"] == {"id": 1, "time": "4:30 PM", "text": "Hi Mom, I'll bring Leo on Sunday", "from": "family",
                                      "name": "Maria", "unread": True, "voice": "/api/messages/1/voice"}
    assert calls[0][0] == WAV and "Rose" in calls[0][1], "her name is a hint for the words"
    # The recording itself, kept on this computer, plays from her Family screen (and Maria's page).
    played = client.get("/api/messages/1/voice")
    assert played.status_code == 200 and played.headers["content-type"] == "audio/wav" and played.content == WAV
    assert (voice_messages.voices_dir() / "voice-1.wav").read_bytes() == WAV
    shown = client.get("/api/messages").json()
    assert shown["messages"][0]["voice"] == "/api/messages/1/voice"
    assert shown["latest_unread"] == {"name": "Maria", "text": "Hi Mom, I'll bring Leo on Sunday", "voice": "/api/messages/1/voice"}
    day = family.get("/api/family/dashboard").json()
    assert day["messages"] == [{"time": "4:30 PM", "text": "Hi Mom, I'll bring Leo on Sunday", "from": "family", "name": "Maria",
                                "voice": "/api/messages/1/voice"}]


def test_the_voice_arrives_even_when_meta_cant_write_it_down(client, connection, monkeypatch):
    heard(monkeypatch, meta_client.MetaError("transcribe failed with HTTP 503"))
    sent = send_voice(maria(client))
    assert sent.status_code == 200
    assert sent.json()["message"]["text"] == "" and sent.json()["message"]["voice"] == "/api/messages/1/voice"
    assert client.get("/api/messages/1/voice").status_code == 200


def test_a_voice_message_needs_a_signed_in_family_member_and_a_real_recording(client, connection, monkeypatch):
    calls = heard(monkeypatch, "Hello")
    assert send_voice(client).status_code == 401
    family = maria(client)
    assert send_voice(family, b"not audio at all").status_code == 400
    assert send_voice(family, b"RIFF" + b"\x00" * (voice_messages.MAX_VOICE_BYTES + 10)).status_code == 400
    assert calls == [] and not voice_messages.voices_dir().exists()
    assert client.get("/api/messages/9/voice").status_code == 404
    # Her own typed message has no voice.
    hers = client.post("/api/messages", json={"text": "Lovely"}).json()["message"]
    assert hers["voice"] == "" and client.get(f"/api/messages/{hers['id']}/voice").status_code == 404


def test_export_takes_the_voices_and_delete_wipes_them(client, connection, monkeypatch):
    heard(monkeypatch, "Hello Mom")
    send_voice(maria(client))
    names = zipfile.ZipFile(io.BytesIO(client.get("/api/data/export").content)).namelist()
    assert "voices/voice-1.wav" in names
    assert client.post("/api/data/delete", json={"confirm": "DELETE"}).status_code == 200
    assert not voice_messages.voices_dir().exists()


# ---------- Her voice travels with her message ----------

def send_hers(client, text, wav=WAV):
    return client.post("/api/messages/voice", data={"text": text}, files={"audio": ("voice.wav", wav, "audio/wav")})


def test_her_message_can_carry_her_own_voice(client, connection, monkeypatch):
    calls = heard(monkeypatch, "never used: the words come from the box she read over")
    sent = send_hers(client, "The tulips came up, come and see them Sunday")
    assert sent.status_code == 200
    message = sent.json()["message"]
    assert message == {"id": 1, "time": "4:30 PM", "text": "The tulips came up, come and see them Sunday", "from": "her",
                       "name": "", "unread": False, "voice": "/api/messages/1/voice"}
    assert calls == [], "her words were already written down by Say it; nothing goes to Meta again"
    assert client.get("/api/messages/1/voice").content == WAV
    # Maria's page: her words, and Play for her voice.
    day = maria(client).get("/api/family/dashboard").json()
    assert day["messages"] == [{"time": "4:30 PM", "text": "The tulips came up, come and see them Sunday", "from": "her",
                                "name": "", "voice": "/api/messages/1/voice"}]


def test_the_safety_net_runs_before_her_voice_is_kept(client, connection, monkeypatch):
    heard(monkeypatch, "unused")
    answer = send_hers(client, "Maria my chest feels tight today")
    assert answer.status_code == 200 and answer.json()["show"] == "emergency"
    assert client.get("/api/messages").json()["messages"] == []
    assert not voice_messages.voices_dir().exists(), "nothing is kept, not even the recording"
    assert connection.execute("SELECT COUNT(*) FROM family_messages").fetchone()[0] == 0


def test_her_voice_message_needs_words_and_a_real_recording(client, connection, monkeypatch):
    heard(monkeypatch, "unused")
    assert send_hers(client, "   ").status_code == 400
    assert send_hers(client, "Hello", b"not a recording").status_code == 400
    assert client.get("/api/messages").json()["messages"] == []
