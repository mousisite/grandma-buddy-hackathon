# scripts/check_photos.py
# A hand-run, REAL end-to-end check of the three photo features, in a real
# browser, with screenshots:
#   - Find my things: SAM 3.1 finds the thing, Muse Spark says where it is
#   - Read it to me: Muse Spark reads a photo of a bill, and of a prize letter
#   - Check a message: a photo of the prize letter (Muse Spark's verdict),
#     the letter's words from Read it to me ("Check it for a scam"), and the
#     letter pasted as a text, where Meta's web search looks up the phone
#     number in it. (A number in a photo is never looked up, and the words
#     Read it to me passes on never carry the number: docs/SAFETY.md 8 and 8d.)
#
# The photos are all made for this project (no people, nothing real): a
# writing desk with reading glasses and house keys, painted with Muse Image
# the first time this runs (1 cent, into scripts/find_photos/desk-keys.webp),
# and the made-up electric bill and prize letter that scripts/check_read.py
# draws (scripts/read_docs/bill.png and scam.png).
#
# Costs about 4 cents (plus 1 cent the first time, for the desk photo): 2 SAM
# looks and 2 short "where it is" sentences, 3 papers read, 3 messages
# checked, 1 web search.
#   .venv\Scripts\python scripts\check_photos.py
#   .venv\Scripts\python scripts\check_photos.py --only find     (find, read, or scam)
#   .venv\Scripts\python scripts\check_photos.py --replay        (only the 1440px screenshots again, free)
# Screenshots land in test-output\photo-*.png at 390px (the real looks) and
# 1440px (the same answers played back, so no more AI calls). The answers
# are kept in test-output\photo-check.json.

import json
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
OUT = ROOT / "test-output"
PHOTOS = ROOT / "scripts" / "find_photos"
PAPERS = ROOT / "scripts" / "read_docs"
DESK = PHOTOS / "desk-keys.webp"
PORT = 8004

DESK_PROMPT = (
    "A realistic phone photo of a small wooden writing desk at home by a window, taken from standing height in "
    "daylight: a pair of reading glasses lying folded on the desk next to a ring of house keys, a closed notebook "
    "and a pen, a desk lamp, a mug, and a small potted plant. No people, no pets, no writing or text anywhere."
)

# The prize letter, pasted as a text (made up, like the letter; the number is
# a fictional 555 one), so the number in it is looked up on the web.
LETTER_TEXT = ("CONGRATULATIONS! YOU HAVE WON $5,000! To claim your prize, send a $50 processing fee in gift cards "
               "within 24 hours. Call 1-800-555-0142 now. Do not tell anyone until your prize arrives.")

# Each step: a name, the screen, what she says or pastes, and the photo.
STEPS = [
    ("find-glasses", "find", "my glasses", DESK),
    ("find-keys", "find", "my keys", DESK),
    ("read-bill", "read", "", PAPERS / "bill.png"),
    ("read-letter", "read", "", PAPERS / "scam.png"),
    ("read-letter-check", "read-then-scam", "", PAPERS / "scam.png"),  # then "Check it for a scam"
    ("scam-letter", "scam", "", PAPERS / "scam.png"),
    ("scam-text", "scam-text", LETTER_TEXT, None),  # pasted: the number in it is looked up
]


def chosen_steps(args: list[str]) -> list:
    only = args[args.index("--only") + 1] if "--only" in args else ""
    return [step for step in STEPS if not only or step[1] == only]


def make_desk_photo() -> None:
    """The desk photo, painted once with the real Muse Image."""
    from app import meta_client

    if DESK.exists():
        return
    started = time.time()
    DESK.write_bytes(meta_client.paint(DESK_PROMPT))
    print(f"Painted {DESK.name} in {time.time() - started:.0f} seconds ({DESK.stat().st_size // 1024} KB)")


def make_papers() -> None:
    """The bill and the prize letter, drawn by scripts/check_read.py if missing."""
    if not (PAPERS / "bill.png").exists() or not (PAPERS / "scam.png").exists():
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_read

        check_read.photos()


def start_server(with_key: bool) -> subprocess.Popen:
    """The app on a throwaway database holding the demo week (Rose, Maria,
    Dr. Lee). With the key it reads .env itself (this script never does);
    without it there are no AI calls at all."""
    from app import db, demo

    database = str(Path(tempfile.mkdtemp(prefix="buddy-photos-")) / "check_photos.db")
    db.init_db(database)
    connection = db.get_connection(database)
    demo.seed(connection, datetime.now())
    connection.commit()
    connection.close()
    env = dict(os.environ, DATABASE_PATH=database)
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
    return server


