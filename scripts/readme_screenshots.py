# scripts/readme_screenshots.py
# The README's screenshots: docs/screenshots/*.png at phone width (390px),
# plus Home at desktop width, from a FRESH copy of the demo week on a
# throwaway database. The app's own data is never touched, so nothing real
# can end up in a picture.
#
# The three Memory book pictures are painted with Muse Image (about 3 cents).
# Find my things, Read it to me, and Check a message show the real answers
# scripts/check_photos.py saved (test-output/photo-check.json), and the voice
# screen shows a real reply from scripts/check_voice.py (test-output/
# voice-check-stream.json): no other AI calls are made.
#   .venv\Scripts\python scripts\readme_screenshots.py
#   .venv\Scripts\python scripts\readme_screenshots.py --no-paint   (no Memory book pictures, free)
#   .venv\Scripts\python scripts\readme_screenshots.py --no-paint --only home-phone,home-desktop   (just those)

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "screenshots"
TEST = ROOT / "test-output"
PORT = 8008
folder = Path(tempfile.mkdtemp(prefix="buddy-readme-"))
os.environ["DATABASE_PATH"] = str(folder / "readme.db")  # before the app reads its settings

from app import db, demo, guard, memories, tools  # noqa: E402
from app.config import get_settings  # noqa: E402
from scripts.browser_checks.home import wait_for_screen  # noqa: E402
from scripts.check_photos import DESK, LETTER_TEXT, PAPERS  # noqa: E402

HEADACHE = "Should I take something for my headache?"
CHEST = "My chest hurts and I can't breathe"


def seed(paint: bool) -> dict:
    """The demo week, ending today, on the throwaway database; the Memory book
    pictures painted (or not). Returns her profile."""
    path = get_settings().database_path
    db.init_db(path)
    connection = db.get_connection(path)
    pages = demo.seed(connection, datetime.now())
    connection.commit()
    profile = dict(db.get_profile(connection))
    connection.close()
    # Home's weather row: a made-up forecast for her town (this server has no key).
    connection = sqlite3.connect(path)
    connection.execute("INSERT OR REPLACE INTO briefings (topic, city, text, sources, made_at) VALUES ('weather', ?, ?, ?, ?)",
                       (profile["city"], "Cloudy today, with a high of 48 and a low of 41.", '["Open-Meteo.com"]',
                        datetime.now().isoformat(timespec="seconds")))
    connection.commit()
    connection.close()
    if paint:
        print(f"Painting {len(pages)} Memory book pictures with Muse Image (about {len(pages)} cents)…")
        for page in pages:
            connection = db.get_connection(path)
            memories.paint_again(connection, page)
            connection.commit()
            connection.close()
            memories.make_page(page)
    return profile


def saved(name: str) -> dict | None:
    answers = TEST / "photo-check.json"
    if not answers.exists():
        return None
    return json.loads(answers.read_text(encoding="utf-8")).get(name)


def real_no_advice_reply() -> str:
    """What Buddy really said to the headache question in scripts/check_voice.py,
    or the fixed no-advice reply if that hasn't been run."""
    results = TEST / "voice-check-stream.json"
    if results.exists():
        for row in json.loads(results.read_text(encoding="utf-8")):
            if row["clip"] == "headache" and row.get("reply"):
                return row["reply"]
    return guard.NO_ADVICE_REPLY


def start_server() -> subprocess.Popen:
    env = dict(os.environ, MODEL_API_KEY="", STRIPE_SECRET_KEY="")  # no AI calls; demo mode on the family page
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], cwd=ROOT,
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/api/ping", timeout=2)
            return server
        except OSError:
            time.sleep(0.5)
    raise SystemExit("The screenshot server didn't start.")


def quiet(page) -> None:
    """No sound, and no pill card over the screen (a pill may be due now)."""
    page.evaluate("window.speak = function () {}; window.warmVoice = function () {}; 0")
    page.add_style_tag(content=".pill-banner { display: none !important; }")


def replay(answer: dict):
    return lambda route: route.fulfill(json=answer)


ONLY: set = set()  # --only: the screenshots to take; empty means all


def shoot(page, name: str) -> str:
    if ONLY and name not in ONLY:
        return ""
    page.wait_for_timeout(900)  # the orb and the cards have settled
    page.screenshot(path=str(OUT / f"{name}.png"))
    return f"{name}.png"


def open_screen(page, screen: str) -> None:
    page.evaluate("document.querySelectorAll('dialog[open]').forEach(d => d.close())")  # a safety screen stays until closed
    page.goto(f"http://localhost:{PORT}/#/{screen}", wait_until="networkidle")
    wait_for_screen(page, screen.split("/")[0] or "today")  # "memory/1" is the memory screen
    quiet(page)


