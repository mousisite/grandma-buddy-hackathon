# scripts/check_realtime.py
# Hand-run trial of Meta's realtime speech-to-text (Muse Voice Transcribe,
# wss://api.meta.ai/v1/asr/realtime, ENDPOINTING mode), before hands-free
# talking is built on it. It makes a short spoken clip with Buddy's own
# voice on this computer (Kokoro), two sentences with a pause between them,
# streams it at real-time speed like a microphone would, and prints every
# event: the live words (partials), each turn's start and end, and the final
# words of each turn, with how long Meta took after she stopped talking.
#
# Costs about $0.0005 (15 seconds of audio at $0.18 an hour).
#   .venv\Scripts\python scripts\check_realtime.py
#   .venv\Scripts\python scripts\check_realtime.py --relay
# --relay goes through our own /api/listen (app/routes/listen.py) on a test
# server with a throwaway database, the way the page does: 16 kHz sound in,
# live words and finished turns out.

import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from websockets.asyncio.client import connect  # noqa: E402

from app import voice  # noqa: E402
from app.config import get_settings  # noqa: E402

URL = "wss://api.meta.ai/v1/asr/realtime"
FRAME_MS = 80
SAID = ["Hi Buddy. What's the weather like today?", "And how did the Blazers do last night?"]


def spoken_clip() -> tuple[bytes, int]:
    """Two sentences in Buddy's voice with 2 seconds of quiet between them and
    after them: raw 16-bit mono PCM and its rate (Kokoro speaks at 24 kHz)."""
    pcm, rate = b"", 24000
    for sentence in SAID:
        with wave.open(io.BytesIO(voice.speech(sentence, voice.DEFAULT_VOICE, 0.9))) as clip:
            rate = clip.getframerate()
            pcm += clip.readframes(clip.getnframes())
        pcm += b"\x00\x00" * rate * 2  # 2 seconds of quiet
    return pcm, rate


async def trial() -> int:
    settings = get_settings()
    if not settings.model_api_key:
        print("No API key in .env.")
        return 1
    pcm, rate = spoken_clip()
    frame = rate * 2 * FRAME_MS // 1000
    print(f"Clip: {len(pcm) / rate / 2:.1f} seconds at {rate} Hz.")
    started = time.monotonic()
    said_end = {}  # turn: when its words ended in the clip (seconds), to measure Meta's wait

    def at() -> str:
        return f"{time.monotonic() - started:5.2f}s"

    async with connect(URL, open_timeout=10, max_size=2**20) as socket:
        await socket.send(json.dumps({
            "authorization": {"accessToken": f"Bearer {settings.model_api_key}"},
            "audioEncoding": "PCM_24KHZ" if rate == 24000 else "PCM_16KHZ",
            "model": settings.transcribe_model,
            "mode": "ENDPOINTING",
            "partialMode": "CUMULATIVE",
            "emitAudioProgress": False,
            "languageBias": [settings.language],
            "keywords": ["Buddy", "Blazers"],
        }))
        ack = json.loads(await socket.recv())
        print(f"{at()} handshake answer: {ack}")
        if "sessionId" not in ack:
            return 1

        async def send_audio():
            for start in range(0, len(pcm), frame):
                await socket.send(pcm[start:start + frame])
                await asyncio.sleep(FRAME_MS / 1000)
            await socket.send(json.dumps({"type": "endStream"}))
            print(f"{at()} sent endStream")

        async def read_events():
            async for message in socket:
                if isinstance(message, bytes):
                    continue
                event = json.loads(message)
                kind = event.get("type")
                if kind == "transcript":
                    print(f"{at()}   live: {event['transcript']!r}")
                elif kind == "speechStart":
                    print(f"{at()} speechStart turn {event['turnId']} (audio {event['audioProcessedMs']} ms)")
                elif kind == "speechEnd":
                    said_end[event["turnId"]] = time.monotonic()
                    print(f"{at()} speechEnd turn {event['turnId']} (audio {event['audioProcessedMs']} ms)")
                elif kind == "speechComplete":
                    waited = time.monotonic() - said_end.get(event["turnId"], time.monotonic())
                    print(f"{at()} speechComplete turn {event['turnId']}: {event['transcript']!r} "
                          f"({waited:.2f}s after speechEnd)")
                else:
                    print(f"{at()} {kind}: {event}")

        await asyncio.gather(send_audio(), read_events())
        print(f"{at()} closed: {socket.close_code} {socket.close_reason!r}")
    return 0


def to_16k(pcm: bytes, rate: int) -> bytes:
    """The clip at 16 kHz, the rate the page sends."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    places = np.linspace(0, len(samples) - 1, int(len(samples) * 16000 / rate))
    return np.interp(places, np.arange(len(samples)), samples).astype(np.int16).tobytes()


async def relay_trial(port: int = 8012) -> int:
    """The same clip through our own relay, like the page."""
    pcm, rate = spoken_clip()
    pcm = to_16k(pcm, rate)
    frame = 16000 * 2 * FRAME_MS // 1000
    env = dict(os.environ, DATABASE_PATH=str(Path(tempfile.mkdtemp(prefix="buddy-relay-")) / "check.db"))
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=ROOT,
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://localhost:{port}/api/ping", timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        started = time.monotonic()
        turns = []
        async with connect(f"ws://localhost:{port}/api/listen",
                           additional_headers={"Origin": f"http://localhost:{port}"}) as socket:
            first = json.loads(await socket.recv())
            print(f"{time.monotonic() - started:5.2f}s relay: {first}")
            if first.get("type") != "ready":
                return 1

            async def send_sound():
                for start in range(0, len(pcm), frame):
                    await socket.send(pcm[start:start + frame])
                    await asyncio.sleep(FRAME_MS / 1000)

            async def read_words():
                async for message in socket:
                    event = json.loads(message)
                    print(f"{time.monotonic() - started:5.2f}s relay: {event}")
                    if event.get("type") == "turn":
                        turns.append(event["text"])
                        if len(turns) == len(SAID):
                            return

            await asyncio.wait_for(asyncio.gather(send_sound(), read_words()), timeout=60)
        print(f"Turns: {turns}")
        return 0 if len(turns) == len(SAID) else 1
    finally:
        server.terminate()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(relay_trial() if "--relay" in sys.argv else trial()))
