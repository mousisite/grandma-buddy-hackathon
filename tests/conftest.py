# Shared test setup, used by every test automatically.
#
# Each test gets:
# - its own empty database in a temporary folder (never the real one),
# - a fake API key, and
# - real internet calls blocked, so no test can ever reach Meta's API
#   or spend money. Tests that need Meta replace it with a fake.

import pytest
import requests

from app import db, meta_client, voice


@pytest.fixture(autouse=True)
def safe_test_setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    # The test client calls itself "testserver" (app/security.py checks names).
    monkeypatch.setenv("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1,::1")

    def no_real_calls(*args, **kwargs):
        raise AssertionError("A test tried to reach the internet (Meta, Stripe, or another site).")

    # Speech-to-text uses requests.post; chat uses the openai package, which
    # gets its connection from meta_client._client(). Both are blocked, and
    # so is every other way out through requests (gets, sessions).
    monkeypatch.setattr(requests, "post", no_real_calls)
    monkeypatch.setattr(requests, "get", no_real_calls)
    monkeypatch.setattr(requests.Session, "request", no_real_calls)
    monkeypatch.setattr(meta_client, "_client", no_real_calls)
    monkeypatch.setattr(meta_client, "ws_connect", no_real_calls)  # live speech-to-text

    # The real voice model is big and slow to load: tests use a fake one.
    def no_real_voice_model():
        raise AssertionError("A test tried to load the real voice model.")

    monkeypatch.setattr(voice, "load_engine", no_real_voice_model)
    monkeypatch.setattr(voice, "_engine", None)
    db.init_db(db_path)
    return db_path
