# Tests for the Memory book (docs/SPEC.md feature 10): she tells Buddy a
# memory, Muse Spark writes a page in her own words, and Muse Image paints a
# picture for it. Every Meta call is FAKE here. Made-up memories only.

import base64
import json
import sqlite3
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app import db, family, memories, meta_client, tools
from app.main import app
from tests.test_companion import reply, tool_call, use_fake

# The first bytes of a real WebP file ("RIFF", a size, "WEBP"), then filler.
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24

GOOD_PAGE = {
    "title": "Summers at the lake",
    "paragraphs": [
        "Every summer we went to the lake with Maria. The water was cold and green.",
        "We had a little blue rowboat, and in 1962 I rowed it all the way across by myself.",
    ],
    "scene": "A small blue rowboat on a green lake in summer, two small figures on the shore seen from behind.",
}

HER_STORY = "Every summer we went to the lake with Maria, the water was cold and green"
HER_ANSWER = "It was 1962, we had a little blue rowboat and I rowed it all the way across by myself"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def connection(safe_test_setup):
    opened = db.get_connection(safe_test_setup)
    db.get_profile(opened)
    opened.execute("UPDATE profile SET preferred_name = 'Rose', family_name = 'Maria', "
                   "family_email = 'maria@example.com' WHERE id = 1")
    opened.commit()
    yield opened
    opened.close()


