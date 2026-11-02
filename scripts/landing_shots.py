# scripts/landing_shots.py
# The phone screens on the landing page (static/about.html), taken from a
# fresh copy of the made-up demo week (scripts/seed_demo.py), so nothing
# real can end up in a committed picture. Saved to static/landing/*.png at
# phone size (390 by 844, drawn at 2x so they stay crisp on any screen).
#
# The memory book page shows one of the bundled demo pictures (painted by
# Muse Image for this project, scripts/demo_pictures/), so nothing is sent
# to Meta and a run costs nothing, with or without a key.
#   .venv\Scripts\python scripts\landing_shots.py

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from scripts.browser_checks.home import READ_BILL, wait_for_screen  # noqa: E402
from scripts.check_read import FOLDER as PAPERS, photos  # noqa: E402
from scripts.demo_screenshots import add_made_up_weather, paper_answer  # noqa: E402

OUT = ROOT / "static" / "landing"
PORT = 8008
# A made-up reply for the talking screen (no AI is called here).
REPLY = "What a lovely morning for the garden, Rose. Did Tom make it over on Sunday?"


def seeded_database(folder: Path) -> Path:
    """The demo week on a fresh database in a temporary folder, bundled pictures included."""
    database = folder / "landing.db"
    env = dict(os.environ, DATABASE_PATH=str(database))
    command = [sys.executable, str(ROOT / "scripts" / "seed_demo.py"), "--reset", "--no-paint"]
    subprocess.run(command, cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    return database


def start_server(database: Path, with_key: bool) -> subprocess.Popen:
    env = dict(os.environ, DATABASE_PATH=str(database))
    if not with_key:
        env["MODEL_API_KEY"] = ""
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], cwd=ROOT,
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/api/ping", timeout=2)
            return server
        except OSError:
            time.sleep(0.5)
    raise SystemExit("The screenshot server didn't start.")


def shots(browser) -> list[str]:
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="light")
    page.add_init_script("localStorage.setItem('theme', 'light')")
    saved = []

    def shot(name: str) -> None:
        page.add_style_tag(content=".pill-banner { display: none !important; }")  # a pill may be due right now
        page.wait_for_timeout(1200)  # the orb and the cards have settled
        page.screenshot(path=str(OUT / f"{name}.png"))
        saved.append(f"{name}.png")

    page.goto(f"http://localhost:{PORT}/#/", wait_until="networkidle")
    wait_for_screen(page, "today")
    page.wait_for_selector("#check-in-done:not([hidden])")
    page.wait_for_selector("#today-weather:not([hidden])")
    shot("home")

    page.goto(f"http://localhost:{PORT}/#/talk", wait_until="load")
    wait_for_screen(page, "talk")
    page.evaluate(f"say({REPLY!r}); showActions([{{type: 'call', label: 'Call Maria', href: 'tel:555-0100'}}])")
    shot("talk")

    page.goto(f"http://localhost:{PORT}/#/pills", wait_until="networkidle")
    wait_for_screen(page, "pills")
    page.wait_for_selector(".check-row")
    shot("pills")

    page.goto(f"http://localhost:{PORT}/#/memory/1", wait_until="networkidle")
    wait_for_screen(page, "memory")
    page.wait_for_function("document.querySelector('.memory-img.shown') || document.querySelector('.memory-picture-words')",
                           timeout=240000)  # a painting can take a minute or two
    shot("memory")

    page.goto(f"http://localhost:{PORT}/#/read", wait_until="networkidle")
    wait_for_screen(page, "read")
    page.route("**/api/read", lambda route: route.fulfill(json=paper_answer("bill", READ_BILL)))
    page.set_input_files("#read-camera", str(PAPERS / "bill.png"))
    page.wait_for_selector("#read-result:not([hidden])")
    shot("read")
    page.close()
    return saved


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright

    with_key = bool(get_settings().model_api_key)
    photos()  # the made-up bill for Read it to me
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="buddy-landing-") as folder:
        database = seeded_database(Path(folder))
        server = start_server(database, with_key)
        add_made_up_weather(database)  # after the server made its tables
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                names = shots(browser)
                browser.close()
        finally:
            server.terminate()
            server.wait()
    print(f"{len(names)} screens saved to static/landing/: " + ", ".join(names))
