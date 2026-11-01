# Tests for the scam checker's web lookup (docs/SPEC.md feature 7, docs/
# SAFETY.md section 8): plain code pulls the phone numbers and web addresses
# out of the message, Meta's web search (through Muse Spark) says whether
# they are reported as scams, and plain code turns that into fixed words:
# the lookup can make the verdict stronger, never weaker, and the number or
# address is never repeated to her. Meta is always FAKE here.

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import briefing, db, meta_client, reminders, scam
from app.main import app
from tests.test_briefing import Searches
from tests.test_scam import FakeAI, use_ai

NOW = datetime(2026, 10, 31, 15, 0)
WITH_NUMBER = "Hi, this is Dana from the bank. Please call (555) 010-0199 to confirm your details."
WITH_SITE = "USPS: your package is on hold, pay $1.99 at usps-redelivery-help.com"
PLAIN = "Hi Rose, it's Maria. I'll bring the children by on Sunday afternoon."


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(reminders, "current_time", lambda: NOW)
    test_client = TestClient(app)
    test_client.put("/api/profile", json={"preferred_name": "Rose", "family_name": "Maria", "family_phone": "555-0100"})
    return test_client


def check(client, text):
    return client.post("/api/scam-check", json={"text": text, "kind": "text"}).json()


# ---------- Plain code finds what to look up ----------

@pytest.mark.parametrize("text, numbers, sites", [
    (WITH_NUMBER, ["(555) 010-0199"], []),
    (WITH_SITE, [], ["usps-redelivery-help.com"]),
    ("Call 1-800-555-0133 or visit https://www.example-prizes.net/claim now", ["1-800-555-0133"], ["example-prizes.net"]),
    (PLAIN, [], []),
    ("Your code is 482913, it expires in 10 minutes", [], []),  # a code, not a phone number
])
def test_the_numbers_and_sites_in_a_message(text, numbers, sites):
    assert scam.contacts(text) == {"numbers": numbers, "sites": sites}


# ---------- The lookup ----------

def test_a_number_reported_as_a_scam_makes_it_a_likely_scam_without_repeating_the_number(client, monkeypatch):
    use_ai(monkeypatch, verdict="suspicious", red_flags=["Says your account is suspended"], explanation="Something is off here.")
    searches = Searches(monkeypatch, text="REPORTED. This number appears on several scam-report sites as a robocall.",
                        sources=[{"title": "Report", "url": "https://www.bbb.org/scamtracker/1"},
                                 {"title": "Report", "url": "https://whocalled.example.net/5550100199"}])
    body = check(client, WITH_NUMBER)
    question, instructions, town = searches.calls[0]
    assert "(555) 010-0199" in question and town == "", "the number is looked up, with no town attached"
    assert "REPORTED" in instructions and "never repeat" in instructions.lower()
    assert body["verdict"] == "likely_scam", "a report online makes the verdict stronger"
    assert body["red_flags"][0] == "The phone number in it has been reported as a scam online."
    assert body["lookup"] == {"reported": True, "words": "The phone number in it has been reported as a scam online.",
                              "sites": ["bbb.org", "whocalled.example.net"]}
    # The AI's lookup words and the number itself never reach the screen.
    shown = str(body)
    assert "010-0199" not in shown and "5550100199" not in shown and "robocall" not in shown
    assert body["explanation"] == scam.RULES_EXPLANATION["likely_scam"], "a raised verdict gets the fixed words"


def test_nothing_found_online_leaves_the_verdict_alone_and_says_it_doesnt_make_it_safe(client, monkeypatch):
    use_ai(monkeypatch, verdict="suspicious", red_flags=["Has a link to click"], explanation="Something is off here.")
    Searches(monkeypatch, text="UNKNOWN. I found no reports about this address.",
             sources=[{"title": "Search", "url": "https://www.scamadviser.com/check"}])
    # One link alone: the rules say suspicious too, so the AI's words stay.
    body = check(client, "Hi Rose, the photos from the reunion are ready at photos-share-family.com, love Dana")
    assert body["verdict"] == "suspicious"
    assert body["explanation"] == "Something is off here."
    assert body["lookup"] == {"reported": False, "sites": ["scamadviser.com"],
                              "words": "Nothing was found online about the website in it. That doesn’t make it safe."}
    assert body["red_flags"] == ["Has a link to click"]


