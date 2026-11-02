# scripts/check_failures.py
# Every way the demo can go wrong, on purpose, with a screenshot of what she
# sees each time, so nothing ever shows "error" or a code:
#   meta-down     Meta can't be reached (META_API_URL points at a dead address):
#                 every AI feature, and the safety net and a pill reminder,
#                 which must still work
#   no-internet   the page can't reach its server at all: the talk screen's
#                 call buttons, the photo screens, the lists
#   microphone    no microphone at all, and one the browser won't allow
#   slow          Meta takes 6 seconds: the orb thinks, "One moment…", then the reply
#   blurry        a very blurry photo through the REAL models: Find my things,
#                 Read it to me, Check a message, a pill label, an old photo
#                 (about 4 cents)
#   offline       the server has stopped: the Home the service worker kept, with its note
# Every message shown is checked for calm words: never "error", "failed", a
# status code, or anything technical.
#   .venv\Scripts\python scripts\check_failures.py
#   .venv\Scripts\python scripts\check_failures.py --only meta-down
# Screenshots: test-output\fail-<part>-<what>-390.png (the talk screen also at 1440).

import base64
import json
import os
import re
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
DEAD = "http://127.0.0.1:9/v1"  # nothing listens there: every Meta call fails at once
PARTS = ["meta-down", "no-internet", "microphone", "slow", "blurry", "offline"]
GRANDSON = "Grandma it's me, I'm in jail, send $2,000 in gift cards and don't tell mom"
# Words that must never reach her screen.
TECHNICAL = re.compile(r"\b(error|errors|failed|failure|exception|traceback|http|undefined|null|nan|timeout|json|api)\b"
                       r"|\b[45]\d\d\b", re.IGNORECASE)
# Where the page's words to her appear.
MESSAGE_SPOTS = ["#message", "#offline-note", "#find-status", "#find-answer", "#read-status", "#read-summary", "#scam-status",
                 "#scam-explanation", "#pill-photo-status", "#pills-undo", "#memories-status", "#memory-status",
                 "#notes-status", "#safety-message", ".toast", "#talk-hint", "#buddy-label", "#find-ask .problem",
                 "#today-weather-text", "#sent-note", "#postcard-note", "#memories-photo-status", "#pill-banner-words"]

report = []  # (part, what, the words she saw)


def start_server(name: str, port: int, extra_env: dict) -> subprocess.Popen:
    """The app on a throwaway database with the demo week, on its own port."""
    from app import db, demo

    folder = Path(tempfile.mkdtemp(prefix=f"buddy-fail-{name}-"))
    database = str(folder / "check.db")
    env = dict(os.environ, DATABASE_PATH=database, STRIPE_SECRET_KEY="", **extra_env)
    # The seed reads its settings from the environment it runs in.
    for key, value in env.items():
        os.environ[key] = value
    db.init_db(database)
    connection = db.get_connection(database)
    demo.seed(connection, datetime.now())
    connection.commit()
    connection.close()
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=ROOT,
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/api/ping", timeout=2)
            return server
        except OSError:
            time.sleep(0.5)
    raise SystemExit(f"The {name} server didn't start.")


def stop(server: subprocess.Popen) -> None:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()


def words_shown(page) -> list[str]:
    """Everything the page is telling her right now, in the usual spots."""
    return page.evaluate("""(spots) => {
        const seen = [];
        for (const spot of spots) {
            for (const element of document.querySelectorAll(spot)) {
                const box = element.getBoundingClientRect();
                const shown = box.width > 0 && box.height > 0 && !element.closest('[hidden]');
                const text = (element.textContent || '').trim();
                if (shown && text) seen.push(text);
            }
        }
        return seen;
    }""", MESSAGE_SPOTS)


