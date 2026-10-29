# Tests for "Check a message", the scam checker (docs/SPEC.md feature 7,
# docs/SAFETY.md section 8): the plain red-flag rules, /api/scam-check with a
# FAKE AI, and meta_client.structured (the structured-output call). No test
# ever reaches the real API. Made-up messages and people only.

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, meta_client, scam
from app.main import app

GRANDSON = "Grandma it's me, I'm in jail, send $2,000 in gift cards and don't tell mom"
PACKAGE = "USPS: your package is on hold, pay $1.99 at usps-redelivery-help.com"
SOCIAL_SECURITY = "Your Social Security number is suspended. Call now to avoid arrest."
DOCTOR = "Hi Rose, Dr. Lee's office confirming your appointment Thursday at 2 PM."

ALWAYS = [
    "Don't click links, reply, or call numbers in the message.",
    "Hang up. Call the real number yourself (from the back of your card or a bill), or call Maria first.",
    "Never share passwords, codes, bank numbers, or your Social Security number.",
]


@pytest.fixture
def client():
    test_client = TestClient(app)
    test_client.put("/api/profile", json={"preferred_name": "Rose", "family_name": "Maria", "family_phone": "555-0100"})
    return test_client


class FakeAI:
    """Plays back scripted structured answers (or a problem) and records each call."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, messages, name, schema, reasoning="medium"):
        self.calls.append({"messages": messages, "name": name, "schema": schema, "reasoning": reasoning})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def use_ai(monkeypatch, verdict="likely_scam", red_flags=("Asks for gift cards",), explanation="This has warning signs."):
    answer = {"verdict": verdict, "red_flags": list(red_flags), "explanation": explanation}
    fake = FakeAI(answer if verdict else meta_client.MetaError("down"))
    monkeypatch.setattr(meta_client, "structured", fake)
    return fake


def check(client, **body):
    return client.post("/api/scam-check", json=body)


def saved_checks(path):
    connection = db.get_connection(path)
    rows = [dict(r) for r in connection.execute("SELECT input_kind, excerpt, verdict, red_flags FROM scam_checks")]
    connection.close()
    return rows


# ---------- The plain rules (no AI) ----------

@pytest.mark.parametrize("message", [GRANDSON, PACKAGE, SOCIAL_SECURITY])
def test_the_safety_md_scams_are_likely_scams_by_the_rules_alone(message):
    verdict, flags = scam.rules_verdict(message)
    assert verdict == "likely_scam"
    assert len(flags) >= 2


def test_the_rules_name_the_red_flags_in_plain_words():
    _, flags = scam.rules_verdict(GRANDSON)
    assert "Asks to be paid with gift cards" in flags
    assert "Asks you to keep it secret" in flags
    assert "Says it's family and needs money" in flags


@pytest.mark.parametrize("message", [
    DOCTOR,
    "My grandson visited, we bought gift wrap for his birthday.",
    "Your prescription is ready for pickup at the pharmacy.",
])
def test_ordinary_messages_have_no_red_flags(message):
    assert scam.rules_verdict(message) == (None, [])


def test_one_red_flag_alone_is_suspicious():
    assert scam.rules_verdict("Congratulations, you have won our prize draw!")[0] == "suspicious"


def test_the_excerpt_is_short_and_has_no_long_numbers():
    excerpt = scam.excerpt("Your account 1234567890 is locked. " + "x" * 300)
    assert "1234567890" not in excerpt and "•••" in excerpt
    assert len(excerpt) <= 120


def test_links_and_phone_numbers_are_taken_out_of_the_ais_words():
    cleaned = scam.without_links_or_numbers("Do not call 1-888-555-0199 or visit https://pay-now.example.com today.")
    assert "555" not in cleaned and "http" not in cleaned
    assert cleaned == "Do not call the number or visit the link today."


# ---------- /api/scam-check with a fake AI ----------

def test_a_likely_scam_comes_back_with_its_title_red_flags_and_what_to_do(client, monkeypatch):
    use_ai(monkeypatch, "likely_scam", ["Asks for gift cards", "Says to keep it secret"], "Real family never asks for gift cards.")
    body = check(client, text=GRANDSON, kind="text").json()
    assert body["verdict"] == "likely_scam"
    assert body["title"] == "Likely scam"
    assert body["red_flags"] == ["Asks for gift cards", "Says to keep it secret"]
    assert body["explanation"] == "Real family never asks for gift cards."
    assert body["what_to_do"] == ALWAYS
    assert body["if_you_paid"][2].startswith("Call the National Elder Fraud Hotline at 1-833-372-8311")
    assert {a["href"] for a in body["actions"]} == {"tel:555-0100", "tel:18333728311"}


def test_the_ai_reads_it_with_a_strict_schema_and_medium_reasoning(client, monkeypatch):
    fake = use_ai(monkeypatch)
    check(client, text=GRANDSON, kind="text")
    call = fake.calls[0]
    assert call["reasoning"] == "medium"
    assert call["schema"]["required"] == ["verdict", "red_flags", "explanation"]
    assert call["schema"]["properties"]["verdict"]["enum"] == ["likely_scam", "suspicious", "looks_safe"]
    assert GRANDSON in call["messages"][-1]["content"]


def test_the_ai_can_never_lower_what_the_rules_found(client, monkeypatch):
    use_ai(monkeypatch, "looks_safe", [], "This looks like a normal message from family.")
    body = check(client, text=GRANDSON, kind="text").json()
    assert body["verdict"] == "likely_scam"
    assert "Asks to be paid with gift cards" in body["red_flags"]
    assert body["explanation"] == "This message has the warning signs of a scam."  # not the AI's "looks normal"


def test_a_message_that_looks_safe_still_says_how_to_be_sure(client, monkeypatch):
    use_ai(monkeypatch, "looks_safe", [], "This looks like an ordinary appointment reminder.")
    body = check(client, text=DOCTOR, kind="text").json()
    assert body["verdict"] == "looks_safe"
    assert body["what_to_do"] == [
        "If you're not sure, call them at a number you already know, not one in the message.",
        "Never share passwords, codes, bank numbers, or your Social Security number.",
    ]
    assert body["if_you_paid"] == [] and body["actions"] == []


def test_when_the_ai_is_down_the_rules_still_answer(client, monkeypatch):
    use_ai(monkeypatch, verdict=None)
    body = check(client, text=GRANDSON, kind="text").json()
    assert body["verdict"] == "likely_scam"
    assert body["explanation"] == "This message has the warning signs of a scam."
    assert body["what_to_do"] == ALWAYS


def test_when_the_ai_is_down_and_no_rule_fires_it_says_not_sure(client, monkeypatch):
    use_ai(monkeypatch, verdict=None)
    body = check(client, text="Hello, is this Rose? Call me back.", kind="text").json()
    assert body["verdict"] == "suspicious"
    assert body["explanation"] == "I'm not sure about this one. Don't click anything, and call Maria before you reply or pay."


def test_a_strange_ai_answer_counts_as_the_ai_being_down(client, monkeypatch):
    use_ai(monkeypatch, "maybe", [], "Hmm.")
    body = check(client, text="Hello, is this Rose? Call me back.", kind="text").json()
    assert body["verdict"] == "suspicious"
    assert body["explanation"].startswith("I'm not sure about this one.")


def test_advice_in_the_ais_words_is_replaced(client, monkeypatch):
    use_ai(monkeypatch, "suspicious", ["Mentions your Medicare card"], "You should take 2 tablets and rest.")
    body = check(client, text="Medicare: confirm your card number to keep your benefits", kind="text").json()
    assert "tablets" not in body["explanation"]
    assert body["explanation"] == "This message has the warning signs of a scam."


def test_a_photo_goes_to_the_ai_as_an_image_and_is_never_stored(client, monkeypatch, safe_test_setup):
    fake = use_ai(monkeypatch)
    photo = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ=="
    assert check(client, image=photo, kind="photo").status_code == 200
    parts = fake.calls[0]["messages"][-1]["content"]
    assert {"type": "image_url", "image_url": {"url": photo}} in parts
    assert saved_checks(safe_test_setup)[0]["excerpt"] == "(photo)"


@pytest.mark.parametrize("body", [
    {"text": "   ", "kind": "text"},
    {"image": "data:text/html;base64,PGgxPg==", "kind": "photo"},
    {"image": "not a picture", "kind": "photo"},
    {"image": "data:image/jpeg;base64," + "A" * 3_100_000, "kind": "photo"},
    {"text": GRANDSON, "kind": "carrier pigeon"},
])
def test_empty_or_strange_input_is_refused_kindly(client, monkeypatch, body):
    fake = use_ai(monkeypatch)
    answer = check(client, **body)
    assert answer.status_code == 400
    assert "error" not in answer.json()["detail"].lower()
    assert fake.calls == []


def test_each_check_is_kept_as_a_short_excerpt(client, monkeypatch, safe_test_setup):
    use_ai(monkeypatch, "likely_scam", ["Asks for gift cards"])
    check(client, text="Call 18885550199 now. " + GRANDSON, kind="voice")
    row = saved_checks(safe_test_setup)[0]
    assert row["input_kind"] == "voice" and row["verdict"] == "likely_scam"
    assert "18885550199" not in row["excerpt"] and len(row["excerpt"]) <= 120
    assert json.loads(row["red_flags"]) == ["Asks for gift cards"]


def test_the_ais_red_flags_are_kept_short(client, monkeypatch):
    use_ai(monkeypatch, "likely_scam", ["One", "Two", "Three", "Four", "Five", "Six"])
    assert check(client, text=GRANDSON, kind="text").json()["red_flags"] == ["One", "Two", "Three", "Four"]


# ---------- meta_client.structured ----------

class FakeOpenAI:
    """Stands in for the openai package's client: returns the given texts in turn."""

    def __init__(self, *contents):
        self.contents = list(contents)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.requests.append(request)
        message = SimpleNamespace(content=self.contents.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def use_openai(monkeypatch, *contents):
    fake = FakeOpenAI(*contents)
    monkeypatch.setattr(meta_client, "_client", lambda: fake)
    return fake


def test_structured_sends_a_strict_json_schema_and_returns_the_parsed_answer(monkeypatch):
    fake = use_openai(monkeypatch, '{"verdict": "looks_safe"}')
    answer = meta_client.structured([{"role": "user", "content": "hi"}], "scam_result", {"type": "object"})
    assert answer == {"verdict": "looks_safe"}
    request = fake.requests[0]
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "scam_result", "schema": {"type": "object"}, "strict": True},
    }
    assert request["reasoning_effort"] == "medium"
    assert request["model"] == "muse-spark-1.3"


def test_structured_asks_once_more_when_the_answer_is_not_json(monkeypatch):
    fake = use_openai(monkeypatch, "Sorry, here you go:", '{"verdict": "suspicious"}')
    assert meta_client.structured([], "scam_result", {})["verdict"] == "suspicious"
    assert len(fake.requests) == 2


def test_structured_gives_up_after_two_answers_that_are_not_json(monkeypatch):
    use_openai(monkeypatch, "nope", "still nope")
    with pytest.raises(meta_client.MetaError):
        meta_client.structured([], "scam_result", {})
