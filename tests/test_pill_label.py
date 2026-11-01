# Tests for a pill from a photo of its bottle (docs/SPEC.md feature 4,
# docs/SAFETY.md section 5): Muse Spark reads the name and the label as
# printed into a strict form; plain code trims them to the form's limits;
# the family member checks each one before it is saved, and types the
# times. Nothing is stored by the reading. Meta is always FAKE here.

import pytest
from fastapi.testclient import TestClient

from app import db, labels, meta_client
from app.main import app

PHOTO = "data:image/jpeg;base64," + "QUJD" * 8


def use_ai(monkeypatch, form):
    calls = []

    def fake(messages, name, schema, reasoning="medium", max_tokens=3000):
        calls.append({"messages": messages, "name": name, "schema": schema, "reasoning": reasoning})
        if isinstance(form, Exception):
            raise form
        return form

    monkeypatch.setattr(meta_client, "structured", fake)
    return calls


def label(readable=True, name="Lisinopril", words="10 mg tablet, take 1 by mouth daily"):
    return {"readable": readable, "name": name, "label": words}


@pytest.fixture
def client():
    return TestClient(app)


def test_the_name_and_the_label_are_read_as_printed(monkeypatch):
    calls = use_ai(monkeypatch, label())
    assert labels.read_label(PHOTO) == {"name": "Lisinopril", "label": "10 mg tablet, take 1 by mouth daily"}
    call = calls[0]
    assert call["name"] == "pill_label" and call["reasoning"] == "low"
    assert call["schema"]["required"] == ["readable", "name", "label"] and call["schema"]["additionalProperties"] is False
    photo = call["messages"][1]["content"][1]
    assert photo == {"type": "image_url", "image_url": {"url": PHOTO}}, "the photo goes to Spark as an image"
    assert "exactly as printed" in call["messages"][0]["content"]


def test_an_unreadable_photo_or_an_empty_answer_is_refused(monkeypatch):
    use_ai(monkeypatch, label(readable=False, name="", words=""))
    with pytest.raises(ValueError, match="couldn’t read that label"):
        labels.read_label(PHOTO)
    use_ai(monkeypatch, label(name="   ", words="Take 1 daily"))
    with pytest.raises(ValueError):
        labels.read_label(PHOTO)


def test_long_or_messy_words_are_trimmed_to_what_the_form_takes(monkeypatch):
    use_ai(monkeypatch, label(name="  Metformin \n Hydrochloride  ", words=("Take 1 tablet " * 30).strip()))
    read = labels.read_label(PHOTO)
    assert read["name"] == "Metformin Hydrochloride"
    assert len(read["label"]) <= labels.MAX_LABEL and read["label"].startswith("Take 1 tablet")
    assert not read["label"].endswith(" ")


def test_the_route_fills_the_form_and_stores_nothing(client, monkeypatch, safe_test_setup):
    use_ai(monkeypatch, label())
    answer = client.post("/api/meds/label", json={"image": PHOTO})
    assert answer.status_code == 200
    assert answer.json() == {"name": "Lisinopril", "label": "10 mg tablet, take 1 by mouth daily",
                             "note": "From the photo. Please check both against the bottle before saving."}
    connection = db.get_connection(safe_test_setup)
    assert connection.execute("SELECT COUNT(*) FROM medications").fetchone()[0] == 0, "reading never saves a pill"
    connection.close()


@pytest.mark.parametrize("image", ["", "not a photo", "data:text/plain;base64,QUJD", "data:image/jpeg;base64," + "A" * 6_000_001],
                         ids=["empty", "not a photo", "not a picture", "too big"])
def test_a_bad_picture_is_refused_kindly(client, monkeypatch, image):
    calls = use_ai(monkeypatch, label())
    answer = client.post("/api/meds/label", json={"image": image})
    assert answer.status_code == 400 and "photo" in answer.json()["detail"]
    assert calls == []


def test_when_spark_cannot_read_it_or_is_down_the_family_can_still_type_it(client, monkeypatch):
    use_ai(monkeypatch, label(readable=False, name="", words=""))
    answer = client.post("/api/meds/label", json={"image": PHOTO})
    assert answer.status_code == 400 and answer.json()["detail"] == labels.COULDNT_READ
    use_ai(monkeypatch, meta_client.MetaError("chat failed with HTTP 503"))
    answer = client.post("/api/meds/label", json={"image": PHOTO})
    assert answer.status_code == 503 and "type it in" in answer.json()["detail"]