# What each screen posts to, which file input takes the photo, and what shows when it's done.
SCREENS = {
    "find": ("**/api/find", "#find-camera", "#find-after:not([hidden])"),
    "read": ("**/api/read", "#read-library", "#read-result:not([hidden])"),
    "read-then-scam": ("**/api/scam-check", "#read-library", "#scam-result:not([hidden])"),
    "scam": ("**/api/scam-check", "#scam-photo-input", "#scam-result:not([hidden])"),
    "scam-text": ("**/api/scam-check", "", "#scam-result:not([hidden])"),
}


def run_step(page, name: str, screen: str, said: str, photo: Path, width: int) -> dict:
    """One step the way she would do it, then a screenshot. Returns the server's answer."""
    from scripts.browser_checks.home import LAYOUT_PROBLEMS_JS, wait_for_screen

    route, file_input, done = SCREENS[screen]
    page.goto(f"http://localhost:{PORT}/#/", wait_until="networkidle")
    wait_for_screen(page, "today")
    first_screen = {"read-then-scam": "read", "scam-text": "scam"}.get(screen, screen)
    page.goto(f"http://localhost:{PORT}/#/{first_screen}", wait_until="networkidle")
    wait_for_screen(page, first_screen)
    if said and screen == "find":
        page.fill("#find-thing", said)
    started = time.time()
    if screen == "scam-text":
        if page.evaluate("document.getElementById('scam-compose').hidden"):
            page.click("#scam-another")  # an earlier step's verdict is still up: Check another message
        try:
            page.fill("#scam-text", said, timeout=15_000)
        except Exception:
            # What is on the screen when the box can't be found (for the log).
            page.screenshot(path=str(OUT / f"photo-{name}-{width}-problem.png"), full_page=True)
            print("PROBLEM: the message box isn't usable. Shown:",
                  page.evaluate("[...document.querySelectorAll('section[data-screen]')].filter(s => !s.hidden).map(s => s.dataset.screen)"),
                  "compose hidden:", page.evaluate("document.getElementById('scam-compose').hidden"),
                  "dialogs:", page.evaluate("[...document.querySelectorAll('dialog[open]')].map(d => d.id)"),
                  "box:", page.evaluate("JSON.stringify(document.getElementById('scam-text').getBoundingClientRect())"),
                  "style:", page.evaluate("const c = getComputedStyle(document.getElementById('scam-text')); c.display + ' ' + c.visibility + ' ' + c.opacity"))
            raise
        with page.expect_response(route, timeout=180_000) as answered:
            page.click("#scam-check")
    elif screen == "read-then-scam":
        # Read the letter first, then "Check it for a scam": its words go to
        # the scam checker as text, so the number in it is looked up.
        with page.expect_response("**/api/read", timeout=180_000):
            page.set_input_files(file_input, str(photo))
        page.wait_for_selector("#read-result:not([hidden])", timeout=30_000)
        with page.expect_response(route, timeout=180_000) as answered:
            page.click("#read-check-scam")
    else:
        with page.expect_response(route, timeout=180_000) as answered:
            page.set_input_files(file_input, str(photo))
    answer = answered.value.json()
    page.wait_for_selector(done, timeout=30_000)
    page.wait_for_timeout(1300)  # the halo finishes drawing; the words settle
    problems = page.evaluate(LAYOUT_PROBLEMS_JS)
    assert not problems, f"layout problems for {name} at {width}px: {problems}"
    page.screenshot(path=str(OUT / f"photo-{name}-{width}.png"), full_page=True)
    answer["_seconds"] = round(time.time() - started, 1)
    return answer


def describe(name: str, answer: dict) -> str:
    screen = next(step[1] for step in STEPS if step[0] == name)
    if screen == "find":
        where = f"box {answer.get('box')} in a {answer.get('width')}x{answer.get('height')} photo" if answer.get("found") else "not found"
        return f"{where}; Buddy: {answer.get('sentence') or answer.get('detail')}"
    if screen == "read":
        facts = ", ".join(f"{f['label']} {f['value']}" for f in answer.get("facts", []))
        scam = f"; scam signs: {answer['scam']['flags']}" if answer.get("scam") else ""
        return f"{answer.get('kind')}: {answer.get('spoken')} [{facts}]{scam}"
    lookup = answer.get("lookup")
    looked = f"; on the web: {lookup['words']} (from {', '.join(lookup['sites']) or 'no named site'})" if lookup else ""
    return f"{answer.get('verdict')}: {answer.get('title')}. {answer.get('explanation')} Signs: {answer.get('red_flags')}{looked}"


