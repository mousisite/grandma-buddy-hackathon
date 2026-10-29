# scripts/check_scam.py
# A hand-run check of "Check a message" with the REAL AI.
#
# Sends the scam test messages from docs/SAFETY.md section 10 through the
# real /api/scam-check (rules, structured output, fixed "what to do"), plus
# one PHOTO of the gift-card text (drawn into a picture with Playwright), and
# checks the verdicts:
#   3 scams        -> likely_scam
#   Dr. Lee's text -> looks_safe or suspicious
#   the photo      -> likely_scam (proves photos reach the AI)
#
# Run it by hand only (about 5 to 10 real calls, under a cent):
#   .venv\Scripts\python scripts\check_scam.py
# It uses a throwaway database, so it never touches her real data.

import base64
import os
import sys
import tempfile
from pathlib import Path

# A throwaway database, set BEFORE the app reads its settings.
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "check_scam.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app.main import app  # noqa: E402

GRANDSON = "Grandma it's me, I'm in jail, send $2,000 in gift cards and don't tell mom"
MESSAGES = [
    (GRANDSON, {"likely_scam"}),
    ("USPS: your package is on hold, pay $1.99 at usps-redelivery-help.com", {"likely_scam"}),
    ("Your Social Security number is suspended. Call now to avoid arrest.", {"likely_scam"}),
    ("Hi Rose, Dr. Lee's office confirming your appointment Thursday at 2 PM.", {"looks_safe", "suspicious"}),
]


def photo_of(text: str) -> str:
    """A picture of a phone text message, as a data URL (like the page sends)."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 600, "height": 260})
        page.set_content(
            "<body style='margin:0;background:#eee;font:28px sans-serif'>"
            "<p style='margin:24px;padding:20px;border-radius:24px;background:#fff'>" + text + "</p></body>"
        )
        picture = page.screenshot(type="jpeg", quality=85)
        browser.close()
    return "data:image/jpeg;base64," + base64.b64encode(picture).decode()


def show(label: str, body: dict) -> None:
    print(f"{label}")
    print(f"  {body['title']}: {body['explanation']}")
    print(f"  Warning signs: {body['red_flags']}")
    print(f"  Buttons: {[a['label'] for a in body['actions']]}\n")


def main() -> int:
    problems = []
    with TestClient(app) as client:  # "with" runs the app's startup (creates the tables)
        client.put("/api/profile", json={"preferred_name": "Rose", "family_name": "Maria", "family_phone": "555-0100"})
        for text, expected in MESSAGES:
            body = client.post("/api/scam-check", json={"text": text, "kind": "text"}).json()
            show(f"Message: {text}", body)
            if body["verdict"] not in expected:
                problems.append(f"{text!r} got {body['verdict']}, expected {' or '.join(sorted(expected))}")

        body = client.post("/api/scam-check", json={"image": photo_of(GRANDSON), "kind": "photo"}).json()
        show("Photo of the gift-card text", body)
        if body["verdict"] != "likely_scam":
            problems.append(f"The photo got {body['verdict']}, expected likely_scam")
        if body["explanation"].startswith("I'm not sure"):
            problems.append("The photo didn't reach the AI (it fell back to the fixed words).")

    for problem in problems:
        print("PROBLEM:", problem)
    print("Scam check:", "PROBLEMS FOUND" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
