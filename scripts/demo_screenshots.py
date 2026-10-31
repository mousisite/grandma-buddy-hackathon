# scripts/demo_screenshots.py
# Screenshots of every screen with the demo week loaded, at phone (390px)
# and desktop (1440px) width, for checking the app before the demo video.
#
# It never touches her real data: it copies the app's database (and the
# Memory book pictures) into test-output/demo-screens/ and starts its own
# server on that copy, with no API key, so no AI is called and nothing is
# spent. The welcome is shown on a second, empty database (it only opens
# while no name is saved).
#
# Run it by hand after scripts/seed_demo.py:
#   .venv\Scripts\python scripts\demo_screenshots.py
# Screenshots go to test-output/demo-<screen>-<width>.png.

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from scripts.browser_checks.home import (  # noqa: E402
    LAYOUT_PROBLEMS_JS, ONE_LINE_JS, READ_BILL, READ_CLINIC, READ_SCAM, read_paper, wait_for_screen,
)
from scripts.check_read import FOLDER as PAPERS, photos  # noqa: E402

OUT = ROOT / "test-output"
FOLDER = OUT / "demo-screens"
PORT, WELCOME_PORT = 8006, 8007
SIZES = [(390, 844), (1440, 900)]
# Each screen, by its address. memory/1 is the first Memory book page.
SCREENS = ["", "talk", "diary", "pills", "notes", "family", "memories", "memory/1", "scam", "find", "read", "settings",
           "help"]


def copy_the_app_data() -> Path:
    """A copy of the app's database (SQLite's own backup, safe while the app
    runs) and its Memory book pictures."""
    shutil.rmtree(FOLDER, ignore_errors=True)
    FOLDER.mkdir(parents=True)
    source_path = Path(get_settings().database_path)
    source = sqlite3.connect(source_path)
    copy = sqlite3.connect(FOLDER / "demo.db")
    source.backup(copy)
    copy.close()
    source.close()
    pictures = source_path.parent / "memories"
    if pictures.exists():
        shutil.copytree(pictures, FOLDER / "memories")
    return FOLDER / "demo.db"


def add_made_up_weather(database: Path) -> None:
    """Home's weather row needs a look-up on the web, and this server has no
    key: a made-up forecast for her town goes into the COPY (made now, so it
    is fresh for 3 hours). Her real database is never touched."""
    connection = sqlite3.connect(database)
    connection.execute("UPDATE profile SET city = 'Portland, Oregon' WHERE city = ''")
    town = connection.execute("SELECT city FROM profile WHERE id = 1").fetchone()[0]
    connection.execute(
        "INSERT OR REPLACE INTO briefings (topic, city, text, sources, made_at) VALUES ('weather', ?, ?, ?, ?)",
        (town, "Sunny, with a high of 62 and a low of 48.", '["weather.gov"]',
         datetime.now().isoformat(timespec="seconds")),
    )
    connection.commit()
    connection.close()


def start_server(database: Path, port: int) -> subprocess.Popen:
    env = dict(os.environ, DATABASE_PATH=str(database), MODEL_API_KEY="")  # no AI calls
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=ROOT,
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/api/ping", timeout=2)
            return server
        except OSError:
            time.sleep(0.5)
    raise SystemExit("The screenshot server didn't start.")


def no_problems(page, where: str) -> None:
    problems = page.evaluate(LAYOUT_PROBLEMS_JS)
    assert not problems, f"layout problems on {where}: {problems}"
    wrapped = page.evaluate(ONE_LINE_JS, ".find-actions .pill-button, .welcome-actions .pill-button, .pill-banner-actions .pill-button")
    assert not wrapped, f"button words wrap on {where}: {wrapped}"


def screens(browser) -> list[str]:
    saved = []
    for width, height in SIZES:
        page = browser.new_page(viewport={"width": width, "height": height})
        for address in SCREENS:
            name = address.split("/")[0] or "today"
            page.goto(f"http://localhost:{PORT}/#/{address}", wait_until="networkidle")
            wait_for_screen(page, name)
            if name == "settings":
                page.evaluate("document.getElementById('learned-setup').open = true")
            if name in ("memories", "memory"):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")  # pictures load as she scrolls
                page.wait_for_function("[...document.querySelectorAll('.memory-img')].every(i => i.classList.contains('shown'))")
                page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(1200)  # the orb and the cards have settled
            no_problems(page, f"{address or 'home'} at {width}px")
            path = OUT / f"demo-{address.replace('/', '-') or 'home'}-{width}.png"
            page.screenshot(path=str(path), full_page=True)
            saved.append(path.name)
        page.close()
    return saved


