# Tests for hands-free talking: the relay at /api/listen between her page
# and Meta's realtime speech-to-text (Muse Voice Transcribe, ENDPOINTING
# mode). The key stays on our server, so the page talks to the relay, and
# the relay talks to Meta. Meta's side is always FAKE here.

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import meta_client
from app.main import app

OWN = {"origin": "http://testserver"}  # Buddy's own page


# ---------- Opening Meta's realtime speech-to-text ----------

def test_listening_starts_with_metas_handshake(monkeypatch):
    sent = []

    class Socket:
        async def send(self, message):
            sent.append(message)

        async def recv(self):
            return json.dumps({"sessionId": "test-session"})

        async def close(self):
            pass

    async def connect(url, **options):
        Socket.url = url
        return Socket()

    monkeypatch.setattr(meta_client, "ws_connect", connect)
    asyncio.run(meta_client.open_listening(["Maria", "Metformin"]))
    assert Socket.url == "wss://api.meta.ai/v1/asr/realtime"
    # The key travels in the first message, never to the browser.
    assert json.loads(sent[0]) == {
        "authorization": {"accessToken": "Bearer test-key"},
        "audioEncoding": "PCM_16KHZ",
        "model": "muse-voice-transcribe-1.0",
        "mode": "ENDPOINTING",
        "partialMode": "CUMULATIVE",
        "emitAudioProgress": False,
        "languageBias": ["English"],
        "keywords": ["Maria", "Metformin"],
    }


def test_a_refused_handshake_is_a_meta_error(monkeypatch):
    class Socket:
        async def send(self, message):
            pass

        async def recv(self):
            return json.dumps({"type": "error", "message": "Invalid request", "sessionId": ""})

        async def close(self):
            pass

    async def connect(url, **options):
        return Socket()

    monkeypatch.setattr(meta_client, "ws_connect", connect)
    with pytest.raises(meta_client.MetaError):
        asyncio.run(meta_client.open_listening([]))


# ---------- The relay ----------

class FakeMeta:
    """Meta's realtime socket, faked: it keeps what it is sent and, once her
    first sound arrives, plays its events, then stays open until closed."""

    def __init__(self, *events):
        self.events = [json.dumps(event) for event in events]
        self.received = []
        self.closed = False

    async def send(self, message):
        self.received.append(message)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self.play()

    async def play(self):
        while not any(isinstance(message, bytes) for message in self.received):
            await asyncio.sleep(0.01)
        for event in self.events:
            yield event
        while not self.closed:
            await asyncio.sleep(0.01)


def use_fake(monkeypatch, fake):
    async def opened(keywords):
        fake.keywords = keywords
        return fake

    monkeypatch.setattr(meta_client, "open_listening", opened)
    return fake


def test_her_words_come_back_live_then_as_a_finished_turn(monkeypatch):
    fake = use_fake(monkeypatch, FakeMeta(
        {"type": "speechStart", "turnId": 0, "audioProcessedMs": 0},
        {"type": "transcript", "transcript": "Hi buddy", "final": False, "audioProcessedMs": 800},
        {"type": "audioProgress", "audioProcessedMs": 900},
        {"type": "speechEnd", "turnId": 0, "audioProcessedMs": 1500},
        {"type": "speechComplete", "turnId": 0, "transcript": "Hi Buddy, what's the weather?", "audioProcessedMs": 1500},
    ))
    sound = b"\x01\x00" * 1280  # 80 ms of 16 kHz audio
    with TestClient(app).websocket_connect("/api/listen", headers=OWN) as socket:
        assert socket.receive_json() == {"type": "ready"}
        socket.send_bytes(sound)
        # Only what the page needs, nothing else Meta sends.
        # The turn's number comes too: the page ends a turn itself after a
        # quiet moment, and must know which of Meta's turns to drop later.
        assert socket.receive_json() == {"type": "hearing", "turn": 0}
        assert socket.receive_json() == {"type": "live", "text": "Hi buddy"}
        assert socket.receive_json() == {"type": "turn", "text": "Hi Buddy, what's the weather?", "turn": 0}
    assert fake.received[0] == sound  # her sound went to Meta as it was
    assert fake.received[-1] == json.dumps({"type": "endStream"})  # leaving ends Meta's stream cleanly
    assert fake.closed


def test_another_website_cant_listen(monkeypatch):
    use_fake(monkeypatch, FakeMeta())
    with pytest.raises(WebSocketDisconnect) as refused:
        with TestClient(app).websocket_connect("/api/listen", headers={"origin": "https://example.com"}) as socket:
            socket.receive_json()
    assert refused.value.code == 1008


def test_without_meta_the_page_is_told_to_use_tap_to_talk(monkeypatch):
    async def no_key(keywords):
        raise meta_client.MetaError("no API key is set up in .env")

    monkeypatch.setattr(meta_client, "open_listening", no_key)
    with TestClient(app).websocket_connect("/api/listen", headers=OWN) as socket:
        assert socket.receive_json() == {"type": "unavailable"}


def test_only_one_listening_at_a_time(monkeypatch):
    use_fake(monkeypatch, FakeMeta())
    client = TestClient(app)
    with client.websocket_connect("/api/listen", headers=OWN) as first:
        assert first.receive_json() == {"type": "ready"}
        with pytest.raises(WebSocketDisconnect) as second_refused:
            with client.websocket_connect("/api/listen", headers=OWN) as second:
                second.receive_json()
        assert second_refused.value.code == 1013
    # Once the first has ended, she can listen again.
    use_fake(monkeypatch, FakeMeta())
    with client.websocket_connect("/api/listen", headers=OWN) as again:
        assert again.receive_json() == {"type": "ready"}


# ---------- "Talk without tapping" (Settings) ----------

def test_talking_without_tapping_starts_on_and_can_be_turned_off():
    client = TestClient(app)
    assert client.get("/api/profile").json()["hands_free"] is True
    assert client.put("/api/profile", json={"hands_free": False}).json()["hands_free"] is False
    assert client.put("/api/profile", json={"hands_free": "yes"}).status_code == 400
