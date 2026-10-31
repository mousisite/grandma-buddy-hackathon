# Tests for the landing page (/about), Privacy, and Terms (docs/SPEC.md
# feature 17): plain pages for the family member who sets Buddy up. They
# are served like Home, say only true things about the app, and never ask
# for a card number (payments come later, in Stripe's test mode).

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import how
from app.config import get_settings
from app.main import STATIC_DIR, app

PAGES = {"/about": "about.html", "/privacy": "privacy.html", "/terms": "terms.html"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("path", sorted(PAGES))
def test_the_pages_are_served_like_home(client, path):
    page = client.get(path)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "<title>" in page.text and "Grandma Buddy" in page.text
    # Always checked for a newer version, like the app's own page.
    assert page.headers["cache-control"] == "no-cache"


def test_the_landing_names_the_meta_models_the_app_really_uses(client):
    # The names come from the same settings as the Help screen, so the page
    # can't drift from what runs.
    settings = get_settings()
    page = client.get("/about").text
    for setting, _ in how.MODELS:
        assert how.model_name(getattr(settings, setting)) in page


def test_the_landing_keeps_the_safety_promise_and_asks_for_no_card(client):
    page = client.get("/about").text
    assert "never gives medical advice" in page
    assert "911" in page
    # Pricing shows plans, but this build takes no payment: no form fields at all.
    assert "$9" in page and "test mode" in page
    assert "<input" not in page and "<form" not in page


def test_the_landing_links_to_the_app_privacy_and_terms(client):
    page = client.get("/about").text
    assert 'href="/"' in page and 'href="/privacy"' in page and 'href="/terms"' in page


def test_every_picture_on_the_landing_is_in_the_repository(client):
    # The phone shots are made by scripts/landing_shots.py from the demo week
    # (made-up data) and committed, so the page never shows a broken picture.
    page = client.get("/about").text
    pictures = re.findall(r'src="/static/([^"]+\.(?:png|webp|jpg))"', page)
    assert pictures, "the landing should show the app"
    for picture in pictures:
        assert (STATIC_DIR / picture).exists(), picture
    # Every picture says what it shows (screen readers, and a slow connection).
    assert page.count("<img") == page.count('alt="')


def test_privacy_says_where_her_data_lives_and_what_meta_gets(client):
    page = client.get("/privacy").text
    assert "on her own computer" in page or "on her computer" in page
    assert "standard" in page and "train" in page
    assert "Send" in page  # the family update goes only when she presses Send


def test_terms_say_what_buddy_is_not(client):
    page = client.get("/terms").text
    assert "not medical advice" in page or "never gives medical advice" in page
    assert "911" in page


def test_the_help_screen_links_to_the_pages():
    index = (Path(STATIC_DIR) / "index.html").read_text(encoding="utf-8")
    assert 'href="/about"' in index and 'href="/privacy"' in index and 'href="/terms"' in index
