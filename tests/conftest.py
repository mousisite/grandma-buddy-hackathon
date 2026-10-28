# Shared test setup, used by every test automatically.
#
# Each test gets:
# - its own empty database in a temporary folder (never the real one),
# - a fake API key, and
# - real internet calls blocked, so no test can ever reach Meta's API
#   or spend money. Tests that need Meta replace it with a fake.

import pytest
import requests

from app import db, meta_client


@pytest.fixture(autouse=True)
def safe_test_setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setenv("MODEL_API_KEY", "test-key")

    def no_real_calls(*args, **kwargs):
        raise AssertionError("A test tried to call the real Meta API.")

    # Speech-to-text uses requests.post; chat uses the openai package, which
    # gets its connection from meta_client._client(). Both are blocked.
    monkeypatch.setattr(requests, "post", no_real_calls)
    monkeypatch.setattr(meta_client, "_client", no_real_calls)
    db.init_db(db_path)
    return db_path
