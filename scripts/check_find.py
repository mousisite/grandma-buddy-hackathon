# scripts/check_find.py
# A hand-run check of "Find my things" with the REAL SAM 3.1 and Muse Spark,
# end to end in a browser, then screenshots.
#
# 1. Makes 4 test photos with Muse Image, once (rooms and a desk only, no
#    people, no writing), into scripts/find_photos/. Made for this project,
#    so we can use them. Skipped when the photos are already there.
# 2. Starts the app on a throwaway database and, in a browser, looks for
#    the glasses (in the living room and on a desk), the keys, the pill
#    bottle, the remote, and an umbrella that isn't there, exactly as she
#    would: type what she's looking for,
#    give it the photo. The real SAM 3.1 finds it; the real Muse Spark says
#    where. Prints each answer, and SAM's own answer line for the glasses.
# 3. Saves screenshots at 390px (light) from those real looks, then replays
#    the same answers (no more AI calls) for 1440px and dark.
#
# Run it by hand only. The first run costs about 7 cents (4 pictures at
# $0.01, 7 looks at $0.0025, 5 short sentences); later runs about 3 cents:
#   .venv\Scripts\python scripts\check_find.py
# Just one look (about half a cent, plus a cent the first time to paint its photo):
#   .venv\Scripts\python scripts\check_find.py --only desk-glasses
# Only the screenshots again, from the answers it saved last time (free):
#   .venv\Scripts\python scripts\check_find.py --screenshots

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "scripts" / "find_photos"
OUT = ROOT / "test-output"
FOLDER = OUT / "find-check"
ANSWERS = FOLDER / "answers.json"
PORT = 8003

ONLY_SCREENSHOTS = "--screenshots" in sys.argv
ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
SENT = {}  # the photo the page sent for each look (only while this runs)

sys.path.insert(0, str(ROOT))

# The test photos: everyday rooms with the thing somewhere in them.
PICTURES = {
    "living-room.webp": (
        "A realistic phone photo of a cozy living room in an older woman's home, taken from standing height in soft "
        "afternoon light: an armchair with a knitted blanket, a small wooden side table beside it with a lamp and a "
        "cup of tea, and a pair of reading glasses resting on the side table next to the lamp. A bookshelf behind. "
        "No people, no pets, no writing or text anywhere."
    ),
    "kitchen.webp": (
        "A realistic phone photo of a tidy home kitchen counter, taken from standing height: a bowl of apples, a set "
        "of house keys on a ring lying near the fruit bowl, an electric kettle, and a small amber pill bottle with a "
        "white cap standing beside the kettle, a folded tea towel. No people, no pets, no labels, writing, or text "
        "anywhere."
    ),
    "sofa.webp": (
        "A realistic phone photo of a living room sofa with soft cushions and a crocheted throw, a black TV remote "
        "control lying between two cushions, a low coffee table with a houseplant and a folded newspaper turned face "
        "down. Warm evening lamp light. No people, no pets, no writing or text anywhere."
    ),
    "desk.webp": (
        "A realistic phone photo of a small wooden writing desk at home by a window, taken from standing height in "
        "daylight: a pair of reading glasses lying folded on the desk beside a closed notebook and a pen, a desk lamp, "
        "a mug, and a small potted plant. No people, no pets, no writing or text anywhere."
    ),
}

# What she looks for, in which photo (the umbrella isn't there).
LOOKS = [
    ("glasses", "my glasses", "living-room.webp"),
    ("keys", "keys", "kitchen.webp"),
    ("pill-bottle", "pill bottle", "kitchen.webp"),
    ("remote", "the remote", "sofa.webp"),
    ("umbrella", "my umbrella", "living-room.webp"),
    ("desk-glasses", "Where are my glasses?", "desk.webp"),
]


def chosen_looks() -> list:
    """Every look, or only the one named with --only."""
    return [look for look in LOOKS if ONLY in (None, look[0])]


def make_photos() -> None:
    from app import meta_client

    PHOTOS.mkdir(parents=True, exist_ok=True)
    needed = {photo for _, _, photo in chosen_looks()}
    for name, prompt in PICTURES.items():
        path = PHOTOS / name
        if name not in needed:
            continue
        if path.exists():
            continue
        started = time.time()
        path.write_bytes(meta_client.paint(prompt))  # the real Muse Image
        print(f"Painted {name} in {time.time() - started:.0f} seconds ({path.stat().st_size // 1024} KB)")


def start_server(with_key: bool) -> subprocess.Popen:
    """The app on a throwaway database. With the key, it reads .env itself
    (this script never does); without it, there are no AI calls at all."""
    env = dict(os.environ, DATABASE_PATH=str(FOLDER / "check_find.db"))
    if not with_key:
        env["MODEL_API_KEY"] = ""
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], cwd=ROOT,
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/api/ping", timeout=2)
            break
        except OSError:
            time.sleep(0.5)
    # Her name is saved, so the app opens on Home, not the welcome.
    request = urllib.request.Request(f"http://localhost:{PORT}/api/profile", method="PUT",
                                     data=json.dumps({"preferred_name": "Rose"}).encode(),
                                     headers={"Content-Type": "application/json"})
    urllib.request.urlopen(request, timeout=10)
    return server


