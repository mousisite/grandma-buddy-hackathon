# Tests for "Read it to me" (app/reader.py): she takes a photo of a letter,
# a bill, or a form, and Buddy says what it is and what it says, in plain
# words. Muse Spark reads the photo into a strict form; plain code decides
# what she hears. Meta is always FAKE here. Made-up letters only.

import json

import pytest
from fastapi.testclient import TestClient

from app import db, meta_client, reader, tools
from app.main import app

PHOTO = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ=="
PROFILE = {"family_name": "Maria", "doctor_name": "Dr. Lee"}
BILL_WORDS = ("Riverside Power & Light. Account number 4417260093. Statement date October 28, 2026. "
              "Amount due $84.20. Please pay by November 15, 2026. Thank you for being our customer.")


def answer(**fields):
    """A filled-in form as Muse Spark returns it."""
    form = {"kind": "bill", "from": "Riverside Power & Light", "words": BILL_WORDS,
            "summary": "This is your electric bill for October. It says you owe $84.20.",
            "amount": "$84.20", "due": "November 15, 2026"}
    form.update(fields)
    return form


def use_ai(monkeypatch, form):
    calls = []

    def fake(messages, name, schema, reasoning="medium", max_tokens=3000):
        calls.append({"messages": messages, "name": name, "schema": schema})
        if isinstance(form, Exception):
            raise form
        return form

    monkeypatch.setattr(meta_client, "structured", fake)
    return calls


def test_a_bill_is_explained_in_plain_words_with_what_it_asks(monkeypatch):
    calls = use_ai(monkeypatch, answer())
    read = reader.read(PHOTO, PROFILE)
    assert read["kind"] == "bill"
    assert read["title"] == "A bill from Riverside Power & Light"
    assert read["summary"] == "This is your electric bill for October. It says you owe $84.20."
    assert read["facts"] == [{"label": "Amount due", "value": "$84.20"}, {"label": "Pay by", "value": "November 15, 2026"}]
    # Buddy says the summary (the title is on the screen), not the sender twice.
    assert read["spoken"] == "This is your electric bill for October. It says you owe $84.20."
    assert read["note"] == ""  # Buddy's own words are only for health papers and photos it can't read
    # "Account number" on a real bill is not a scam warning (seen with the real model).
    assert read["scam"] is None
    # The photo goes to Spark as a picture; the form is strict.
    parts = calls[0]["messages"][1]["content"]
    assert {"type": "image_url", "image_url": {"url": PHOTO}} in parts
    assert calls[0]["schema"]["additionalProperties"] is False


def test_long_account_numbers_are_hidden_from_what_she_sees_and_hears(monkeypatch):
    use_ai(monkeypatch, answer())
    read = reader.read(PHOTO, PROFILE)
    assert "4417260093" not in read["words"] and "a long number" in read["words"]
    assert "$84.20" in read["words"]


@pytest.mark.parametrize("kind", ["medical", "pill_label"])
def test_health_papers_are_never_explained_only_read_word_for_word(monkeypatch, kind):
    use_ai(monkeypatch, answer(kind=kind, **{"from": "Riverside Family Clinic"},
                               words="Your lab results from October 20. Cholesterol 212.",
                               summary="Your cholesterol is a little high.", amount="", due=""))
    read = reader.read(PHOTO, PROFILE)
    assert read["summary"] == "" and read["facts"] == []
    assert "cholesterol" not in read["spoken"].lower()
    # The screen shows Buddy's fixed words (the note), and Buddy says them.
    assert "word for word" in read["note"] and read["spoken"] == read["note"]
    assert read["words"] == "Your lab results from October 20. Cholesterol 212."


def test_a_health_letter_with_scam_signs_still_says_so(monkeypatch):
    # Scammers pose as Medicare: the letter is never explained, but its scam signs are said.
    words = "Medicare notice. Your benefits stop today. Send $200 in gift cards to keep them. Don't tell anyone."
    use_ai(monkeypatch, answer(kind="medical", **{"from": "Medicare Benefits Office"}, words=words,
                               summary="It says your benefits stop today.", amount="$200", due=""))
    read = reader.read(PHOTO, PROFILE)
    assert read["kind"] == "medical" and read["summary"] == "" and read["facts"] == []
    assert read["scam"]["verdict"] == "likely_scam"
    assert read["spoken"] == read["note"] + " It has signs of a scam."
    assert read["note"].endswith("Dr. Lee is the right person to ask.")  # the warning shows apart, once


