# scripts/qa_screens.py
# Every screen at three widths and in both themes, for a design review: the
# app's screens with the demo week, the landing and its Privacy and Terms,
# the family page (signed out, and signed in as the made-up Maria), and the
# welcome's three steps on an empty database. Free: no key, no AI.
#   .venv\Scripts\python scripts\qa_screens.py
#   .venv\Scripts\python scripts\qa_screens.py --only talk,pills --widths 375
# Screenshots: test-output\qa\<screen>-<width>-<theme>.png (full page).
# Each page is also checked for sideways scrolling, small tap targets, and
# words spilling out of buttons (scripts/browser_checks/home.py's check).

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "test-output" / "qa"
PORT, EMPTY_PORT = 8024, 8025
WIDTHS = {375: 812, 768: 1024, 1440: 900}
THEMES = ("light", "dark")
SCREENS = ["", "talk", "diary", "pills", "notes", "family", "memories", "memory/1", "scam", "find", "read", "settings",
           "help"]
PAGES = ["about", "privacy", "terms"]

from scripts.browser_checks.home import LAYOUT_PROBLEMS_JS, wait_for_screen  # noqa: E402


def start_server(seeded: bool, port: int) -> subprocess.Popen:
    from app import db, demo

    folder = Path(tempfile.mkdtemp(prefix="buddy-qa-"))
    database = str(folder / "qa.db")
    os.environ["DATABASE_PATH"] = database
    if seeded:
        db.init_db(database)
        connection = db.get_connection(database)
        demo.seed(connection, datetime.now())
        connection.commit()
        connection.close()
    env = dict(os.environ, DATABASE_PATH=database, MODEL_API_KEY="", STRIPE_SECRET_KEY="")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=ROOT,
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/api/ping", timeout=2)
            return server
        except OSError:
            time.sleep(0.5)
    raise SystemExit("The QA server didn't start.")


def settle(page, screen: str) -> None:
    """Pictures loaded, cards risen, the orb still."""
    page.evaluate("window.speak = function () {}; window.warmVoice = function () {}; 0")
    if screen in ("memories", "memory"):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_function("[...document.querySelectorAll('.memory-img')].every(i => i.classList.contains('shown'))")
        page.evaluate("window.scrollTo(0, 0)")
    if screen == "family":
        page.wait_for_function("!!document.querySelector('#postcard:not([hidden]) .memory-img.shown') || "
                               "document.getElementById('postcard-note').textContent !== ''")
    if screen == "settings":
        page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    if screen == "notes":
        page.wait_for_function("document.getElementById('notes-doc').getAttribute('aria-busy') !== 'true'")
    page.wait_for_timeout(1200)


def shoot(page, name: str, width: int, theme: str, problems: list) -> None:
    found = page.evaluate(LAYOUT_PROBLEMS_JS)
    if found:
        problems.append((name, width, theme, found))
    page.screenshot(path=str(OUT / f"{name}-{width}-{theme}.png"), full_page=True)


def app_screens(browser, only: set, widths: list, problems: list) -> int:
    count = 0
    for theme in THEMES:
        for width in widths:
            page = browser.new_context(viewport={"width": width, "height": WIDTHS[width]}, color_scheme=theme,
                                       service_workers="block").new_page()
            page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
            for address in SCREENS:
                name = address.split("/")[0] or "home"
                if only and name not in only:
                    continue
                page.goto(f"http://localhost:{PORT}/#/{address}", wait_until="networkidle")
                wait_for_screen(page, name if name != "home" else "today")
                settle(page, name)
                shoot(page, name if address != "memory/1" else "memory-page", width, theme, problems)
                count += 1
            # The talk screen with words on it (a made-up exchange, no AI).
            if not only or "talk-reply" in only:
                page.goto(f"http://localhost:{PORT}/#/talk", wait_until="networkidle")
                wait_for_screen(page, "talk")
                settle(page, "talk")
                page.evaluate("newExchange('Should I take something for my headache?');"
                              "showReply(\"I'm sorry about that headache, Rose, I can't give medical advice. Dr. Lee is the right person to ask, shall I add that to your doctor notes? And if it feels like an emergency, please call 911.\");"
                              "showActions([{label: 'Call Dr. Lee', href: 'tel:5550199'}, {label: 'Call Maria', href: 'tel:5550100'}, {type: 'add_question', label: 'Add to doctor notes', question: 'q'}])")
                page.wait_for_timeout(1600)
                shoot(page, "talk-reply", width, theme, problems)
                count += 1
            # The landing, Privacy, Terms, and the family page.
            for address in PAGES:
                if only and address not in only:
                    continue
                page.goto(f"http://localhost:{PORT}/{address}", wait_until="networkidle")
                page.wait_for_timeout(1200)
                shoot(page, address, width, theme, problems)
                count += 1
            if not only or "family-page" in only:
                page.goto(f"http://localhost:{PORT}/family", wait_until="networkidle")
                page.wait_for_selector("#family-signin:not([hidden])")
                page.wait_for_timeout(800)
                shoot(page, "family-signin", width, theme, problems)
                page.click("#family-demo-signin")
                page.wait_for_selector("#family-day:not([hidden])")
                page.wait_for_function("document.getElementById('pills').textContent.trim() !== ''")
                page.wait_for_timeout(1200)
                shoot(page, "family-page", width, theme, problems)
                count += 2
            page.close()
    return count


def welcome_screens(browser, only: set, widths: list, problems: list) -> int:
    if only and "welcome" not in only:
        return 0
    count = 0
    for theme in THEMES:
        for width in widths:
            server = start_server(seeded=False, port=EMPTY_PORT)
            try:
                page = browser.new_context(viewport={"width": width, "height": WIDTHS[width]}, color_scheme=theme,
                                           service_workers="block").new_page()
                page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
                page.goto(f"http://localhost:{EMPTY_PORT}/", wait_until="networkidle")
                wait_for_screen(page, "welcome")
                page.wait_for_timeout(800)
                shoot(page, "welcome-1", width, theme, problems)
                page.click("#welcome-begin")
                page.wait_for_selector("#welcome-name-form:not([hidden])")
                page.fill("#welcome-name", "Rose")
                page.wait_for_timeout(500)
                shoot(page, "welcome-2", width, theme, problems)
                page.click("#welcome-name-form button[type=submit]")
                page.wait_for_selector("#welcome-family-form:not([hidden])")
                page.wait_for_timeout(500)
                shoot(page, "welcome-3", width, theme, problems)
                page.close()
                count += 3
            finally:
                server.terminate()
                server.wait()
    return count


def main(args: list[str]) -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else set()
    widths = [int(w) for w in args[args.index("--widths") + 1].split(",")] if "--widths" in args else list(WIDTHS)
    problems: list = []
    server = start_server(seeded=True, port=PORT)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            count = app_screens(browser, only, widths, problems)
            count += welcome_screens(browser, only, widths, problems)
            browser.close()
    finally:
        server.terminate()
    for name, width, theme, found in problems:
        print(f"PROBLEM {name} at {width}px {theme}: {found}")
    print(f"{count} screenshots in test-output/qa; layout problems: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
