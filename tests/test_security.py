# Tests for requests that don't come from Grandma Buddy's own page.
#
# Buddy runs on her computer, and her browser can also have other websites
# open. Without these checks, any website could quietly send requests to
# http://localhost:8000: add a doctor question, paint a Memory book page
# (which costs money), or ask for her doctor notes (an AI call). So:
# - every /api request from another website (or another port on this
#   computer) is refused, using the headers browsers add to each request;
# - a request for any other host name than this computer's is refused
#   ("DNS rebinding": a website's name pointed at this computer).

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

QUESTION = {"question": "Can I take my pills with coffee?"}


@pytest.fixture
def client():
    return TestClient(app)


def questions(safe_test_setup):
    connection = db.get_connection(safe_test_setup)
    count = connection.execute("SELECT COUNT(*) FROM doctor_questions").fetchone()[0]
    connection.close()
    return count


@pytest.mark.parametrize("headers", [
    {"Sec-Fetch-Site": "cross-site", "Origin": "https://example.com"},  # another website
    {"Sec-Fetch-Site": "same-site", "Origin": "http://localhost:3000"},  # another port on this computer
    {"Origin": "https://example.com"},  # an older browser: no Sec-Fetch-Site
    {"Origin": "null"},  # a sandboxed page or a file
])
def test_a_change_from_another_website_is_refused_and_nothing_is_saved(client, safe_test_setup, headers):
    refused = client.post("/api/doctor-questions", json=QUESTION, headers=headers)
    assert refused.status_code == 403
    assert questions(safe_test_setup) == 0


def test_a_page_from_another_website_cant_make_buddy_spend_money_with_a_get(client):
    # <img src="http://localhost:8000/api/doctor-notes?days=30"> on another site.
    refused = client.get("/api/doctor-notes?days=7", headers={"Sec-Fetch-Site": "cross-site"})
    assert refused.status_code == 403


def test_buddys_own_page_works(client, safe_test_setup):
    own = {"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}
    assert client.post("/api/doctor-questions", json=QUESTION, headers=own).status_code == 200
    assert questions(safe_test_setup) == 1


def test_typing_an_address_in_the_browser_still_works(client):
    assert client.get("/api/ping", headers={"Sec-Fetch-Site": "none"}).status_code == 200


def test_a_link_from_another_website_can_still_open_buddy(client):
    # Only /api is guarded: a link to the app itself is fine.
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


@pytest.mark.parametrize("host", ["example.com", "localhost.example.com", "192.168.1.20"])
def test_another_host_name_is_refused(client, host):
    refused = client.get("/api/ping", headers={"Host": host})
    assert refused.status_code == 400


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000"])
def test_this_computers_names_are_allowed(client, host):
    assert client.get("/api/ping", headers={"Host": host}).status_code == 200