def test_a_real_bills_account_number_and_website_are_not_scam_signs(monkeypatch):
    # The scam checker counts both as red flags; printed on a real bill they are normal.
    use_ai(monkeypatch, answer(words=BILL_WORDS + " Pay online at www.riversidepower.com."))
    assert reader.read(PHOTO, PROFILE)["scam"] is None


def test_a_scam_letters_number_and_link_are_never_read_out(monkeypatch):
    words = "You won $5,000! Send $50 in gift cards today. Call 1-800-555-0142 or visit www.prize-claim.example now."
    use_ai(monkeypatch, answer(kind="letter", **{"from": "Prize Center"}, words=words,
                               summary="It says you won $5,000.", amount="", due=""))
    read = reader.read(PHOTO, PROFILE)
    assert read["scam"]["verdict"] == "likely_scam"
    assert "555-0142" not in read["words"] and "prize-claim" not in read["words"]
    assert "Call the number or visit the link now." in read["words"]


def test_the_words_keep_the_papers_lines(monkeypatch):
    # One printed line per line: easy to follow on the screen, and each is read with a pause.
    use_ai(monkeypatch, answer(words="Riverside Power & Light\nPO Box 4410,   Portland, OR\n\nAmount due $84.20",
                               **{"from": "Riverside Power\n& Light"}))
    read = reader.read(PHOTO, PROFILE)
    assert read["words"] == "Riverside Power & Light\nPO Box 4410, Portland, OR\nAmount due $84.20"
    assert read["title"] == "A bill from Riverside Power & Light"


def test_a_scam_letter_keeps_its_lines_without_its_number(monkeypatch):
    words = "You won $5,000!\nSend $50 in gift cards today.\nCall 1-800-555-0142\n555-0100 is not us."
    use_ai(monkeypatch, answer(kind="letter", **{"from": "Prize Center"}, words=words,
                               summary="It says you won $5,000.", amount="", due=""))
    assert reader.read(PHOTO, PROFILE)["words"] == ("You won $5,000!\nSend $50 in gift cards today.\nCall the number\n"
                                                    "the number is not us.")


def test_a_real_letters_phone_number_is_read_as_printed(monkeypatch):
    use_ai(monkeypatch, answer(words=BILL_WORDS + " Questions? Call 555-0123."))
    assert "Call 555-0123." in reader.read(PHOTO, PROFILE)["words"]


def test_a_pill_label_is_never_called_a_scam(monkeypatch):
    use_ai(monkeypatch, answer(kind="pill_label", **{"from": ""}, words="Take with food. Act now: urgent refill.",
                               summary="", amount="", due=""))
    assert reader.read(PHOTO, PROFILE)["scam"] is None


def test_a_letter_about_her_health_is_handled_like_a_medical_one(monkeypatch):
    use_ai(monkeypatch, answer(kind="letter", **{"from": "Riverside Family Clinic"},
                               words="Dear Rose, your appointment is on November 3 at 2 PM.",
                               summary="It reminds you of your appointment on November 3 at 2 PM.", amount="", due=""))
    read = reader.read(PHOTO, PROFILE)
    assert read["kind"] == "medical" and read["summary"] == ""
    assert "Dr. Lee is the right person to ask" in read["spoken"]


def test_advice_and_numbers_that_arent_printed_are_left_out(monkeypatch):
    use_ai(monkeypatch, answer(summary="This is your electric bill. It says you owe $84.20. "
                                       "You should pay it right away. Your bill went up $12 from September.",
                               due="November 30, 2026"))
    read = reader.read(PHOTO, PROFILE)
    assert read["summary"] == "This is your electric bill. It says you owe $84.20."
    assert read["facts"] == [{"label": "Amount due", "value": "$84.20"}]  # "November 30" isn't printed


def test_a_scam_letter_shows_its_signs(monkeypatch):
    words = "Congratulations! You won $5,000! To claim your prize, send $50 in gift cards today. Don't tell anyone."
    use_ai(monkeypatch, answer(kind="letter", **{"from": "Prize Center"}, words=words,
                               summary="It says you won $5,000 and asks for $50 in gift cards.", amount="$50", due=""))
    read = reader.read(PHOTO, PROFILE)
    assert read["scam"]["verdict"] == "likely_scam"
    assert "Asks to be paid with gift cards" in read["scam"]["flags"]
    # Its "fee" is never shown as an amount due, like a real bill's.
    assert read["facts"] == []