def close_up(page, selector: str, name: str) -> str:
    """One part of a screen, without the phone's tab bar floating over it."""
    page.add_style_tag(content=".tabbar { display: none !important; }")
    page.locator(selector).first.screenshot(path=str(OUT / name))
    return name


def paper_answer(name: str, stand_in: dict) -> dict:
    """What the real Muse Spark said about a made-up paper (saved by
    scripts/check_read.py), or the browser check's stand-in."""
    saved = PAPERS / f"{name}.json"
    return json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else stand_in


def read_close_ups(page, width: int) -> list[str]:
    """Read it to me: the Home chips, Buddy reading a bill (the orb on the
    photo), and the cards for the bill, the clinic letter, and the scam."""
    saved = []
    page.goto(f"http://localhost:{PORT}/#/", wait_until="networkidle")
    wait_for_screen(page, "today")
    saved.append(close_up(page, ".home .chips", f"demo-read-chips-{width}.png"))
    page.goto(f"http://localhost:{PORT}/#/read", wait_until="networkidle")
    wait_for_screen(page, "read")
    page.add_style_tag(content=".pill-banner { display: none !important; }")  # a pill may be due in the copy
    held = []
    page.route("**/api/read", lambda route: held.append(route))
    page.set_input_files("#read-camera", str(PAPERS / "bill.png"))
    page.wait_for_selector("#read-photo:not([hidden])")
    page.wait_for_function("document.getElementById('read-status').textContent !== ''")
    page.wait_for_timeout(800)  # the orb is thinking
    saved.append(close_up(page, "#read-photo", f"demo-read-reading-{width}.png"))
    while not held:
        page.wait_for_timeout(100)
    held[0].fulfill(json=paper_answer("bill", READ_BILL))
    page.wait_for_selector("#read-result:not([hidden])")
    for name, stand_in in [("bill", READ_BILL), ("clinic", READ_CLINIC), ("scam", READ_SCAM)]:
        if name != "bill":
            page.click("#read-another")
            read_paper(page, name, paper_answer(name, stand_in))
        page.wait_for_timeout(700)  # the card has risen in
        no_problems(page, f"read, the {name} at {width}px")
        saved.append(close_up(page, "#read-result", f"demo-read-{name}-{width}.png"))
    return saved


