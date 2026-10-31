# Tests for a Memory book page from an old photo (docs/SPEC.md feature 20):
# she picks a photo, SAM 3.1 checks for people, Muse Spark describes the
# scene and asks one question (never who anyone is), she tells the story,
# and the page is painted in the book's style, or, when people are in the
# photo, her own photo is the picture (kept on this computer only). Every
# Meta call is FAKE here. Made-up photos: a few bytes, never a real picture.

import base64
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import db, family, memories, meta_client, prompts, tools
from app.main import app
from tests.test_memories import GOOD_PAGE, WEBP, FakePainter, FakeWriter

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 24  # a JPEG file's first bytes, then filler
PHOTO = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
A_PERSON = "<|box;x1=120;y1=40;x2=300;y2=420;w=600;h=450;c=0.93|>"
DESCRIPTION = {"scene": "A green lake with a small blue rowboat, and a wooden dock in summer light.",
               "question": "What do you remember about that day at the lake?"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def connection(safe_test_setup):
    opened = db.get_connection(safe_test_setup)
    db.get_profile(opened)
    opened.execute("UPDATE profile SET preferred_name = 'Rose', family_name = 'Maria' WHERE id = 1")
    opened.commit()
    yield opened
    opened.close()


def fake_sam(monkeypatch, answer):
    calls = []

    def fake(image, phrase):
        calls.append({"image": image, "phrase": phrase})
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(meta_client, "segment", fake)
    return calls


def start_from_photo(client, monkeypatch, sam=A_PERSON, description=DESCRIPTION, page=GOOD_PAGE):
    """A photo is sent; Spark describes it, then (later) writes the page."""
    fake_sam(monkeypatch, sam)
    writer, painter = FakeWriter(description, page), FakePainter(WEBP)
    monkeypatch.setattr(meta_client, "structured", writer)
    monkeypatch.setattr(meta_client, "paint", painter)
    answer = client.post("/api/memories/photo", json={"image": PHOTO})
    return answer, writer, painter


def tell_the_story(connection, conversation_id: str) -> int:
    """She tells it in the memory talk; at the end save_memory fills the page."""
    db.save_message(connection, conversation_id, "assistant", "What do you remember about that day at the lake?")
    db.save_message(connection, conversation_id, "user", "Every summer we went to the lake with Maria, the water was cold and green")
    db.save_message(connection, conversation_id, "assistant", "When was that?")
    db.save_message(connection, conversation_id, "user", "It was 1962, we had a little blue rowboat and I rowed it all the way across by myself")
    memory_id, new = tools.save_memory(connection, conversation_id, "memory")
    connection.commit()
    assert new, "the photo's page is filled in, written, and painted once"
    return memory_id


# ---------- Starting from a photo ----------

def test_buddy_describes_the_photo_and_asks_one_question(client, connection, monkeypatch):
    answer, writer, painter = start_from_photo(client, monkeypatch)
    assert answer.status_code == 200
    started = answer.json()
    assert started["opening"] == DESCRIPTION["scene"] + " " + DESCRIPTION["question"]
    assert started["conversation_id"].startswith("photo-")
    row = connection.execute("SELECT * FROM memories WHERE id = ?", (started["id"],)).fetchone()
    assert row["status"] == "telling" and row["people"] == 1 and row["photo_scene"] == DESCRIPTION["scene"]
    # Her photo is kept on this computer (never sent anywhere to be painted).
    assert (memories.pictures_dir() / row["photo"]).read_bytes() == JPEG
    # The description came from Spark with the photo, with the no-names instructions.
    parts = writer.calls[0][1]["content"]
    assert {"type": "image_url", "image_url": {"url": PHOTO}} in parts
    assert writer.calls[0][0]["content"] == prompts.PHOTO_MEMORY
    assert "never" in prompts.PHOTO_MEMORY.lower() and "who" in prompts.PHOTO_MEMORY.lower()


def test_people_in_the_photo_make_it_the_pages_own_picture(client, connection, monkeypatch):
    answer, writer, painter = start_from_photo(client, monkeypatch, sam=A_PERSON)
    started = answer.json()
    memory_id = tell_the_story(connection, started["conversation_id"])
    assert memory_id == started["id"]
    memories.make_page(memory_id)
    row = connection.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    assert row["status"] == "ready" and row["title"] == GOOD_PAGE["title"]
    assert painter.prompts == [], "a photo with people is never painted (no likeness is ever made)"
    assert row["picture"] == f"{memory_id}.jpg"
    assert (memories.pictures_dir() / row["picture"]).read_bytes() == JPEG
    page = client.get("/api/memories").json()["pages"][0]
    assert page["picture"].startswith(f"/api/memories/{memory_id}/picture") and page["people"] is True


def test_a_photo_without_people_is_painted_in_the_books_style(client, connection, monkeypatch):
    answer, writer, painter = start_from_photo(client, monkeypatch, sam="")  # SAM found nobody
    started = answer.json()
    memory_id = tell_the_story(connection, started["conversation_id"])
    memories.make_page(memory_id)
    row = connection.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    assert row["people"] == 0 and row["status"] == "ready" and row["picture"] == f"{memory_id}.webp"
    assert len(painter.prompts) == 1 and painter.prompts[0].startswith(memories.STYLE)
    assert GOOD_PAGE["scene"] in painter.prompts[0]
    # Her photo stays with the page too, served only by its own name.
    page = client.get("/api/memories").json()["pages"][0]
    assert page["photo"].startswith(f"/api/memories/{memory_id}/photo") and page["people"] is False
    assert client.get(page["photo"]).content == JPEG


def test_when_sam_cant_look_the_photo_counts_as_having_people(client, connection, monkeypatch):
    # Fail closed: never paint from a photo that might show someone.
    answer, writer, painter = start_from_photo(client, monkeypatch, sam=meta_client.MetaError("SAM failed with HTTP 500"))
    row = connection.execute("SELECT people FROM memories WHERE id = ?", (answer.json()["id"],)).fetchone()
    assert row["people"] == 1


def test_the_writer_knows_what_the_photo_shows(client, connection, monkeypatch):
    page = dict(GOOD_PAGE, paragraphs=["Every summer we went to the lake with Maria. There was a wooden dock.",
                                       "In 1962 I rowed our little blue rowboat across by myself."])
    answer, writer, painter = start_from_photo(client, monkeypatch, sam="", page=page)
    memory_id = tell_the_story(connection, answer.json()["conversation_id"])
    memories.make_page(memory_id)
    row = connection.execute("SELECT title, story FROM memories WHERE id = ?", (memory_id,)).fetchone()
    # "dock" came from the photo's description, not her words: still allowed.
    assert "wooden dock" in json.loads(row["story"])[0]
    assert DESCRIPTION["scene"] in writer.calls[1][1]["content"]


@pytest.mark.parametrize("description", [
    {"scene": "Rose and Tom standing by the lake.", "question": "Who is that with you?"},  # names, and who
    {"scene": "A hospital bed by a window.", "question": "What do you remember?"},         # health
    {"scene": "A lake.", "question": "You should visit it again, when?"},                    # advice
    {"scene": "A lake in 1962.", "question": "What do you remember?"},                       # a number it can't know
])
def test_a_description_that_breaks_a_rule_is_dropped_for_fixed_words(client, connection, monkeypatch, description):
    answer, writer, painter = start_from_photo(client, monkeypatch, description=description)
    assert answer.json()["opening"] == memories.PHOTO_OPENING
    row = connection.execute("SELECT photo_scene FROM memories WHERE id = ?", (answer.json()["id"],)).fetchone()
    assert row["photo_scene"] == ""


def test_when_spark_cant_describe_it_buddy_still_asks(client, connection, monkeypatch):
    fake_sam(monkeypatch, "")
    monkeypatch.setattr(meta_client, "structured", FakeWriter(meta_client.MetaError("chat failed with HTTP 500")))

    def failing(messages, name, schema, reasoning="medium", max_tokens=3000):
        raise meta_client.MetaError("chat failed with HTTP 500")

    monkeypatch.setattr(meta_client, "structured", failing)
    answer = client.post("/api/memories/photo", json={"image": PHOTO})
    assert answer.status_code == 200 and answer.json()["opening"] == memories.PHOTO_OPENING


def test_only_a_photo_is_accepted(client, connection, monkeypatch):
    fake_sam(monkeypatch, "")
    refused = client.post("/api/memories/photo", json={"image": "data:text/html;base64,PGI+"})
    assert refused.status_code == 400
    assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0


# ---------- A photo she never told about ----------

def test_an_untold_photo_stays_out_of_the_book_and_fades_after_a_day(client, connection, monkeypatch):
    answer, writer, painter = start_from_photo(client, monkeypatch)
    memory_id = answer.json()["id"]
    assert client.get("/api/memories").json()["pages"] == []  # not a page yet
    assert client.get(f"/api/memories/{memory_id}/photo").status_code == 200
    old = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
    connection.execute("UPDATE memories SET created_at = ? WHERE id = ?", (old, memory_id))
    connection.commit()
    client.get("/api/memories")  # housekeeping: a day-old untold photo is forgotten, file and all
    assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0
    assert not list(memories.pictures_dir().glob("photo-*"))


def test_the_family_never_hears_of_an_untold_photo(client, connection, monkeypatch):
    start_from_photo(client, monkeypatch)
    today = datetime.now().date()
    assert family.memory_lines(connection, today.isoformat() + "T00:00:00", today.isoformat() + "T23:59:59") == []
    assert family.day_facts(connection, today, dict(db.get_profile(connection), share_diary=True))["memories"] == []