def checks_for(name: str, answer: dict) -> list[str]:
    lines = []

    def must(ok: bool, words: str) -> None:
        lines.append(("PASS  " if ok else "FAIL  ") + words)

    if name.startswith("find"):
        must(bool(answer.get("found")), f"{name}: found it in the photo")
        must(bool(answer.get("sentence")), f"{name}: Buddy says where it is")
    elif name == "read-bill":
        must(answer.get("kind") == "bill", f"read as a bill (kind: {answer.get('kind')})")
        must(any("84.20" in f["value"] for f in answer.get("facts", [])), "the amount due $84.20 is printed on it and read")
        must(not answer.get("scam"), "no scam signs on the bill")
    elif name == "read-letter":
        must(bool(answer.get("scam")), "the prize letter is flagged with signs of a scam")
    elif name == "read-letter-check":
        must(answer.get("verdict") == "likely_scam", f"the letter's words are a likely scam (verdict: {answer.get('verdict')})")
        must(answer.get("lookup") is None, "no lookup: the words Read it to me passes on carry no number (docs/SAFETY.md 8d)")
    elif name == "scam-text":
        must(answer.get("verdict") == "likely_scam", f"the pasted letter is a likely scam (verdict: {answer.get('verdict')})")
        must(bool(answer.get("lookup")), "the phone number in it was looked up on the web")
    elif name == "scam-letter":
        must(answer.get("verdict") == "likely_scam", f"the photo of the letter is a likely scam (verdict: {answer.get('verdict')})")
        must(answer.get("lookup") is None, "a number in a photo is never looked up (docs/SAFETY.md section 8)")
    return lines


def real_run(steps: list) -> dict:
    """Every step with the real models, in a browser at 390px."""
    from playwright.sync_api import sync_playwright

    answers = {}
    server = start_server(with_key=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block").new_page()
            for name, screen, said, photo in steps:
                answer = run_step(page, name, screen, said, photo, 390)
                answers[name] = answer
                what = photo.name if photo else "pasted text"
                print(f"\n=== {name} ({what}{', ' + repr(said) if said and photo else ''}): {answer['_seconds']} s")
                print("  " + describe(name, answer))
                for line in checks_for(name, answer):
                    print("  " + line)
            browser.close()
    finally:
        server.terminate()
    return answers


def replay(answer: dict):
    """A stand-in for the server that gives back one real answer. (Playwright
    hands a handler with two arguments the request too, so it takes one.)"""
    return lambda route: route.fulfill(json=answer)


def replay_run(steps: list, answers: dict) -> None:
    """The same answers at 1440px (no AI calls, free)."""
    from playwright.sync_api import sync_playwright

    server = start_server(with_key=False)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="block").new_page()
            for name, screen, said, photo in steps:
                route = SCREENS[screen][0]
                page.unroute(route)
                page.route(route, replay(answers[name]))
                if screen == "read-then-scam":
                    page.unroute("**/api/read")
                    page.route("**/api/read", replay(answers["read-letter"]))
                run_step(page, name, screen, said, photo, 1440)
            browser.close()
    finally:
        server.terminate()


def main(args: list[str]) -> int:
    from app.config import get_settings

    if not get_settings().model_api_key:
        print("No API key in .env.")
        return 1
    steps = chosen_steps(args)
    OUT.mkdir(exist_ok=True)
    make_papers()
    if "--replay" in args:
        answers = json.loads((OUT / "photo-check.json").read_text(encoding="utf-8"))
        steps = [step for step in steps if step[0] in answers]
    else:
        if any(photo == DESK for _, _, _, photo in steps):
            make_desk_photo()
        saved = json.loads((OUT / "photo-check.json").read_text(encoding="utf-8")) if (OUT / "photo-check.json").exists() else {}
        saved.update(real_run(steps))  # --only keeps the other steps' saved answers
        (OUT / "photo-check.json").write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
        answers = saved
        steps = [step for step in STEPS if step[0] in answers] if "--only" not in args else steps
    replay_run(steps, answers)
    failed = [line for name, answer in answers.items() for line in checks_for(name, answer) if line.startswith("FAIL")]
    print(f"\nPhoto check: {'PROBLEMS FOUND' if failed else 'OK'} ({len(steps)} steps). Screenshots: test-output/photo-*.png")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