def record(page, part: str, what: str, width: int = 390, scroll_to: str = "") -> None:
    """A screenshot (scrolled to scroll_to, if given), and a check that
    nothing technical is on the screen."""
    if scroll_to:
        page.eval_on_selector(scroll_to, "element => element.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(600)
    path = OUT / f"fail-{part}-{what}-{width}.png"
    page.screenshot(path=str(path), full_page=False)
    seen = words_shown(page)
    technical = [text for text in seen if TECHNICAL.search(text)]
    report.append((part, what, seen, technical))
    print(f"  {what}: " + (" | ".join(seen)[:230] if seen else "(no words shown)"))
    if technical:
        print(f"  PROBLEM: technical words on the screen: {technical}")


def open_screen(page, port: int, screen: str) -> None:
    from scripts.browser_checks.home import wait_for_screen

    page.goto(f"http://localhost:{port}/#/{screen}", wait_until="networkidle")
    wait_for_screen(page, screen.split("/")[0] or "today")
    page.evaluate("window.speak = window.speak || function () {}; 0")


def quiet(page) -> None:
    """No sound from the page while it is checked: the voice "finishes" at
    once (so a greeting hands over to the microphone as it would)."""
    page.evaluate("window.speak = function (text, options) {"
                  "  if (options && options.onEnd) { setTimeout(options.onEnd, 50); }"
                  "}; window.warmVoice = function () {}; 0")


def talk_with(page, words: str, wait_for: str) -> None:
    # The same path the talk screen takes: a problem goes to talkProblem's kind words.
    page.evaluate("(words) => { newExchange(words); return askBuddy(words).catch(talkProblem); }", words)
    page.wait_for_function(f"document.getElementById('message').textContent.includes({json.dumps(wait_for)})", timeout=30000)


# ---------- meta-down: Meta can't be reached ----------

def meta_down(playwright) -> None:
    port = 8014
    server = start_server("meta-down", port, {"META_API_URL": DEAD, "MODEL_API_KEY": "not-a-real-key"})
    try:
        browser = playwright.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        for width, height in ((390, 844), (1440, 900)):
            context = browser.new_context(viewport={"width": width, "height": height}, service_workers="block",
                                          permissions=["microphone"])
            page = context.new_page()
            # Buddy's AI can't be reached: a kind reply, and the talk goes on.
            open_screen(page, port, "talk")
            quiet(page)
            talk_with(page, "Hello Buddy, how are you?", "trouble thinking")
            record(page, "meta-down", "talk", width)
            if width == 1440:
                context.close()
                continue
            # The safety net still works: plain rules on the server, no AI.
            talk_with(page, "my chest feels really tight", "could be an emergency")
            page.wait_for_selector("#safety-screen[open][data-kind='emergency']")
            record(page, "meta-down", "safety-net", width)
            page.click("#safety-close")
            page.wait_for_function("!document.getElementById('safety-screen').open")
            # Tap to talk: live speech-to-text can't start, so she taps; her
            # recording can't be written down, so Buddy says so, with the calls.
            open_screen(page, port, "")
            quiet(page)
            page.click("#start-talk")
            page.wait_for_selector("#talk-button[data-state='listening']", timeout=20000)
            page.wait_for_timeout(800)
            page.click("#talk-button")
            page.wait_for_function("document.getElementById('message').textContent.includes('catch that')", timeout=30000)
            record(page, "meta-down", "tap-to-talk", width)
            # A pill reminder still comes (the server's own clock and rules).
            page.goto(f"http://localhost:{port}/?demo=reminder#/", wait_until="load")
            page.wait_for_selector("#start-talk")
            quiet(page)
            page.mouse.click(5, height - 5)
            page.wait_for_selector("#pill-banner:not([hidden])", timeout=10000)
            record(page, "meta-down", "pill-reminder", width)
            # Check a message: the plain rules still give a verdict.
            open_screen(page, port, "scam")
            quiet(page)
            page.fill("#scam-text", GRANDSON)
            page.click("#scam-check")
            page.wait_for_selector("#scam-result:not([hidden])", timeout=30000)
            record(page, "meta-down", "scam-rules", width)
            # Read it to me, Find my things, a pill label, an old photo.
            open_screen(page, port, "read")
            quiet(page)
            page.set_input_files("#read-library", str(PAPERS / "bill.png"))
            page.wait_for_function("document.getElementById('read-status').textContent.includes('just now')", timeout=30000)
            record(page, "meta-down", "read", width)
            open_screen(page, port, "find")
            quiet(page)
            page.fill("#find-thing", "my glasses")
            page.set_input_files("#find-camera", str(PHOTOS / "desk-keys.webp"))
            page.wait_for_function("document.getElementById('find-status').textContent.includes('just now')", timeout=30000)
            record(page, "meta-down", "find", width)
            open_screen(page, port, "pills")
            quiet(page)
            page.set_input_files("#pill-photo-input", str(PAPERS / "label.png"))
            page.wait_for_function("document.getElementById('pill-photo-status').textContent.includes('just now')", timeout=30000)
            record(page, "meta-down", "pill-label", width, scroll_to="#pill-photo-status")
            open_screen(page, port, "memories")
            quiet(page)
            page.set_input_files("#memory-photo-input", str(PHOTOS / "kitchen.webp"))
            # With Meta down the photo stays hers (never painted) and Buddy opens
            # the memory talk with its fixed words, so the talk screen comes up.
            page.wait_for_function("currentScreen() === 'talk' || "
                                   "document.getElementById('memories-photo-status').textContent.includes('just now')", timeout=30000)
            page.wait_for_timeout(800)
            record(page, "meta-down", "old-photo", width)
            # Doctor notes and Home: the week's facts are plain code, so they still show.
            open_screen(page, port, "notes")
            page.wait_for_function("document.getElementById('notes-doc').getAttribute('aria-busy') !== 'true'", timeout=30000)
            record(page, "meta-down", "doctor-notes", width)
            open_screen(page, port, "")
            page.wait_for_selector(".today .row", timeout=10000)
            record(page, "meta-down", "home", width)
            context.close()
        browser.close()
    finally:
        stop(server)


# ---------- no-internet: the page can't reach its server ----------

def no_internet(playwright) -> None:
    port = 8015
    server = start_server("no-internet", port, {"MODEL_API_KEY": ""})
    try:
        browser = playwright.chromium.launch()
        page = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block").new_page()
        open_screen(page, port, "talk")
        quiet(page)
        page.route("**/api/**", lambda route: route.abort())  # from now on, nothing gets through
        talk_with(page, "Hello Buddy", "reach the internet")
        record(page, "no-internet", "talk")
        for screen, file_input, photo, spot in (
            ("find", "#find-camera", PHOTOS / "desk-keys.webp", "find-status"),
            ("read", "#read-library", PAPERS / "bill.png", "read-status"),
        ):
            page.goto(f"http://localhost:{port}/#/{screen}", wait_until="load")
            page.wait_for_selector(f"section[data-screen='{screen}']:not([hidden])")
            quiet(page)
            if screen == "find":
                page.fill("#find-thing", "my glasses")
            page.set_input_files(file_input, str(photo))
            page.wait_for_function(f"document.getElementById('{spot}').textContent.includes('internet')", timeout=30000)
            record(page, "no-internet", screen)
        page.goto(f"http://localhost:{port}/#/scam", wait_until="load")
        page.wait_for_selector("section[data-screen='scam']:not([hidden])")
        quiet(page)
        page.fill("#scam-text", GRANDSON)
        page.click("#scam-check")
        page.wait_for_function("document.getElementById('scam-status').textContent.includes('just now')", timeout=30000)
        record(page, "no-internet", "scam")
        for screen, spot in (("pills", "pills-undo"), ("memories", "memories-status")):
            page.goto(f"http://localhost:{port}/#/{screen}", wait_until="load")
            page.wait_for_selector(f"section[data-screen='{screen}']:not([hidden])")
            page.wait_for_function(f"document.getElementById('{spot}').textContent.includes('just now')", timeout=30000)
            record(page, "no-internet", screen)
        browser.close()
    finally:
        stop(server)


# ---------- microphone: blocked in the browser ----------

def microphone_blocked(playwright) -> None:
    port = 8016
    server = start_server("microphone", port, {"MODEL_API_KEY": ""})
    try:
        # No microphone at all (nothing to ask for).
        browser = playwright.chromium.launch()
        page = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block").new_page()
        open_screen(page, port, "")
        quiet(page)
        page.click("#start-talk")
        page.wait_for_function("document.getElementById('message').textContent.includes('find a microphone')", timeout=30000)
        record(page, "microphone", "none")
        browser.close()
        # A microphone the browser won't allow: the refusal a click on "Block"
        # gives (headless Chromium would leave the question hanging instead).
        browser = playwright.chromium.launch()
        page = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block").new_page()
        page.add_init_script("navigator.mediaDevices.getUserMedia = () => "
                             "Promise.reject(new DOMException('Permission denied', 'NotAllowedError'));")
        open_screen(page, port, "")
        quiet(page)
        page.click("#start-talk")
        page.wait_for_function("document.getElementById('message').textContent.includes('hear you yet')", timeout=30000)
        record(page, "microphone", "blocked")
        open_screen(page, port, "scam")
        quiet(page)
        page.click("#scam-read")
        page.wait_for_function("document.getElementById('scam-status').textContent.includes('hear you yet')", timeout=30000)
        record(page, "microphone", "scam-read-aloud")
        browser.close()
    finally:
        stop(server)


# ---------- slow: Meta takes 6 seconds ----------

def slow_meta(playwright) -> None:
    port = 8017
    server = start_server("slow", port, {"MODEL_API_KEY": ""})
    try:
        browser = playwright.chromium.launch()
        page = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block").new_page()
        open_screen(page, port, "talk")
        quiet(page)

        def slowly(route):
            page.wait_for_timeout(6000)
            route.fulfill(json={"reply": "Sorry to keep you waiting, Rose. What a nice afternoon for it.", "show": None, "actions": []})

        page.route("**/api/chat", slowly)
        # As the talk screen does after her words: thinking until the answer.
        page.evaluate("newExchange('Hello Buddy'); setTalkState('working');"
                      "askBuddy('Hello Buddy').catch(talkProblem).then(function () { setTalkState('idle'); }); 0")
        page.wait_for_function("talkState === 'working'")
        page.wait_for_timeout(2000)
        assert page.get_attribute(".orb--voice", "data-buddy") == "thinking"
        record(page, "slow", "talk-waiting")
        page.wait_for_function("document.getElementById('message').textContent.includes('waiting')", timeout=30000)
        page.wait_for_function("talkState === 'idle'")
        record(page, "slow", "talk-answered")
        page.unroute("**/api/chat")
        open_screen(page, port, "read")
        quiet(page)

        def slowly_read(route):
            page.wait_for_timeout(5000)
            route.fulfill(json={"kind": "bill", "title": "A bill from Riverside Power & Light",
                                "summary": "This is an electricity bill. It says $84.20 is due by November 15, 2026.", "note": "",
                                "facts": [{"label": "Amount due", "value": "$84.20"}], "words": "Riverside Power & Light",
                                "spoken": "This is an electricity bill.", "scam": None})

        page.route("**/api/read", slowly_read)
        page.set_input_files("#read-library", str(PAPERS / "bill.png"))
        page.wait_for_function("document.getElementById('read-status').textContent.includes('reading')", timeout=10000)
        page.wait_for_timeout(1500)
        record(page, "slow", "read-waiting")
        page.wait_for_selector("#read-result:not([hidden])", timeout=30000)
        browser.close()
    finally:
        stop(server)


# ---------- blurry: a very blurry photo, through the real models ----------

def blurry_version(page, photo: Path) -> Path:
    """The photo shrunk to 24 pixels wide and blown back up: a blur."""
    data = "data:image/webp;base64," + base64.b64encode(photo.read_bytes()).decode()
    blurred = page.evaluate("""async (src) => {
        const image = new Image();
        image.src = src;
        await image.decode();
        const tiny = document.createElement('canvas');
        tiny.width = 24; tiny.height = Math.max(1, Math.round(24 * image.height / image.width));
        tiny.getContext('2d').drawImage(image, 0, 0, tiny.width, tiny.height);
        const big = document.createElement('canvas');
        big.width = 1200; big.height = Math.round(1200 * image.height / image.width);
        const paint = big.getContext('2d');
        paint.imageSmoothingEnabled = true; paint.imageSmoothingQuality = 'high';
        paint.drawImage(tiny, 0, 0, big.width, big.height);
        return big.toDataURL('image/jpeg', 0.7);
    }""", data)
    out = OUT / f"blurry-{photo.stem}.jpg"
    out.write_bytes(base64.b64decode(blurred.split(",", 1)[1]))
    return out


def blurry_photos(playwright) -> None:
    from app.config import get_settings

    if not get_settings().model_api_key:
        print("  (no API key in .env: the blurry photos need the real models; skipped)")
        return
    port = 8018
    server = start_server("blurry", port, {})
    try:
        browser = playwright.chromium.launch()
        page = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block").new_page()
        page.goto(f"http://localhost:{port}/", wait_until="load")
        desk = blurry_version(page, PHOTOS / "desk-keys.webp")
        bill = blurry_version(page, PAPERS / "bill.png")
        label = blurry_version(page, PAPERS / "label.png")
        open_screen(page, port, "find")
        quiet(page)
        page.fill("#find-thing", "my glasses")
        with page.expect_response("**/api/find", timeout=120000):
            page.set_input_files("#find-camera", str(desk))
        page.wait_for_function("document.getElementById('find-answer').textContent.trim() !== '' || "
                               "document.getElementById('find-status').textContent.trim() !== ''", timeout=30000)
        page.wait_for_timeout(1300)
        record(page, "blurry", "find")
        open_screen(page, port, "read")
        quiet(page)
        with page.expect_response("**/api/read", timeout=120000):
            page.set_input_files("#read-library", str(bill))
        page.wait_for_selector("#read-result:not([hidden])", timeout=30000)
        record(page, "blurry", "read")
        open_screen(page, port, "scam")
        quiet(page)
        with page.expect_response("**/api/scam-check", timeout=120000):
            page.set_input_files("#scam-photo-input", str(bill))
        page.wait_for_selector("#scam-result:not([hidden])", timeout=30000)
        record(page, "blurry", "scam-photo")
        open_screen(page, port, "pills")
        quiet(page)
        with page.expect_response("**/api/meds/label", timeout=120000):
            page.set_input_files("#pill-photo-input", str(label))
        page.wait_for_timeout(500)
        record(page, "blurry", "pill-label", scroll_to="#pill-photo-status")
        open_screen(page, port, "memories")
        quiet(page)
        with page.expect_response("**/api/memories/photo", timeout=120000):
            page.set_input_files("#memory-photo-input", str(desk))
        page.wait_for_timeout(1500)
        record(page, "blurry", "old-photo")
        browser.close()
    finally:
        stop(server)


# ---------- offline: the server has stopped ----------

def server_stopped(playwright) -> None:
    port = 8019
    server = start_server("offline", port, {"MODEL_API_KEY": ""})
    try:
        browser = playwright.chromium.launch()
        page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()  # the service worker is allowed here
        page.goto(f"http://localhost:{port}/", wait_until="networkidle")
        # The page registers its service worker itself; wait until it is in
        # charge and has kept the shell, the offline page among it.
        page.wait_for_function("navigator.serviceWorker.ready.then(() => true)", timeout=20000)
        page.wait_for_function("caches.match('/static/offline.html').then(found => !!found)", timeout=20000)
        page.reload(wait_until="networkidle")  # now under the worker's control
        stop(server)
        # The worker serves the Home it kept, so Buddy still opens; the talk
        # screen then says it can't reach the internet, with the calls.
        page.goto(f"http://localhost:{port}/", wait_until="load")
        page.wait_for_selector("#start-talk", timeout=15000)
        page.wait_for_timeout(1500)
        record(page, "offline", "home-kept")
        page.goto(f"http://localhost:{port}/#/talk", wait_until="load")
        page.wait_for_selector("section[data-screen='talk']:not([hidden])", timeout=15000)
        quiet(page)
        talk_with(page, "Hello Buddy", "reach the internet")
        record(page, "offline", "talk")
        browser.close()
    finally:
        if server.poll() is None:
            stop(server)


def main(args: list[str]) -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(exist_ok=True)
    parts = [args[args.index("--only") + 1]] if "--only" in args else PARTS
    runs = {"meta-down": meta_down, "no-internet": no_internet, "microphone": microphone_blocked, "slow": slow_meta,
            "blurry": blurry_photos, "offline": server_stopped}
    with sync_playwright() as playwright:
        for part in parts:
            print(f"\n=== {part}")
            runs[part](playwright)
    problems = [(part, what, technical) for part, what, _, technical in report if technical]
    (OUT / "failures-check.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFailure check: {'PROBLEMS FOUND ' + str(problems) if problems else 'OK'} "
          f"({len(report)} states, screenshots in test-output/fail-*.png)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
