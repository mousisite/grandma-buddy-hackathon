# scripts/check_memory.py
# A hand-run check of the Memory book with the REAL AI, then screenshots.
#
# Puts two made-up memory talks in a throwaway database (test-output/
# memory-check/), then lets Muse Spark write each page and Muse Image paint
# it, exactly as the app does after she saves a memory. Prints each page and
# whether the AI's page passed the checks in app/memories.py (only her names
# and numbers, no advice); if it didn't, the page is her own words, and this
# says so. Then it opens the Memory book in a browser (no more AI calls) and
# saves screenshots at 390 and 1440px, light and dark, to test-output/.
#
# Run it by hand only. It costs about 3 cents (2 pictures at $0.01 and 2 short
# writing calls):
#   .venv\Scripts\python scripts\check_memory.py
# Only the screenshots again, from the pages it made last time (no AI, free):
#   .venv\Scripts\python scripts\check_memory.py --screenshots

import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "test-output"
FOLDER = OUT / "memory-check"
PORT = 8002

ONLY_SCREENSHOTS = "--screenshots" in sys.argv

# A throwaway database, set BEFORE the app reads its settings.
if not ONLY_SCREENSHOTS:
    shutil.rmtree(FOLDER, ignore_errors=True)
os.environ["DATABASE_PATH"] = str(FOLDER / "check_memory.db")
sys.path.insert(0, str(ROOT))

from app import db, memories, tools  # noqa: E402

# Made-up memories (docs/SAFETY.md section 9: demo data only).
TALKS = {
    "check-memory-farm": [
        ("user", "When I was a girl we spent every summer at my aunt Lucy's farm. I fed the chickens every morning "
                 "and we picked blueberries by the old stone wall."),
        ("assistant", "That sounds wonderful. When was that?"),
        ("user", "Oh, about 1958. My little brother Tom was there too, and he always ate more berries than he picked."),
    ],
    "check-memory-dance": [
        ("user", "I met my husband Walter at a dance at the church hall. He stepped on my feet all night."),
        ("assistant", "What a story! Who else was there?"),
        ("user", "My best friend June. It was the spring of 1961, and the hall smelled of lilacs."),
    ],
}


def write_and_paint() -> bool:
    db.init_db()
    connection = db.get_connection()
    db.get_profile(connection)
    connection.execute("UPDATE profile SET preferred_name = 'Rose', name = 'Rose Demo', family_name = 'Maria', "
                       "family_email = 'maria@example.com' WHERE id = 1")
    for conversation, talk in TALKS.items():
        for role, words in talk:
            db.save_message(connection, conversation, role, words)
    connection.commit()

    checks = []
    real_check = memories.checked

    def recording_check(answer, said):
        page, fix = real_check(answer, said)
        checks.append(fix or "passed")
        return page, fix

    memories.checked = recording_check
    good = True
    for conversation in TALKS:
        memory_id = tools.save_memory(connection, conversation)
        connection.commit()
        checks.clear()
        started = time.time()
        memories.make_page(memory_id)  # the real Muse Spark and Muse Image
        page = memories.page(connection, memory_id)
        print(f"Page {memory_id}, {time.time() - started:.0f} seconds. The AI's page: {' / '.join(checks) or 'no answer'}")
        print(f"  Title: {page['title']}")
        for paragraph in page["paragraphs"]:
            print(f"  {paragraph}")
        print(f"  Picture ({page['status']}): {page['scene']}")
        picture = memories.picture_path(connection.execute(
            "SELECT picture FROM memories WHERE id = ?", (memory_id,)).fetchone()["picture"])
        print(f"  File: {picture} ({picture.stat().st_size // 1024} KB)\n" if picture else "  File: none\n")
        good = good and page["status"] == "ready" and page["title"] != memories.FALLBACK_TITLE

    # One more page, still being painted, to see the shimmer (no AI call).
    connection.execute("INSERT INTO memories (created_at, updated_at, her_words, title, story, status) "
                       "VALUES (?, ?, 'Sunday dinners at home.', 'Sunday dinners', '[\"Sunday dinners at home.\"]', 'painting')",
                       (db.now(), db.now()))
    connection.commit()
    connection.close()
    return good


def screenshots() -> None:
    """The Memory book and one page, 390 and 1440px, light and dark."""
    env = dict(os.environ, MODEL_API_KEY="")  # no more AI calls from here on
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], cwd=ROOT,
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://localhost:{PORT}/api/ping", timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        from playwright.sync_api import sync_playwright
        from scripts.browser_checks.home import LAYOUT_PROBLEMS_JS

        def no_layout_problems(page, where):
            problems = page.evaluate(LAYOUT_PROBLEMS_JS)
            assert not problems, f"layout problems in {where}: {problems}"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            # (theme, width, height, text size): the four screenshots, then a
            # phone with the largest text (checked, not saved).
            for theme, width, height, words in [("light", 390, 844, 1), ("light", 1440, 900, 1),
                                                ("dark", 390, 844, 1), ("dark", 1440, 900, 1),
                                                ("light", 390, 844, 2)]:
                page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
                page.add_init_script(f"localStorage.setItem('words', '{words}')")
                page.goto(f"http://localhost:{PORT}/#/memories", wait_until="networkidle")
                # Lower pages load as she scrolls: scroll down so every painting is there.
                page.wait_for_selector(".memory-card .memory-img")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_function("[...document.querySelectorAll('.memory-card .memory-img')].every(i => i.classList.contains('shown'))")
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(900)
                no_layout_problems(page, f"the Memory book at {width}px")
                if words == 1:
                    page.screenshot(path=str(OUT / f"memory-book-{width}-{theme}.png"), full_page=True)
                page.click(".memory-card >> nth=-1")  # the oldest page: the farm
                page.wait_for_selector("#memory-picture .memory-img.shown")
                page.wait_for_timeout(900)
                no_layout_problems(page, f"a memory page at {width}px")
                if words == 1:
                    page.screenshot(path=str(OUT / f"memory-page-{width}-{theme}.png"), full_page=True)
                page.close()
            browser.close()
        print("Screenshots: test-output/memory-book-*.png and test-output/memory-page-*.png "
              "(and no layout problems, also with the largest text)")
    finally:
        server.terminate()


if __name__ == "__main__":
    ok = ONLY_SCREENSHOTS or write_and_paint()
    screenshots()
    print("Memory check OK." if ok else "PROBLEM: a page fell back to her own words or has no picture (see above).")
    sys.exit(0 if ok else 1)
