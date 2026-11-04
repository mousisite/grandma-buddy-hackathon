# app/config.py
# Reads the app's settings from the .env file.
#
# This is the ONLY file that reads .env. Every other file asks this one.
# Never print the API key, write it to a log, or send it to the browser.

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# The project folder. A relative DATABASE_PATH counts from here, so the app
# and scripts/seed_demo.py use the same database whatever folder they are
# started from.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent

# Load the .env file (if it exists) into environment variables.
load_dotenv()


@dataclass
class Settings:
    """All settings for Grandma Buddy. See .env.example for what each one means."""

    model_api_key: str = ""  # Meta Model API key. Empty means "not set up yet".
    meta_api_url: str = "https://api.meta.ai/v1"  # where Meta's API is (a check can point it at a dead address)
    chat_model: str = "muse-spark-1.3"  # conversation model (standard, never -contributor)
    transcribe_model: str = "muse-voice-transcribe-1.0"  # speech-to-text model
    image_model: str = "muse-image-1.0"  # paints the Memory book pictures (standard, never -contributor)
    sam_model: str = "sam-3.1"  # finds her things in a photo ("Find my things")
    language: str = "English"  # the app's language, sent to speech-to-text as a hint
    database_path: str = "data/grandma_buddy.db"  # where the SQLite file lives
    # The names this computer may be reached by (app/security.py).
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "::1")
    # The Family plan's checkout, in Stripe's TEST mode only (sk_test_…).
    # Empty means demo mode: no real charge, no card fields.
    stripe_secret_key: str = ""
    # The public demo on a host (docs/DEPLOY.md): the made-up week, reset
    # nightly, a share of Meta's calls per visitor and per day, no sign-ups.
    public_demo: bool = False
    ai_calls_per_visitor_hour: int = 40
    ai_calls_per_day: int = 600
    voice_threads: int = 0  # ONNX Runtime threads for the natural voice: 0 lets it use every core; 2 on a 2-CPU host
    voice_sentences_per_visitor_hour: int = 300  # a public demo: each visitor's share of the natural voice
    demo_reset_hour: int = 3  # the server's clock (UTC on most hosts)


def get_settings() -> Settings:
    """Read the current settings.

    Called fresh each time (instead of once at startup) so tests
    can change settings with environment variables.
    """
    settings = Settings(
        model_api_key=os.getenv("MODEL_API_KEY", ""),
        meta_api_url=os.getenv("META_API_URL", "https://api.meta.ai/v1").strip().rstrip("/"),
        chat_model=os.getenv("CHAT_MODEL", "muse-spark-1.3"),
        transcribe_model=os.getenv("TRANSCRIBE_MODEL", "muse-voice-transcribe-1.0"),
        image_model=os.getenv("IMAGE_MODEL", "muse-image-1.0"),
        sam_model=os.getenv("SAM_MODEL", "sam-3.1"),
        language=os.getenv("LANGUAGE", "English"),
        database_path=str(PROJECT_FOLDER / os.getenv("DATABASE_PATH", "data/grandma_buddy.db")),
        allowed_hosts=tuple(
            name.strip().lower() for name in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,::1").split(",") if name.strip()
        ),
        stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", "").strip(),
        public_demo=os.getenv("PUBLIC_DEMO", "").strip().lower() in ("1", "true", "yes", "on"),
        ai_calls_per_visitor_hour=int(os.getenv("AI_CALLS_PER_VISITOR_HOUR", "40")),
        ai_calls_per_day=int(os.getenv("AI_CALLS_PER_DAY", "600")),
        voice_threads=int(os.getenv("VOICE_THREADS", "0")),
        voice_sentences_per_visitor_hour=int(os.getenv("VOICE_SENTENCES_PER_VISITOR_HOUR", "300")),
        demo_reset_hour=int(os.getenv("DEMO_RESET_HOUR", "3")),
    )
    # Payments only ever run in Stripe's test mode, so nothing is ever really
    # charged. A live key refuses to start (and is never printed).
    if settings.stripe_secret_key and not settings.stripe_secret_key.startswith("sk_test_"):
        raise ValueError("Grandma Buddy takes payments in Stripe's test mode only: STRIPE_SECRET_KEY must start with sk_test_.")
    # Standard models only. In "-contributor" mode Meta may train on what she
    # says, and this app holds her health information, so it refuses to run.
    for model in (settings.chat_model, settings.transcribe_model, settings.image_model, settings.sam_model):
        if "contributor" in model:
            raise ValueError(f"Grandma Buddy uses standard Meta models only, not {model}.")
    return settings
