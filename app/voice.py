# app/voice.py
# Buddy's natural voice. Meta has no text-to-speech model, and browsers'
# own voices sound robotic on many computers, so Buddy speaks with Kokoro:
# an open voice model (Apache-2.0, by hexgrad) that runs right here on this
# computer through the kokoro-onnx package. It sounds the same in every
# browser, costs nothing, and nothing Buddy says leaves the computer.
#
# The model files come from scripts/get_voice.py (models/, git-ignored; on
# the public demo's host they are baked into the Docker image). Without
# them, or without the package, /api/voice says so and the page uses the
# browser's own voice instead, so Buddy always talks.
#
# Fast first words, on a small host too:
# - The model loads in the background when the app starts (warm_up), so
#   health checks never wait: /api/voice says "loading" until it is ready
#   and the page uses the browser's voice meanwhile.
# - The fixed safety lines and Buddy's stock lines are made at warm-up.
# - Every sentence made is kept (CACHE_SIZE), the same sentence asked twice
#   at once is made once, and the first sentence of each reply is made the
#   moment the reply exists (say_ahead), before the page even asks.
# - VOICE_THREADS (.env) sets ONNX Runtime's threads: 2 on a 2-CPU host, 0
#   at home (every core).

import io
import re
import secrets
import threading
import time
import wave
from collections import OrderedDict
from importlib.util import find_spec
from pathlib import Path

from app.config import get_settings

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
CACHE_SIZE = 256  # sentences kept, about 100 KB each
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")  # the page splits the same way (speech.js, sentencesOf)

PROCESS = secrets.token_hex(3)  # this server process, for /api/voice: a host should run exactly one

_engine = None
_lock = threading.Lock()  # the model says one sentence at a time (its pronunciation part isn't made for two at once)
_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
_cache_lock = threading.Lock()
_making: dict = {}  # a sentence being made right now -> an Event for anyone else asking for it
_fixed: set = set()  # the sentences made ahead at warm-up (never capped in a public demo)
_warm = False  # the model is loaded and the safety lines are made: ready to speak
_urgent = 0  # sentences being made for someone right now (the warm-up's leftovers give way to them)

# The model needs about 550 MB; a container with less (a 512 MB plan) would
# be killed loading it, so the voice stays off there (the browser's speaks).
MEMORY_NEEDED = 1_200_000_000
MEMORY_LIMIT_FILES = ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes")


def available() -> bool:
    """True if the voice files and the kokoro-onnx package are here
    (checked without loading the model)."""
    return MODEL_FILE.exists() and VOICES_FILE.exists() and find_spec("kokoro_onnx") is not None


def ready() -> bool:
    """True once the model is loaded and the fixed lines are made (warm_up
    done), so nobody queues behind the warm-up."""
    return _engine is not None and _warm