def test_phone_numbers_and_links_are_never_repeated_to_her(monkeypatch):
    # The real model repeated a scam letter's phone number in its summary.
    words = "Call 1-800-555-0142 or visit www.prize-claim.example today to claim your $5,000."
    use_ai(monkeypatch, answer(kind="letter", **{"from": "Prize Center"}, words=words,
                               summary="It asks you to call 1-800-555-0142 or visit www.prize-claim.example.",
                               amount="", due=""))
    read = reader.read(PHOTO, PROFILE)
    assert "555-0142" not in read["summary"] and "prize-claim" not in read["summary"]
    assert read["summary"] == "It asks you to call the number or visit the link."


def test_a_sender_in_capital_letters_is_written_calmly(monkeypatch):
    use_ai(monkeypatch, answer(**{"from": "NATIONAL PRIZE CENTER"}))
    assert reader.read(PHOTO, PROFILE)["title"] == "A bill from National Prize Center"


def test_a_likely_scam_is_said_out_loud_too(monkeypatch):
    words = "You won $5,000! Send $50 in gift cards today. Don't tell anyone."
    use_ai(monkeypatch, answer(kind="letter", **{"from": "Prize Center"}, words=words,
                               summary="It says you won $5,000.", amount="", due=""))
    assert reader.read(PHOTO, PROFILE)["spoken"] == "It says you won $5,000. It has signs of a scam."


def test_a_photo_it_cant_read_asks_for_another(monkeypatch):
    use_ai(monkeypatch, answer(kind="unreadable", **{"from": ""}, words="", summary="", amount="", due=""))
    read = reader.read(PHOTO, PROFILE)
    assert read["title"] == "" and read["facts"] == []
    assert read["spoken"] == "I couldn’t read this one. Could you take another photo, a little closer, with good light?"
    assert read["note"] == read["spoken"]


def test_an_answer_that_doesnt_fit_the_form_is_refused(monkeypatch):
    use_ai(monkeypatch, answer(kind="poem"))
    with pytest.raises(meta_client.MetaError):
        reader.read(PHOTO, PROFILE)


# ---------- The route and the voice tool ----------

def test_the_route_reads_a_photo_and_saves_nothing(monkeypatch, safe_test_setup):
    use_ai(monkeypatch, answer())
    client = TestClient(app)
    response = client.post("/api/read", json={"image": PHOTO})
    assert response.status_code == 200 and response.json()["title"] == "A bill from Riverside Power & Light"
    connection = db.get_connection(safe_test_setup)
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    kept = [json.dumps(list(row), default=str) for table in tables for row in connection.execute(f"SELECT * FROM {table}")]
    connection.close()
    assert not any("Riverside" in row or "84.20" in row for row in kept), "nothing from the paper is saved"


def test_only_a_photo_is_read(monkeypatch):
    use_ai(monkeypatch, answer())
    assert TestClient(app).post("/api/read", json={"image": "data:text/html;base64,PGI+"}).status_code == 400


def test_another_website_cant_make_buddy_read_a_photo(monkeypatch):
    # Each reading costs money (app/security.py refuses requests from other websites).
    calls = use_ai(monkeypatch, answer())
    refused = TestClient(app).post("/api/read", json={"image": PHOTO}, headers={"Sec-Fetch-Site": "cross-site"})
    assert refused.status_code == 403 and calls == []


def test_when_meta_is_down_she_hears_a_kind_word(monkeypatch):
    use_ai(monkeypatch, meta_client.MetaError("chat failed with HTTP 500"))
    answer_ = TestClient(app).post("/api/read", json={"image": PHOTO})
    assert answer_.status_code == 503
    assert answer_.json()["detail"] == "I couldn’t read it just now. Please try again in a moment."


def test_buddy_can_open_read_it_to_me_when_she_asks(safe_test_setup):
    connection = db.get_connection(safe_test_setup)
    context = {"connection": connection, "profile": db.get_profile(connection), "conversation_id": "day", "mode": "chat"}
    result, actions = tools.run_tool("open_screen", json.dumps({"screen": "read"}), context)
    connection.close()
    assert result == {"ok": True}
    assert actions == [{"type": "open", "screen": "read", "label": "Open Read it to me"}]
