# app/config.py
# Reads the app's settings from the .env file.
#
# This is the ONLY file that reads .env. Every other file asks this one.
# Never print the API key, write it to a log, or send it to the browser.

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load the .env file (if it exists) into environment variables.
load_dotenv()


@dataclass
class Settings:
    """All settings for Grandma Buddy. See .env.example for what each one means."""

    model_api_key: str = ""  # Meta Model API key. Empty means "not set up yet".
    chat_model: str = "muse-spark-1.3"  # conversation model (standard, never -contributor)
    transcribe_model: str = "muse-voice-transcribe-1.0"  # speech-to-text model
    language: str = "English"  # the app's language, sent to speech-to-text as a hint
    database_path: str = "data/grandma_buddy.db"  # where the SQLite file lives


def get_settings() -> Settings:
    """Read the current settings.

    Called fresh each time (instead of once at startup) so tests
    can change settings with environment variables.
    """
    return Settings(
        model_api_key=os.getenv("MODEL_API_KEY", ""),
        chat_model=os.getenv("CHAT_MODEL", "muse-spark-1.3"),
        transcribe_model=os.getenv("TRANSCRIBE_MODEL", "muse-voice-transcribe-1.0"),
        language=os.getenv("LANGUAGE", "English"),
        database_path=os.getenv("DATABASE_PATH", "data/grandma_buddy.db"),
    )