def memory_limit_bytes() -> int | None:
    """The container's memory limit, when the host sets one (Linux cgroups)."""
    for name in MEMORY_LIMIT_FILES:
        try:
            text = Path(name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text.isdigit() and int(text) < 1 << 60:  # "max" or a huge number means no limit
            return int(text)
        return None
    return None


def can_load() -> bool:
    """True unless the host's memory limit is too small for the model."""
    limit = memory_limit_bytes()
    return limit is None or limit >= MEMORY_NEEDED


def session_options():
    """ONNX Runtime's options: VOICE_THREADS threads when set, else its own choice."""
    import onnxruntime as rt  # installed with kokoro-onnx; only needed here

    options = rt.SessionOptions()
    threads = get_settings().voice_threads
    if threads > 0:
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
    return options


def load_engine():
    """Load the voice model (about 2 seconds). Tests replace this."""
    import onnxruntime as rt
    from kokoro_onnx import Kokoro

    session = rt.InferenceSession(str(MODEL_FILE), session_options(), providers=["CPUExecutionProvider"])
    return Kokoro.from_session(session, str(VOICES_FILE))


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


def sentences_of(text: str) -> list[str]:
    """The sentences of a text, as the page asks for them, one at a time."""
    return [part.strip() for part in SENTENCE_END.split(text) if part.strip()]


def first_sentence(text: str) -> str:
    parts = sentences_of(text)
    return parts[0] if parts else ""


def speech(text: str, voice: str, speed: float, background: bool = False) -> bytes:
    """Buddy saying these words, as a WAV. Kept once made; asked for twice
    at once, made once (the second ask waits for the first). `background`
    is the warm-up making lines ahead: it gives way to everyone else."""
    global _urgent
    key = (text, voice, round(speed, 2))
    with _cache_lock:
        wav = _cache.get(key)
        if wav is not None:
            _cache.move_to_end(key)
            return wav
        waiting = _making.get(key)
        maker = waiting is None
        if maker:
            waiting = _making[key] = threading.Event()
    if not maker:
        waiting.wait(timeout=60)
        with _cache_lock:
            wav = _cache.get(key)
        if wav is None:
            raise RuntimeError("the voice couldn't make these words")
        return wav
    try:
        if not background:
            with _cache_lock:
                _urgent += 1
        wav = _make(text, voice, speed)
        with _cache_lock:
            _cache[key] = wav
            while len(_cache) > CACHE_SIZE:
                _cache.popitem(last=False)
        return wav
    finally:
        with _cache_lock:
            if not background:
                _urgent -= 1
            _making.pop(key, None)
        waiting.set()


def _when_nobody_waits() -> None:
    """The warm-up pauses while a sentence is being made for someone."""
    while True:
        with _cache_lock:
            busy = _urgent > 0
        if not busy:
            return
        time.sleep(0.02)


def _forget() -> None:
    with _cache_lock:
        _cache.clear()
        _making.clear()


speech.cache_clear = _forget  # as the old lru_cache offered (tests use it)


def _make(text: str, voice: str, speed: float) -> bytes:
    global _engine
    with _lock:
        if _engine is None:
            _engine = load_engine()
        language = "en-gb" if voice.startswith("b") else "en-us"
        samples, rate = _engine.create(text, voice=voice, speed=speed, lang=language)
    return wav_bytes(samples, rate)


def fixed_lines(family_name: str = "") -> list[str]:
    """The lines that never change and must never wait: the safety screens'
    words, Buddy's trouble and no-advice lines, the bridge lines."""
    from app import companion, guard, safety  # here, not at the top: companion imports a lot

    lines = [safety.fixed_message(kind, family_name) for kind in safety.PRIORITY]  # the essentials, first
    lines += [companion.TROUBLE_REPLY, guard.NO_ADVICE_REPLY]
    lines += list(companion.BRIDGES.values())
    kept: list[str] = []
    for line in lines:
        if line and line not in kept:
            kept.append(line)
    return kept


def is_fixed(text: str) -> bool:
    """True for a sentence made ahead at warm-up (a safety line, say)."""
    return text in _fixed


def coming() -> bool:
    """True while the voice is on its way: the files are here, the host can
    hold the model, and the warm-up hasn't finished yet."""
    return available() and can_load() and not ready()


def say_ahead(text: str, voice: str = DEFAULT_VOICE, speed: float = 0.9):
    """Start making a reply's first sentence now, in the background, so the
    page's request for it finds it ready or on its way. Returns the thread,
    or None when the voice isn't loaded (the page then uses the browser's)."""
    first = first_sentence(text)
    if not first or not ready():
        return None
    thread = threading.Thread(target=_quietly, args=(first, voice, speed), daemon=True)
    thread.start()
    return thread


def _quietly(text: str, voice: str, speed: float) -> None:
    try:
        speech(text, voice, speed)
    except Exception as problem:  # the page falls back to the browser voice
        print(f"The natural voice couldn't make a line ahead: {type(problem).__name__}")  # never her words


def warm_up() -> None:
    """Load the model when the app starts (in the background, see
    app/main.py) and make the fixed lines ahead, so a safety message or her
    first reply never waits for loading."""
    global _engine, _warm
    from app import safety

    if not can_load():
        print("The natural voice needs about 1.2 GB of memory; this host has less, so the browser's voice speaks.")
        return
    try:
        with _lock:
            if _engine is None:
                _engine = load_engine()
        family = ""
        try:
            from app import db

            connection = db.get_connection()
            try:
                family = (db.get_profile(connection)["family_name"] or "").strip()
            finally:
                connection.close()
        except Exception:
            pass  # no database yet: the lines without a name are still made
        lines = ["Hello."] + fixed_lines(family)  # the lines as she would hear them, with her family's name
        essential = 1 + len(safety.PRIORITY)  # "Hello." and the three safety screens' words
        for number, line in enumerate(lines):
            for sentence in sentences_of(line):
                _fixed.add(sentence)
                if number >= essential:
                    _when_nobody_waits()  # the stock lines give way to a real ask
                speech(sentence, DEFAULT_VOICE, 0.9, background=True)
            if number == essential - 1:
                _warm = True  # ready: a safety message never waits, the rest keeps being made
    except Exception as problem:  # the page falls back to the browser voice
        print(f"The natural voice couldn't start: {type(problem).__name__}")
        _warm = _engine is not None  # loaded but a line failed: still usable