class FakeWriter:
    """Plays back pages for Muse Spark's structured answer."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.calls = []

    def __call__(self, messages, name, schema, reasoning="medium", max_tokens=3000):
        self.calls.append(messages)
        return self.pages.pop(0)


class FakePainter:
    """Stands in for meta_client.paint: remembers each prompt."""

    def __init__(self, picture=WEBP):
        self.picture = picture
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.picture, Exception):
            raise self.picture
        return self.picture


def fake_meta(monkeypatch, pages=(GOOD_PAGE,), picture=WEBP):
    writer, painter = FakeWriter(*pages), FakePainter(picture)
    monkeypatch.setattr(meta_client, "structured", writer)
    monkeypatch.setattr(meta_client, "paint", painter)
    return writer, painter


def memory_chat(client, text, conversation="day1-memory-1"):
    return client.post("/api/chat", json={"conversation_id": conversation, "text": text, "mode": "memory"}).json()


def tell_the_lake_story(client, monkeypatch):
    """A memory talk: her story, one follow-up question, her answer, saved."""
    ai = use_fake(
        monkeypatch,
        reply("What a lovely place. When was that?"),
        tool_call("c1", "save_memory", {}),
        reply("I'm writing that into your memory book, and painting a picture for it."),
    )
    memory_chat(client, HER_STORY)
    return memory_chat(client, HER_ANSWER), ai


# ---------- Painting with Muse Image (meta_client.paint) ----------

class FakeImages:
    def __init__(self, data):
        self.data = data
        self.requests = []

    def generate(self, **request):
        self.requests.append(request)
        return SimpleNamespace(data=self.data)


def test_paint_asks_muse_image_for_one_picture_with_web_lookups_off(monkeypatch):
    images = FakeImages([SimpleNamespace(b64_json=base64.b64encode(WEBP).decode())])
    monkeypatch.setattr(meta_client, "_client", lambda: SimpleNamespace(images=images))
    assert meta_client.paint("a rowboat on a lake") == WEBP
    request = images.requests[0]
    assert request["model"] == "muse-image-1.0"  # a standard model
    assert (request["prompt"], request["n"], request["size"]) == ("a rowboat on a lake", 1, "1536x1024")
    # Her story never leaves the request: no web or image search, no shell.
    assert request["extra_body"] == {"tool_enablement": {
        "enable_image_search": False, "enable_web_search": False, "enable_shell": False}}


def test_paint_with_no_picture_in_the_answer_is_a_meta_error(monkeypatch):
    monkeypatch.setattr(meta_client, "_client", lambda: SimpleNamespace(images=FakeImages([])))
    with pytest.raises(meta_client.MetaError):
        meta_client.paint("a rowboat on a lake")


def server_error(status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.meta.ai/v1/images/generations"))
    return openai.InternalServerError("painting failed", response=response, body=None)


class FailingImages(FakeImages):
    """Fails with the given HTTP errors first, then paints."""

    def __init__(self, *errors):
        super().__init__([SimpleNamespace(b64_json=base64.b64encode(WEBP).decode())])
        self.errors = list(errors)

    def generate(self, **request):
        self.requests.append(request)
        if self.errors:
            raise self.errors.pop(0)
        return SimpleNamespace(data=self.data)


def test_paint_tries_again_when_meta_says_503_but_not_500(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    retried = FailingImages(server_error(503))
    monkeypatch.setattr(meta_client, "_client", lambda: SimpleNamespace(images=retried))
    assert meta_client.paint("a rowboat") == WEBP and len(retried.requests) == 2

    broken = FailingImages(server_error(500))
    monkeypatch.setattr(meta_client, "_client", lambda: SimpleNamespace(images=broken))
    with pytest.raises(meta_client.MetaError):
        meta_client.paint("a rowboat")
    assert len(broken.requests) == 1


# ---------- Saving a memory ----------

def test_a_memory_talk_saves_her_words_and_the_page_is_written_and_painted(client, monkeypatch, connection):
    writer, painter = fake_meta(monkeypatch)
    body, ai = tell_the_lake_story(client, monkeypatch)
    assert body["memory_saved"] and body["memory_done"]
    assert {"type": "open", "screen": "memories", "label": "Open my memory book"} in body["actions"]
    # The AI was told how a memory talk goes.
    assert "save_memory" in ai.calls[0][0]["content"] and "one at a time" in ai.calls[0][0]["content"]

    row = connection.execute("SELECT * FROM memories").fetchone()
    assert row["her_words"] == HER_STORY + ". " + HER_ANSWER + "."
    # The writer saw the whole talk, Buddy's question too, so "1962" makes sense.
    talk = json.dumps(writer.calls[0])
    assert "When was that?" in talk and "1962" in talk
    # The picture: the fixed style first, then the scene the writer described.
    assert painter.prompts == [memories.STYLE + "\n\nThe scene: " + GOOD_PAGE["scene"]]

    page = client.get("/api/memories").json()["pages"][0]
    assert (page["status"], page["title"], page["paragraphs"]) == ("ready", GOOD_PAGE["title"], GOOD_PAGE["paragraphs"])
    picture = client.get(page["picture"])
    assert picture.status_code == 200 and picture.content == WEBP
    assert picture.headers["content-type"] == "image/webp"


def can_write(db_path):
    """True if another part of the app could save right now (no one holds the write lock)."""
    other = sqlite3.connect(db_path, timeout=0)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.rollback()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        other.close()


def test_nothing_waits_on_the_database_while_the_ai_writes_or_paints(client, monkeypatch, safe_test_setup):
    writer, painter = FakeWriter(GOOD_PAGE), FakePainter()
    free = []

    def writing(*args, **kwargs):
        free.append(can_write(safe_test_setup))
        return writer(*args, **kwargs)

    def painting(prompt):
        free.append(can_write(safe_test_setup))
        return painter(prompt)

    monkeypatch.setattr(meta_client, "structured", writing)
    monkeypatch.setattr(meta_client, "paint", painting)
    tell_the_lake_story(client, monkeypatch)
    assert free == [True, True]


def test_saving_again_after_the_ai_saved_paints_the_page_once(client, monkeypatch):
    _, painter = fake_meta(monkeypatch)
    body, _ = tell_the_lake_story(client, monkeypatch)
    again = client.post("/api/memories", json={"conversation_id": "day1-memory-1", "mode": "memory"})
    assert again.json()["id"] == body["memory_saved"]
    assert len(client.get("/api/memories").json()["pages"]) == 1
    assert len(painter.prompts) == 1


def said_later(connection, conversation, words, seconds):
    """Her words in a talk, a few seconds from now (talks take time)."""
    db.save_message(connection, conversation, "user", words)
    later = (datetime.now() + timedelta(seconds=seconds)).isoformat(timespec="seconds")
    connection.execute("UPDATE messages SET created_at = ? WHERE id = last_insert_rowid()", (later,))
    connection.commit()


def test_two_memories_in_one_day_of_ordinary_talk_are_two_pages(client, monkeypatch, connection):
    _, painter = fake_meta(monkeypatch, pages=(GOOD_PAGE, GOOD_PAGE, GOOD_PAGE, GOOD_PAGE))
    db.save_message(connection, "day1", "user", HER_STORY + ". " + HER_ANSWER)
    connection.commit()
    first = client.post("/api/memories", json={"conversation_id": "day1"}).json()
    # A short "yes, save it" afterward is the same memory, not a new page.
    said_later(connection, "day1", "Yes please, save it", seconds=5)
    assert client.post("/api/memories", json={"conversation_id": "day1"}).json()["id"] == first["id"]
    # Another real memory later that day is a page of its own, without the first one.
    said_later(connection, "day1", "Every Sunday my father made pancakes for all of us and sang to the radio", 10)
    second = client.post("/api/memories", json={"conversation_id": "day1"}).json()
    assert second["id"] != first["id"] and len(painter.prompts) == 2
    words = connection.execute("SELECT her_words FROM memories WHERE id = ?", (second["id"],)).fetchone()[0]
    assert "Every Sunday my father made pancakes" in words and "lake" not in words


def test_words_around_a_safety_screen_never_reach_a_page(client, monkeypatch, connection):
    def ai_is_down(*args, **kwargs):
        raise meta_client.MetaError("down")

    fake_meta(monkeypatch)
    monkeypatch.setattr(meta_client, "structured", ai_is_down)  # so the page is exactly her saved words
    db.save_message(connection, "day1", "user", "I had a hard night")
    connection.commit()
    # The crisis screen in another talk: her words there and here are not kept.
    assert memory_chat(client, "I wish I wasn't here anymore")["show"] == "crisis"
    db.save_message(connection, "day1", "user", HER_STORY)
    connection.commit()
    client.post("/api/memories", json={"conversation_id": "day1"})
    page = client.get("/api/memories").json()["pages"][0]
    assert page["paragraphs"] == [HER_STORY + "."]


def test_a_check_in_or_something_hurts_talk_never_becomes_a_page(connection):
    db.save_message(connection, "day1-diary-1", "user", HER_STORY)
    context = {"connection": connection, "profile": db.get_profile(connection),
               "conversation_id": "day1-diary-1", "mode": "diary"}
    result, buttons = tools.run_tool("save_memory", "{}", context)
    assert result["ok"] is False and buttons == []
    assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0


def test_saving_twice_in_one_talk_keeps_one_page(client, monkeypatch, connection):
    fake_meta(monkeypatch, pages=(GOOD_PAGE, GOOD_PAGE))
    use_fake(
        monkeypatch,
        tool_call("c1", "save_memory", {}),
        tool_call("c2", "save_memory", {}),
        reply("It's in your memory book."),
    )
    memory_chat(client, HER_STORY)
    assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1


def test_her_third_answer_saves_the_memory_even_if_the_ai_did_not(client, monkeypatch, connection):
    fake_meta(monkeypatch)
    use_fake(monkeypatch, reply("When was that?"), reply("Who was there?"), reply("How lovely."))
    memory_chat(client, HER_STORY)
    memory_chat(client, "In 1962")
    body = memory_chat(client, "Just me and Maria")
    assert body["memory_saved"] and body["memory_done"]
    assert connection.execute("SELECT her_words FROM memories").fetchone()[0].endswith("Just me and Maria.")


def test_the_safety_net_runs_first_in_a_memory_talk(client, monkeypatch, connection):
    use_fake(monkeypatch)  # no answers: the AI must not be asked
    body = memory_chat(client, "my chest feels really tight")
    assert body["show"] == "emergency"
    assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0


def test_in_ordinary_talk_buddy_can_offer_the_save_button(client, monkeypatch):
    use_fake(monkeypatch, tool_call("c1", "offer_memory_page", {}),
             reply("What a lovely memory. Would you like me to put it in your memory book?"))
    body = client.post("/api/chat", json={"conversation_id": "day1", "text": HER_STORY}).json()
    assert {"type": "memory", "label": "Save it in my memory book"} in body["actions"]
    assert not body["memory_saved"]


def test_the_save_button_makes_a_page_from_her_recent_words(client, monkeypatch, connection):
    fake_meta(monkeypatch)
    db.save_message(connection, "day1", "user", HER_STORY)
    db.save_message(connection, "day1", "assistant", "What a lovely memory. When was that?")
    db.save_message(connection, "day1", "user", HER_ANSWER)
    connection.commit()
    page = client.post("/api/memories", json={"conversation_id": "day1"}).json()
    assert page["id"]
    assert client.get("/api/memories").json()["pages"][0]["status"] == "ready"


def test_the_save_button_needs_a_memory_first(client):
    assert client.post("/api/memories", json={"conversation_id": "day1"}).status_code == 400


# ---------- No invented facts, no advice ----------

def test_names_and_numbers_she_never_said_are_found():
    found = memories.invented("We went to Paris in 1962 with Maria.", "we went to the city with maria")
    assert found == ["Paris", "1962"]


def test_apostrophes_inside_words_are_typeset_and_quotes_are_left_alone():
    assert memories.curly("aunt Lucy's farm, 'Come in!'") == "aunt Lucy’s farm, 'Come in!'"


def test_words_at_the_start_of_a_sentence_are_not_names():
    assert memories.invented("Summer was warm. The water was green. I loved it.", "the water was warm") == []


def test_a_page_with_invented_facts_is_written_again_and_told_why(client, monkeypatch, connection):
    invented = dict(GOOD_PAGE, paragraphs=["We sailed to Paris with Maria.", "It was 1962."])
    writer, _ = fake_meta(monkeypatch, pages=(invented, GOOD_PAGE))
    tell_the_lake_story(client, monkeypatch)
    assert "Paris" in writer.calls[1][-1]["content"]
    assert client.get("/api/memories").json()["pages"][0]["title"] == GOOD_PAGE["title"]


def test_a_page_that_invents_twice_uses_her_own_words(client, monkeypatch):
    invented = dict(GOOD_PAGE, paragraphs=["We sailed to Paris.", "It was lovely."])
    fake_meta(monkeypatch, pages=(invented, invented))
    tell_the_lake_story(client, monkeypatch)
    page = client.get("/api/memories").json()["pages"][0]
    assert page["title"] == "A memory"
    assert page["paragraphs"] == [HER_STORY + ". " + HER_ANSWER + "."]


def test_a_page_with_advice_uses_her_own_words(client, monkeypatch):
    advice = dict(GOOD_PAGE, paragraphs=["The lake was cold.", "You should rest your knee and try ice."])
    fake_meta(monkeypatch, pages=(advice, advice))
    tell_the_lake_story(client, monkeypatch)
    assert client.get("/api/memories").json()["pages"][0]["title"] == "A memory"


def test_when_the_ai_is_down_the_page_keeps_her_words(client, monkeypatch):
    def ai_is_down(*args, **kwargs):
        raise meta_client.MetaError("down")

    fake_meta(monkeypatch, picture=meta_client.MetaError("down"))
    monkeypatch.setattr(meta_client, "structured", ai_is_down)
    tell_the_lake_story(client, monkeypatch)
    page = client.get("/api/memories").json()["pages"][0]
    assert (page["title"], page["status"], page["picture"]) == ("A memory", "no_picture", "")


# ---------- Painting again, and pages that got stuck ----------

def test_a_failed_painting_keeps_the_page_and_can_be_painted_again(client, monkeypatch):
    fake_meta(monkeypatch, picture=meta_client.MetaError("busy"))
    tell_the_lake_story(client, monkeypatch)
    page = client.get("/api/memories").json()["pages"][0]
    assert (page["status"], page["title"], page["picture"]) == ("no_picture", GOOD_PAGE["title"], "")

    monkeypatch.setattr(meta_client, "paint", FakePainter())
    client.post(f"/api/memories/{page['id']}/paint")
    assert client.get("/api/memories").json()["pages"][0]["status"] == "ready"


def test_a_page_stuck_for_minutes_can_be_painted_again(client, connection):
    old = (datetime.now() - timedelta(minutes=20)).isoformat(timespec="seconds")
    connection.execute("INSERT INTO memories (created_at, updated_at, her_words, status) VALUES (?, ?, 'Hello', 'painting')",
                       (old, old))
    connection.commit()
    assert client.get("/api/memories").json()["pages"][0]["status"] == "no_picture"


def test_something_that_only_looks_like_a_picture_is_not_saved(client, monkeypatch):
    fake_meta(monkeypatch, picture=b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 24)  # a sound file, not a WebP
    tell_the_lake_story(client, monkeypatch)
    assert client.get("/api/memories").json()["pages"][0]["status"] == "no_picture"


def test_the_picture_route_never_follows_a_strange_file_name(client, connection):
    connection.execute("INSERT INTO memories (created_at, updated_at, her_words, picture, status) "
                       "VALUES (?, ?, 'Hello', '../check.db', 'ready')", (db.now(), db.now()))
    connection.commit()
    assert client.get("/api/memories/1/picture").status_code == 404


def test_only_a_painted_page_has_a_picture(client, connection):
    connection.execute("INSERT INTO memories (created_at, updated_at, her_words, status) VALUES (?, ?, 'Hello', 'writing')",
                       (db.now(), db.now()))
    connection.commit()
    assert client.get("/api/memories/1/picture").status_code == 404
    assert client.get("/api/memories/99/picture").status_code == 404


# ---------- The book, and sharing it ----------

def test_pages_come_newest_first_with_an_email_for_family(client, monkeypatch, connection):
    second = dict(GOOD_PAGE, title="The blue rowboat",
                  paragraphs=["We had a little blue rowboat.", "In 1962 I rowed it all the way across by myself."])
    fake_meta(monkeypatch, pages=(GOOD_PAGE, second))
    tell_the_lake_story(client, monkeypatch)
    use_fake(monkeypatch, tool_call("c1", "save_memory", {}), reply("Saved."))
    memory_chat(client, HER_ANSWER, conversation="day1-memory-2")
    pages = client.get("/api/memories").json()["pages"]
    assert [page["title"] for page in pages] == ["The blue rowboat", "Summers at the lake"]

    link = urlsplit(pages[1]["mailto"])
    fields = parse_qs(link.query)
    assert unquote(link.path) == "maria@example.com"
    assert fields["subject"] == ["A memory from Rose: Summers at the lake"]
    body = fields["body"][0].replace("\r\n", "\n")
    assert GOOD_PAGE["paragraphs"][0] in body and GOOD_PAGE["paragraphs"][1] in body


def test_the_family_update_names_the_new_memory_pages(client, monkeypatch, connection):
    fake_meta(monkeypatch)
    tell_the_lake_story(client, monkeypatch)
    text = family.summary(connection, date.today())["text"]
    assert 'Memory book: 1 new page\n  - "Summers at the lake"' in text


def test_the_family_update_has_no_memory_line_on_a_day_without_pages(connection):
    assert "Memory book" not in family.summary(connection, date.today())["text"]
