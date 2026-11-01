# app/voice_messages.py
# A voice message from the family (docs/SPEC.md feature 22, docs/SAFETY.md
# 9c): a family member records a few words on the family page. The
# recording is kept on this computer (data/voice-messages/), Muse Voice
# Transcribe writes down what it heard so the words show too (and Buddy can
# say them), and she hears her family member's own voice on her Family
# screen. The recording is played as it is, never changed; the words are
# what Meta heard, shown as the family member's, never the AI's.

import re
from pathlib import Path

from app import db, meta_client
from app.config import get_settings

MAX_VOICE_BYTES = 5 * 1024 * 1024  # a minute or two of 16 kHz mono WAV
VOICE_NAME = re.compile(r"^voice-\d+\.wav$")  # only names made here are ever served


def voices_dir() -> Path:
    """data/voice-messages/, next to the database (git-ignored with it)."""
    return Path(get_settings().database_path).parent / "voice-messages"


def voice_path(name: str) -> Path | None:
    return voices_dir() / name if VOICE_NAME.match(name or "") else None


def is_wav(recording: bytes) -> bool:
    """A WAV file starts with "RIFF", its size, then "WAVE"."""
    return len(recording) <= MAX_VOICE_BYTES and recording[:4] == b"RIFF" and recording[8:12] == b"WAVE"


def words_of(recording: bytes, her_name: str) -> str:
    """What Muse Voice Transcribe heard, with her name and the usual names as
    hints; "" when it can't (the voice still arrives)."""
    keywords = [name for name in [her_name, *db.get_keywords()] if name]
    try:
        return meta_client.transcribe(recording, keywords).strip()
    except Exception as problem:  # Meta down, the internet down: never her family's words
        print(f"Writing down a voice message failed: {type(problem).__name__}")
        return ""


def keep(recording: bytes, message_id: int) -> str:
    """The recording, kept under the message's own name. Returns that name."""
    name = f"voice-{message_id}.wav"
    voices_dir().mkdir(parents=True, exist_ok=True)
    (voices_dir() / name).write_bytes(recording)
    return name