def test_a_real_company_online_never_lowers_the_verdict(client, monkeypatch):
    # The rules say likely scam (payment and a held package); the web says the site is real.
    use_ai(monkeypatch, verdict="likely_scam", red_flags=["Asks you to pay a fee"], explanation="This has warning signs.")
    Searches(monkeypatch, text="CLEAR. The address belongs to the postal service's real site.",
             sources=[{"title": "USPS", "url": "https://www.usps.com"}])
    body = check(client, WITH_SITE)
    assert body["verdict"] == "likely_scam"
    assert body["lookup"]["reported"] is False
    assert body["lookup"]["words"] == "Nothing was found online about the website in it. That doesn’t make it safe."


def test_the_sites_named_never_include_the_suspicious_address_itself(client, monkeypatch):
    use_ai(monkeypatch, verdict="suspicious", red_flags=["Has a link to click"], explanation="Something is off here.")
    Searches(monkeypatch, text="REPORTED. The site is flagged as a phishing page.",
             sources=[{"title": "The site", "url": "https://www.usps-redelivery-help.com/track"},
                      {"title": "Lookup", "url": "https://5550100199.whocalled.example.net/"},
                      {"title": "Report", "url": "https://www.scamadviser.com/check"}])
    body = check(client, WITH_SITE + " or call (555) 010-0199")
    assert body["lookup"]["sites"] == ["scamadviser.com"], "the looked-up address, and a host with the number, are never shown"
    assert "usps-redelivery" not in str(body) and "0199" not in str(body)


def test_a_message_with_nothing_to_look_up_is_not_searched(client, monkeypatch):
    use_ai(monkeypatch, verdict="looks_safe", red_flags=[], explanation="This looks like an ordinary message.")
    searches = Searches(monkeypatch)
    body = check(client, PLAIN)
    assert searches.calls == [] and body["lookup"] is None


def test_a_photo_is_never_looked_up(client, monkeypatch):
    use_ai(monkeypatch, verdict="likely_scam", red_flags=["Asks for gift cards"])
    searches = Searches(monkeypatch)
    picture = "data:image/jpeg;base64," + "QUJD" * 4
    body = client.post("/api/scam-check", json={"image": picture, "kind": "photo"}).json()
    assert searches.calls == [] and body["lookup"] is None


def test_when_the_web_search_fails_the_check_still_answers(client, monkeypatch):
    use_ai(monkeypatch, verdict="suspicious", red_flags=["Threatens arrest or trouble"], explanation="Something is off here.")

    def no_internet(question, instructions, town):
        raise meta_client.MetaError("Web search failed: APIConnectionError")

    monkeypatch.setattr(meta_client, "search", no_internet)
    body = check(client, WITH_NUMBER)
    assert body["verdict"] == "suspicious"  # the AI's verdict, with no web to make it stronger
    assert body["lookup"] is None


def test_an_answer_without_a_real_search_or_without_the_word_is_not_trusted(client, monkeypatch):
    use_ai(monkeypatch, verdict="suspicious", red_flags=["Threatens arrest or trouble"], explanation="Something is off here.")
    Searches(monkeypatch, text="REPORTED. Scammers use it.", searched=False)
    assert check(client, WITH_NUMBER)["lookup"] is None
    Searches(monkeypatch, text="It is probably a scam number.")  # no first word: plain code can't read it
    assert check(client, WITH_NUMBER)["lookup"] is None


def test_the_lookup_counts_toward_the_days_web_searches(client, monkeypatch, safe_test_setup):
    use_ai(monkeypatch, verdict="suspicious", red_flags=["Threatens arrest or trouble"], explanation="Something is off here.")
    searches = Searches(monkeypatch, text="UNKNOWN. Nothing found.")
    connection = db.get_connection(safe_test_setup)
    connection.execute("INSERT INTO web_searches (day, count) VALUES (?, ?)", (NOW.date().isoformat(), briefing.MAX_SEARCHES_A_DAY - 1))
    connection.commit()
    assert check(client, WITH_NUMBER)["lookup"] is not None
    assert briefing.searches_today(connection, NOW) == briefing.MAX_SEARCHES_A_DAY
    assert check(client, WITH_NUMBER)["lookup"] is None, "over the day's budget: no search"
    assert len(searches.calls) == 1
    connection.close()


def test_search_without_a_town_sends_no_location(monkeypatch):
    from tests.test_briefing import FakeResponses, N, cited

    fake = FakeResponses(cited("UNKNOWN. Nothing found.", "https://www.bbb.org/scamtracker"))
    monkeypatch.setattr(meta_client, "_client", lambda: N(responses=fake))
    meta_client.search("Is this number reported as a scam?", "Answer with one word first.", "")
    assert fake.requests[0]["tools"] == [{"type": "web_search", "search_context_size": "low"}]