def look(page, said: str, photo: Path, theme: str, width: int, name: str) -> dict:
    """Look for one thing like she would, and save a screenshot."""
    from scripts.browser_checks.home import LAYOUT_PROBLEMS_JS, wait_for_screen

    # Home, then Find: a fresh question (each screen change finishes first).
    page.goto(f"http://localhost:{PORT}/#/", wait_until="networkidle")
    wait_for_screen(page, "today")
    page.goto(f"http://localhost:{PORT}/#/find", wait_until="networkidle")
    wait_for_screen(page, "find")
    page.fill("#find-thing", said)
    with page.expect_response("**/api/find", timeout=120_000) as answered:
        page.set_input_files("#find-camera", str(photo))
    answer = answered.value.json()
    SENT[name] = answered.value.request.post_data_json["image"]  # the JPEG the page made
    page.wait_for_selector("#find-after:not([hidden])")
    page.wait_for_timeout(1300)  # the halo has finished drawing
    problems = page.evaluate(LAYOUT_PROBLEMS_JS)
    assert not problems, f"layout problems for {name} at {width}px: {problems}"
    page.screenshot(path=str(OUT / f"find-{name}-{width}-{theme}.png"), full_page=True)
    return answer


def real_looks() -> dict:
    """Every look with the real SAM 3.1 and Muse Spark, in a browser at 390px."""
    from playwright.sync_api import sync_playwright

    answers = {}
    server = start_server(with_key=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844})
            for name, said, photo in chosen_looks():
                started = time.time()
                answer = look(page, said, PHOTOS / photo, "light", 390, name)
                answers[name] = answer
                found = f"box {answer['box']} of {answer['width']}x{answer['height']}" if answer.get("found") else "not found"
                print(f"{said!r} in {photo}: {found}, {time.time() - started:.1f} seconds")
                print(f"  Buddy: {answer.get('sentence') or answer.get('detail')}")
            browser.close()
    finally:
        server.terminate()
    ANSWERS.write_text(json.dumps(answers, indent=2), encoding="utf-8")
    return answers


def sam_line() -> None:
    """SAM 3.1's own answer line for the glasses (one more look), so the box
    and mask records can be checked by eye."""
    from app import finder, meta_client

    if "glasses" not in SENT:
        return  # only one look this time
    line = meta_client.segment(SENT["glasses"], "glasses")  # the same JPEG the page sent
    (FOLDER / "sam-line.txt").write_text(line, encoding="utf-8")
    print(f"SAM 3.1's answer line ({len(line)} characters, saved to test-output/find-check/sam-line.txt):")
    print("  " + (line[:240] + ("…" if len(line) > 240 else "")))
    print(f"  Read by finder.parse_matches: {finder.parse_matches(line)}")


def replay(answer: dict):
    """A stand-in for /api/find that gives back one real answer. (Playwright
    hands a handler with two arguments the request too, so it takes one.)"""
    return lambda route: route.fulfill(json=answer)


def replayed_screenshots(answers: dict) -> None:
    """The same answers at 1440px and in dark (no AI calls, free)."""
    from playwright.sync_api import sync_playwright

    server = start_server(with_key=False)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for theme, width, height in [("light", 1440, 900), ("dark", 390, 844), ("dark", 1440, 900)]:
                page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
                for name, said, photo in chosen_looks():
                    if name not in ("glasses", "umbrella", "keys", "desk-glasses"):
                        continue
                    page.unroute("**/api/find")
                    page.route("**/api/find", replay(answers[name]))
                    look(page, said, PHOTOS / photo, theme, width, name)
                page.close()
            browser.close()
    finally:
        server.terminate()


if __name__ == "__main__":
    if ONLY_SCREENSHOTS:
        saved = json.loads(ANSWERS.read_text(encoding="utf-8"))
        if ONLY:
            saved = {ONLY: saved[ONLY]}
    else:
        shutil.rmtree(FOLDER, ignore_errors=True)
        FOLDER.mkdir(parents=True)
        make_photos()
        saved = real_looks()
        sam_line()
    replayed_screenshots(saved)
    found = [name for name, answer in saved.items() if answer.get("found")]
    print(f"Found: {', '.join(found) or 'nothing'}. Screenshots: test-output/find-*.png")
    if ONLY:
        good = bool(saved[ONLY].get("found"))
    else:
        good = set(found) == {"glasses", "keys", "pill-bottle", "remote", "desk-glasses"} and not saved["umbrella"].get("found")
    print("Find check OK." if good else "PROBLEM: see the answers above.")
    sys.exit(0 if good else 1)
