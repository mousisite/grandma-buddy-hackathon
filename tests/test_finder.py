# Tests for "Find my things" (app/finder.py and meta_client.segment):
# what she's looking for, SAM 3.1's answer line, the best match, and the
# sentence Buddy says. Every Meta call is faked; nothing reaches the real API.

import time
from types import SimpleNamespace

import httpx
import openai
import pytest

from app import finder, meta_client

PHOTO = "data:image/jpeg;base64,/9j/AAAA"

# SAM 3.1's answer line, in the documented format (one record per match:
# an id, a box, then a mask). x2 and y2 are inclusive; w and h are the
# photo's size; c is the confidence (include_confidence on).
ONE_MATCH = "<0f>0<|box;x1=100;y1=200;x2=199;y2=259;w=1000;h=800;c=0.91|><|mask;x=0;y=0;data=60,100,!abc|>"
TWO_MATCHES = (
    "<0f>0<|box;x1=10;y1=20;x2=49;y2=59;w=1000;h=800;c=0.55|><|mask;x=0;y=0;data=40,40,!ab|>,"
    "3<|box;x1=600;y1=500;x2=699;y2=579;w=1000;h=800;c=0.88|><|mask;x=0;y=0;data=80,100,!cd|>"
)


# ---------- What she's looking for ----------

@pytest.mark.parametrize("said, thing", [
    ("glasses", "glasses"),
    ("Where are my glasses?", "glasses"),
    ("Buddy, where are my reading glasses?", "reading glasses"),
    ("I can't find my keys", "keys"),
    ("where's the TV remote", "remote control"),
    ("my clicker", "remote control"),
    ("Have you seen my specs?", "glasses"),
    ("my pills", "pill bottle"),
    ("Pill bottle", "pill bottle"),
    ("Help me find my phone please", "phone"),
])
def test_clean_thing_keeps_only_the_thing(said, thing):
    assert finder.clean_thing(said) == thing


def test_clean_thing_is_empty_when_she_named_nothing_and_short_when_she_rambles():
    assert finder.clean_thing("Where are my") == ""
    assert finder.clean_thing("   ") == ""
    assert len(finder.clean_thing("my big old blue and white striped knitting bag").split()) <= finder.MAX_WORDS


# ---------- SAM 3.1's answer ----------

def test_parse_matches_reads_each_box_with_its_confidence_and_photo_size():
    assert finder.parse_matches(ONE_MATCH) == [
        {"x1": 100, "y1": 200, "x2": 199, "y2": 259, "w": 1000, "h": 800, "score": 0.91},
    ]
    assert [match["score"] for match in finder.parse_matches(TWO_MATCHES)] == [0.55, 0.88]


def test_parse_matches_with_nothing_found_or_a_garbled_line_is_empty():
    assert finder.parse_matches("") == []  # SAM says "no match" with an empty line
    assert finder.parse_matches("<0f>") == []
    assert finder.parse_matches("<|box;x1=a;y1=2|>") == []
    assert finder.parse_matches("something else entirely") == []


def test_a_box_without_a_confidence_counts_as_sure():
    line = "<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10|>"
    assert finder.parse_matches(line)[0]["score"] == 1.0


def test_best_match_is_the_surest_one_and_only_if_sure_enough():
    assert finder.best_match(finder.parse_matches(TWO_MATCHES))["x1"] == 600
    unsure = "<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10;c=0.2|>"
    assert finder.best_match(finder.parse_matches(unsure)) is None
    assert finder.best_match([]) is None


# ---------- What Buddy says ----------

@pytest.mark.parametrize("box, place", [
    ({"x1": 50, "y1": 600, "x2": 150, "y2": 700}, "near the bottom left of your photo"),
    ({"x1": 800, "y1": 50, "x2": 900, "y2": 150}, "near the top right of your photo"),
    ({"x1": 450, "y1": 350, "x2": 550, "y2": 450}, "in the middle of your photo"),
    ({"x1": 50, "y1": 350, "x2": 150, "y2": 450}, "on the left side of your photo"),
    ({"x1": 450, "y1": 650, "x2": 550, "y2": 750}, "near the bottom of your photo"),
])
def test_where_words_says_where_in_the_photo(box, place):
    assert finder.where_words("keys", box, 1000, 800) == f"Your keys are {place}."


def test_where_words_says_is_for_one_thing():
    box = {"x1": 450, "y1": 350, "x2": 550, "y2": 450}
    assert finder.where_words("remote control", box, 1000, 800).startswith("Your remote control is ")


def test_not_found_is_kind_and_asks_for_another_photo():
    sentence = finder.not_found("glasses")
    assert "glasses" in sentence and "another" in sentence