def phone_shots(browser, profile: dict) -> list[str]:
    page = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block").new_page()
    names = []

    open_screen(page, "")
    page.wait_for_selector("#today-weather:not([hidden])")
    names.append(shoot(page, "home-phone"))
    # The Today list up close: the weather line with where it comes from, the check-in, her pills.
    if not ONLY or "today-list" in ONLY:
        page.add_style_tag(content=".tabbar { display: none !important; }")
        page.locator(".today").first.screenshot(path=str(OUT / "today-list.png"))
        names.append("today-list.png")

    # Voice mode: the real no-advice reply to the headache question, with its buttons.
    open_screen(page, "talk")
    actions = tools.call_doctor(profile) + tools.call_family(profile) + [tools.add_question_action(HEADACHE)]
    page.evaluate("([her, reply, actions]) => { newExchange(her); showReply(reply); showActions(actions); }",
                  [HEADACHE, real_no_advice_reply(), actions])
    page.wait_for_timeout(1500)  # the words have finished appearing
    names.append(shoot(page, "talk-no-advice"))

    # The safety net: her words through the real /api/chat (no AI involved).
    open_screen(page, "talk")
    page.evaluate("(words) => { newExchange(words); return askBuddy(words); }", CHEST)
    page.wait_for_selector("#safety-screen[open][data-kind='emergency']")
    names.append(shoot(page, "safety-emergency"))
    page.click("#safety-close")
    page.wait_for_function("!document.getElementById('safety-screen').open")

    open_screen(page, "pills")
    page.wait_for_selector("#pills-today .check-row")
    names.append(shoot(page, "pills"))

    if saved("find-glasses"):
        open_screen(page, "find")
        page.route("**/api/find", replay(saved("find-glasses")))
        page.fill("#find-thing", "my glasses")
        page.set_input_files("#find-camera", str(DESK))
        page.wait_for_selector("#find-after:not([hidden])")
        page.wait_for_timeout(1300)  # the halo has finished drawing
        names.append(shoot(page, "find"))

    if saved("read-bill"):
        open_screen(page, "read")
        page.route("**/api/read", replay(saved("read-bill")))
        page.set_input_files("#read-library", str(PAPERS / "bill.png"))
        page.wait_for_selector("#read-result:not([hidden])")
        names.append(shoot(page, "read"))

    if saved("scam-text"):
        open_screen(page, "scam")
        page.route("**/api/scam-check", replay(saved("scam-text")))
        page.fill("#scam-text", LETTER_TEXT)
        page.click("#scam-check")
        page.wait_for_selector("#scam-result:not([hidden])")
        names.append(shoot(page, "scam"))

    open_screen(page, "memories")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")  # pictures load as she scrolls
    page.wait_for_function("[...document.querySelectorAll('.memory-img')].every(i => i.classList.contains('shown'))")
    page.evaluate("window.scrollTo(0, 0)")
    names.append(shoot(page, "memories"))

    open_screen(page, "memory/1")
    page.wait_for_function("[...document.querySelectorAll('.memory-img')].every(i => i.classList.contains('shown'))")
    names.append(shoot(page, "memory-page"))

    open_screen(page, "family")
    page.wait_for_function("!!document.querySelector('#postcard:not([hidden]) .memory-img.shown') || "
                           "document.getElementById('postcard-note').textContent !== ''")
    names.append(shoot(page, "family-screen"))

    open_screen(page, "notes")
    page.wait_for_selector("#notes-doc .doc-questions")
    names.append(shoot(page, "doctor-notes"))

    # Maria's page, with the demo account.
    page.goto(f"http://localhost:{PORT}/family", wait_until="networkidle")
    page.click("#family-demo-signin")
    page.wait_for_selector("#family-day:not([hidden])")
    page.wait_for_function("document.getElementById('pills').textContent.trim() !== ''")
    names.append(shoot(page, "family-page"))
    page.close()
    return names


def desktop_shot(browser) -> list[str]:
    page = browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="block").new_page()
    open_screen(page, "")
    page.wait_for_selector("#today-weather:not([hidden])")
    name = shoot(page, "home-desktop")
    page.close()
    return [name]


def main(args: list[str]) -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    if "--only" in args:
        ONLY.update(args[args.index("--only") + 1].split(","))
    profile = seed(paint="--no-paint" not in args and bool(get_settings().model_api_key))
    server = start_server()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            names = [name for name in phone_shots(browser, profile) + desktop_shot(browser) if name]
            browser.close()
    finally:
        server.terminate()
    sizes = sum((OUT / name).stat().st_size for name in names) // 1024
    print(f"{len(names)} screenshots in docs/screenshots ({sizes} KB): " + ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
