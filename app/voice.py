# app/voice.py
# Buddy's natural voice. Meta has no text-to-speech model, and browsers'
# own voices sound robotic on many computers, so Buddy speaks with Kokoro:
# an open voice model (Apache-2.0, by hexgrad) that runs right here on this
# computer through the kokoro-onnx package. It sounds the same in every
# browser, costs nothing, and nothing Buddy says leaves the computer.
#
# The model files come from scripts/get_voice.py (models/, git-ignored).
# Without them, or without the package, /api/voice says so and the page
# uses the browser's own voice instead, so Buddy always talks.

import io
import threading
import wave
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "models"
MODEL_FILE = MODELS / "kokoro-v1.0.onnx"
VOICES_FILE = MODELS / "voices-v1.0.bin"

# The voices offered in Settings, best first: Kokoro's best-rated English
# voices (its VOICES.md grades). "af" is an American woman, "bf" a British
# woman, "am" an American man.
VOICES = {
    "af_heart": "Heart",
    "af_bella": "Bella",
    "af_nicole": "Nicole",
    "bf_emma": "Emma (British)",
    "am_michael": "Michael",
}
DEFAULT_VOICE = "af_heart"
MAX_TEXT = 600  # the page sends one sentence at a time

_engine = None
_lock = threading.Lock()  # one at a time: the pronunciation part isn't made for two at once


def available() -> bool:
    """True if the voice files and the kokoro-onnx package are here
    (checked without loading the model)."""
    return MODEL_FILE.exists() and VOICES_FILE.exists() and find_spec("kokoro_onnx") is not None


def load_engine():
    """Load the voice model (about 3 seconds). Tests replace this."""
    from kokoro_onnx import Kokoro

    return Kokoro(str(MODEL_FILE), str(VOICES_FILE))


def wav_bytes(samples, rate: int) -> bytes:
    """The model's sound (numbers from -1 to 1) as a 16-bit mono WAV file."""
    import numpy as np  # installed with kokoro-onnx; only needed here

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(rate)
        sound.writeframes(pcm.tobytes())
    return out.getvalue()


@lru_cache(maxsize=64)  # the same words (a greeting, a safety message) are made once
def speech(text: str, voice: str, speed: float) -> bytes:
    """Buddy saying these words, as a WAV."""
    global _engine
    with _lock:
        if _engine is None:
            _engine = load_engine()
        language = "en-gb" if voice.startswith("b") else "en-us"
        samples, rate = _engine.create(text, voice=voice, speed=speed, lang=language)
    return wav_bytes(samples, rate)


def warm_up() -> None:
    """Load the model and say one word when the app starts, so her first
    reply (or a safety message) never waits for loading."""
    try:
        speech("Hello.", DEFAULT_VOICE, 0.9)
    except Exception as problem:  # the page falls back to the browser voice
        print(f"The natural voice couldn't start: {type(problem).__name__}")