def close_ups(browser) -> list[str]:
    """The Oct 30 polish, up close at both widths: the Today list (check-in
    done), the family update's pills line, Doctor notes questions (the first
    marked as asked, on the copy), the Memory book cards, Read it to me,
    and the pill reminder card from the hidden ?demo=reminder."""
    saved = []
    for width, height in SIZES:
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"http://localhost:{PORT}/#/", wait_until="networkidle")
        wait_for_screen(page, "today")
        page.wait_for_selector("#check-in-done:not([hidden])")
        page.wait_for_selector("#today-weather:not([hidden])")
        saved.append(close_up(page, ".today", f"demo-fix-today-{width}.png"))

        # Where Buddy read the news, under its words in voice mode (made-up reply).
        page.goto(f"http://localhost:{PORT}/#/talk", wait_until="load")
        wait_for_screen(page, "talk")
        page.evaluate("say('There’s a night market in Old Town on Saturday, from 2 to 10.');"
                      "showActions([{type: 'sources', sites: ['pdxpipeline.com', 'jambase.com']}])")
        page.add_style_tag(content=".pill-banner { display: none !important; }")  # a pill may be due in the copy
        page.wait_for_timeout(600)
        saved.append(close_up(page, "[data-screen='talk']", f"demo-fix-sources-{width}.png"))

        # Talking without tapping: her words as she says them (made up: no
        # microphone here), "Pause" on the button, the orb listening.
        page.goto(f"http://localhost:{PORT}/#/talk", wait_until="load")
        wait_for_screen(page, "talk")
        page.add_style_tag(content=".pill-banner { display: none !important; }")
        page.evaluate("showActions([]); setTalkState('listening'); showLiveWords('Do you know what the weather is like');"
                      "document.getElementById('talk-label').textContent = 'Pause';"
                      "document.getElementById('talk-button').setAttribute('data-hands-free', 'her')")
        page.wait_for_timeout(600)
        saved.append(close_up(page, "[data-screen='talk']", f"demo-fix-handsfree-{width}.png"))

        page.goto(f"http://localhost:{PORT}/#/family", wait_until="networkidle")
        wait_for_screen(page, "family")
        page.wait_for_function("document.getElementById('update-text').textContent.includes('Pills: ')")
        saved.append(close_up(page, ".family-update", f"demo-fix-family-{width}.png"))

        page.goto(f"http://localhost:{PORT}/#/notes", wait_until="networkidle")
        wait_for_screen(page, "notes")
        page.wait_for_selector("#notes-doc .doc-questions")
        if width == SIZES[0][0]:
            page.click("#notes-doc .doc-questions li >> nth=0 >> text=Mark as asked")
        page.wait_for_selector("#notes-doc .doc-questions .doc-asked")
        page.wait_for_timeout(300)
        saved.append(close_up(page, "#notes-doc .doc-section", f"demo-fix-notes-{width}.png"))

        page.goto(f"http://localhost:{PORT}/#/memories", wait_until="networkidle")
        wait_for_screen(page, "memories")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_function("[...document.querySelectorAll('.memory-img')].every(i => i.classList.contains('shown'))")
        heights = page.eval_on_selector_all(".memory-card", "cards => cards.map(c => Math.round(c.getBoundingClientRect().height))")
        if width >= 768:
            assert len(set(heights)) == 1, f"Memory book cards side by side should be the same height: {heights}"
        saved.append(close_up(page, "#memory-cards", f"demo-fix-memories-{width}.png"))
        page.close()

        page = browser.new_page(viewport={"width": width, "height": height})
        saved += read_close_ups(page, width)
        page.close()

        # The hidden demo reminder: it pops up 2 seconds after the first tap.
        for theme in ("light", "dark"):
            page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
            page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
            # Not "networkidle": the voice is made ahead (warmVoice), which keeps the network busy.
            page.goto(f"http://localhost:{PORT}/?demo=reminder#/", wait_until="load")
            wait_for_screen(page, "today")
            page.mouse.click(5, height - 5)  # the first tap, on an empty spot
            page.wait_for_selector("#pill-banner:not([hidden])", timeout=10000)
            words = page.text_content("#pill-banner-words") or ""
            assert words.startswith("Rose, it’s time for your "), words
            page.wait_for_timeout(900)  # it has risen in
            no_problems(page, f"the demo reminder at {width}px, {theme}")
            name = f"demo-fix-reminder-{width}{'' if theme == 'light' else '-dark'}.png"
            page.screenshot(path=str(OUT / name))
            saved.append(name)
            page.close()
    return saved


def welcome(browser) -> list[str]:
    """The welcome's three steps, on an empty database."""
    saved = []
    for width, height in SIZES:
        server = start_server(FOLDER / f"welcome-{width}.db", WELCOME_PORT)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"http://localhost:{WELCOME_PORT}/", wait_until="networkidle")
            wait_for_screen(page, "welcome")
            page.click("#welcome-begin")
            page.wait_for_selector("#welcome-name-form:not([hidden])")
            page.fill("#welcome-name", "Rose")
            for step, action in [(1, "#welcome-name-form button[type=submit]"), (2, "#welcome-family-form button[type=submit]")]:
                page.wait_for_timeout(500)
                no_problems(page, f"welcome step {step} at {width}px")
                path = OUT / f"demo-welcome-{step}-{width}.png"
                page.screenshot(path=str(path), full_page=True)
                saved.append(path.name)
                if step == 2:
                    page.fill("#welcome-family-name", "Maria")
                    page.fill("#welcome-family-phone", "555-0100")
                page.click(action)
                page.wait_for_selector(f"[data-step='{step + 1}']:not([hidden])")
            page.wait_for_timeout(500)
            no_problems(page, f"welcome step 3 at {width}px")
            path = OUT / f"demo-welcome-3-{width}.png"
            page.screenshot(path=str(path), full_page=True)
            saved.append(path.name)
            page.close()
        finally:
            server.terminate()
            server.wait()
    return saved


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright

    photos()  # the made-up papers for Read it to me (made once, no AI)
    database = copy_the_app_data()
    server = start_server(database, PORT)
    add_made_up_weather(database)  # after the server made its tables
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            names = screens(browser) + close_ups(browser) + welcome(browser)
            browser.close()
    finally:
        server.terminate()
    print(f"{len(names)} screenshots, no layout problems, every button's words on one line:")
    print("  " + ", ".join(names))