class FakeSpark:
    """Stands in for meta_client.structured: answers with a sentence, or fails."""

    def __init__(self, sentence=None, error=None):
        self.sentence = sentence
        self.error = error
        self.calls = []

    def __call__(self, messages, name, schema, reasoning="medium", max_tokens=3000):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return {"sentence": self.sentence}


BOX = {"x1": 100, "y1": 200, "x2": 199, "y2": 259}


def test_describe_sends_the_photo_the_thing_and_where_it_is_to_spark(monkeypatch):
    spark = FakeSpark("Your glasses are on the side table, next to the lamp.")
    monkeypatch.setattr(meta_client, "structured", spark)
    assert finder.describe(PHOTO, "glasses", BOX, 1000, 800) == "Your glasses are on the side table, next to the lamp."
    developer, user = spark.calls[0]
    assert developer["role"] == "developer" and "never read" in developer["content"].lower()
    parts = user["content"]
    assert parts[1] == {"type": "image_url", "image_url": {"url": PHOTO}}
    assert "glasses" in parts[0]["text"]
    assert "10%" in parts[0]["text"] and "32%" in parts[0]["text"]  # the box, as parts of the photo


@pytest.mark.parametrize("spark", [
    FakeSpark(error=meta_client.MetaError("down")),
    FakeSpark("You should take your pills now, they are on the table."),  # advice: the guard says no
    FakeSpark("Your glasses are on the table. " * 8),  # far too long to say
    FakeSpark(""),
])
def test_describe_falls_back_to_plain_words_when_spark_cant_help(monkeypatch, spark):
    monkeypatch.setattr(meta_client, "structured", spark)
    assert finder.describe(PHOTO, "glasses", BOX, 1000, 800) == finder.where_words("glasses", BOX, 1000, 800)


# ---------- The whole look ----------

def test_find_with_a_match_returns_the_box_and_spark_sentence(monkeypatch):
    monkeypatch.setattr(meta_client, "segment", lambda image, phrase: ONE_MATCH)
    monkeypatch.setattr(meta_client, "structured", FakeSpark("Your keys are by the fruit bowl."))
    assert finder.find(PHOTO, "keys", 0, 0) == {
        "found": True,
        "sentence": "Your keys are by the fruit bowl.",
        "box": {"x1": 100, "y1": 200, "x2": 199, "y2": 259},
        "width": 1000,
        "height": 800,
    }


def test_sam_is_asked_in_words_it_knows_but_buddy_says_hers():
    assert finder.sam_words("pill bottle") == "medicine bottle"
    assert finder.sam_words("glasses") == "glasses"


def test_find_with_no_match_never_asks_spark(monkeypatch):
    spark = FakeSpark("should not be used")
    monkeypatch.setattr(meta_client, "segment", lambda image, phrase: "")
    monkeypatch.setattr(meta_client, "structured", spark)
    assert finder.find(PHOTO, "umbrella", 1000, 800) == {"found": False, "sentence": finder.not_found("umbrella")}
    assert spark.calls == []


# ---------- The SAM 3.1 call (meta_client.segment) ----------

class FakeResponses:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(output_text=answer)


def test_segment_sends_the_documented_sam_request(monkeypatch):
    responses = FakeResponses(ONE_MATCH)
    monkeypatch.setattr(meta_client, "_client", lambda: SimpleNamespace(responses=responses))
    assert meta_client.segment(PHOTO, "glasses") == ONE_MATCH
    request = responses.requests[0]
    assert request["model"] == "sam-3.1"
    assert request["input"] == [{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": "glasses"},
        {"type": "input_image", "image_url": PHOTO},
    ]}]
    assert request["metadata"] == {"include_confidence": "true", "mask_encoding": "one_bit"}
    assert request["store"] is False  # Meta doesn't keep her photo


def test_segment_with_nothing_found_is_an_empty_line(monkeypatch):
    monkeypatch.setattr(meta_client, "_client", lambda: SimpleNamespace(responses=FakeResponses(None)))
    assert meta_client.segment(PHOTO, "umbrella") == ""


def rate_limited():
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.meta.ai/v1/responses"))
    return openai.RateLimitError("busy", response=response, body=None)


def test_segment_waits_and_tries_again_when_meta_is_busy(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    responses = FakeResponses(rate_limited(), ONE_MATCH)
    monkeypatch.setattr(meta_client, "_client", lambda: SimpleNamespace(responses=responses))
    assert meta_client.segment(PHOTO, "glasses") == ONE_MATCH and len(responses.requests) == 2


def test_segment_without_a_key_is_a_meta_error(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "")
    with pytest.raises(meta_client.MetaError):
        meta_client.segment(PHOTO, "glasses")
