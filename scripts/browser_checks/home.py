# scripts/browser_checks/home.py
# Opens the home screen in a real browser, talks to it with a fake
# microphone, checks the layout, and saves screenshots to test-output/.
#
# Run it by hand: .venv\Scripts\python scripts\browser_checks\home.py
# Needs no API key and never calls Meta: the speech-to-text answer is faked.
# It starts its own test server on port 8001.

import os
import struct
import subprocess
import tempfile
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "test-output"
PORT = 8001


def wait_for_server(timeout_seconds: int = 60) -> None:
    """Wait until the test server answers /api/ping."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://localhost:{PORT}/api/ping", timeout=2) as reply:
                if reply.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("test server never started")


# Runs inside the browser and returns a list of layout problems (empty = good).
LAYOUT_PROBLEMS_JS = """() => {
  const problems = [];
  const root = document.documentElement;
  if (root.scrollWidth > root.clientWidth) {
    problems.push(`sideways scrolling: ${root.scrollWidth} > ${root.clientWidth}`);
  }
  // An icon squeezed by long words gets narrower than it is tall.
  document.querySelectorAll("button .icon").forEach((icon) => {
    const box = icon.getBoundingClientRect();
    if (box.width < box.height - 1) {
      problems.push(`squashed icon on "${icon.parentElement.textContent.trim()}"`);
    }
  });
  // Words must stay inside their button, even with the biggest words.
  // Measures each line of text itself (decorations like the plate's rings
  // may reach outside a button on purpose).
  document.querySelectorAll("button").forEach((button) => {
    const box = button.getBoundingClientRect();
    const walker = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let spilled = false;
    while (walker.nextNode() && !spilled) {
      if (!walker.currentNode.textContent.trim()) continue;
      range.selectNodeContents(walker.currentNode);
      for (const line of range.getClientRects()) {
        if (line.left < box.left - 1 || line.right > box.right + 1) spilled = true;
      }
    }
    if (spilled) {
      problems.push(`words spill out of "${button.textContent.trim()}"`);
    }
  });
  // Stars must stay beside the page column, never behind the words.
  const page = document.querySelector(".page").getBoundingClientRect();
  document.querySelectorAll(".sparkle").forEach((star) => {
    const box = star.getBoundingClientRect();
    const onScreen = box.right > 0 && box.left < root.clientWidth;
    if (onScreen && box.right > page.left && box.left < page.right) {
      problems.push(`star behind the words at x=${Math.round(box.left)}`);
    }
  });
  return problems;
}"""


def check_wav(upload: bytes) -> None:
    """The recording the page uploaded must be a 16 kHz mono 16-bit WAV."""
    start = upload.find(b"RIFF")
    assert start >= 0, "no WAV file in the upload"
    fields = struct.unpack("<4sI4s4sIHHIIHH4sI", upload[start : start + 44])
    riff, _, wave, fmt, _, audio_format, channels, rate, _, _, bits, data, data_size = fields
    assert (riff, wave, fmt, data) == (b"RIFF", b"WAVE", b"fmt ", b"data"), f"bad WAV header: {fields}"
    assert (audio_format, channels, rate, bits) == (1, 1, 16000, 16), f"wrong WAV format: {fields}"
    assert data_size > 16000, f"recording too short: {data_size} bytes"  # over half a second


def check_layout(page, where: str) -> None:
    """Fail if the page scrolls sideways, an icon is squashed, or a star sits behind words."""
    problems = page.evaluate(LAYOUT_PROBLEMS_JS)
    assert not problems, f"layout problems at {where}: {problems}"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    # The test server gets its own throwaway database and no API key, so a
    # browser check can never touch her real data or call the real AI.
    temp_folder = tempfile.mkdtemp(prefix="buddy-check-")
    test_env = dict(os.environ, DATABASE_PATH=str(Path(temp_folder) / "check.db"), MODEL_API_KEY="")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=ROOT,
        env=test_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server()

        from playwright.sync_api import sync_playwright

        problems: list[str] = []
        with sync_playwright() as playwright:
            # A fake microphone that plays a beep, with permission already given.
            browser = playwright.chromium.launch(
                args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
            )
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900}, permissions=["microphone"])
                page.on("console", lambda msg: problems.append(msg.text) if msg.type == "error" else None)
                page.on("pageerror", lambda err: problems.append(str(err)))

                page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
                page.wait_for_timeout(1200)  # let the entrance animations finish
                page.screenshot(path=str(OUT / "home-desktop.png"))
                check_layout(page, "desktop")

                # Talk: tap, "speak" for a moment, tap again, and her words appear.
                # The server's answer is faked here, so Meta is never called.
                uploads = []

                def fake_transcribe(route):
                    uploads.append(route.request.post_data_buffer)
                    route.fulfill(json={"transcript": "Maria is coming on Sunday"})

                page.route("**/api/transcribe", fake_transcribe)
                # Buddy's AI reply is faked too, with an "Add to doctor notes" button.
                page.route("**/api/chat", lambda route: route.fulfill(json={
                    "reply": "What a lovely visit! When is she coming?",
                    "show": None,
                    "actions": [{"type": "add_question", "label": "Add to doctor notes", "question": "Is it okay to walk more?"}],
                }))
                page.click("#talk-button")
                page.wait_for_selector("#talk-button[data-state='listening']")
                assert "Listening" in (page.text_content("#message") or "")
                page.wait_for_timeout(1500)
                page.screenshot(path=str(OUT / "home-listening.png"))
                page.click("#talk-button")
                page.wait_for_selector("#you-said:not([hidden])")
                said = page.text_content("#you-said-text") or ""
                assert said == "Maria is coming on Sunday", f"unexpected words shown: {said!r}"
                page.wait_for_selector("#talk-button[data-state='idle']")
                check_wav(uploads[0])
                buddy = " ".join((page.text_content("#message") or "").split())
                assert buddy == "What a lovely visit! When is she coming?", f"Buddy's reply not shown: {buddy!r}"
                page.wait_for_timeout(1300)  # let Buddy's words finish appearing
                page.screenshot(path=str(OUT / "home-you-said.png"))
                # "Add to doctor notes" saves the question (the real route, test database).
                page.click("#actions button")
                page.wait_for_selector("#actions button:has-text('Added to doctor notes')")

                # The safety net, end to end: she says an emergency warning sign
                # (faked speech-to-text), the real /api/chat answers with no AI,
                # and the red full-screen message with Call 911 appears.
                safety_page = browser.new_page(viewport={"width": 390, "height": 844}, permissions=["microphone"])
                safety_page.on("pageerror", lambda err: problems.append(str(err)))
                safety_page.route("**/api/transcribe", lambda route: route.fulfill(json={"transcript": "my chest feels really tight"}))
                safety_page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
                safety_page.click("#talk-button")
                safety_page.wait_for_selector("#talk-button[data-state='listening']")
                safety_page.wait_for_timeout(600)
                safety_page.click("#talk-button")
                safety_page.wait_for_selector("#safety-screen[open][data-kind='emergency']")
                message = safety_page.text_content("#safety-message") or ""
                assert message == "This could be an emergency. If it is, please call 911 right now.", message
                assert safety_page.get_attribute("#safety-actions a", "href") == "tel:911"
                safety_page.wait_for_timeout(500)  # let the screen finish fading in
                safety_page.screenshot(path=str(OUT / "safety-emergency.png"))
                safety_page.click("#safety-close")
                assert not safety_page.is_visible("#safety-screen"), "the safety screen did not close"
                # Behind it, the Call 911 button stays under Buddy's words.
                assert safety_page.get_attribute("#actions a", "href") == "tel:911"

                # Phone width: nothing cut off, no sideways scrolling.
                phone = browser.new_page(viewport={"width": 375, "height": 812})
                phone.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
                phone.wait_for_timeout(1200)
                phone.screenshot(path=str(OUT / "home-375px.png"))
                check_layout(phone, "375px")

                # The Words button grows the text, twice = biggest, still no overflow.
                phone.click("#text-size-button")
                phone.click("#text-size-button")
                phone.wait_for_timeout(300)
                size_note = phone.text_content("#message") or ""
                assert "biggest" in size_note, f"words did not grow: {size_note!r}"
                phone.screenshot(path=str(OUT / "home-375px-big.png"), full_page=True)
                check_layout(phone, "375px with biggest words")

                # Her choice is remembered: after a reload the words are still biggest.
                phone.reload(wait_until="networkidle")
                label = phone.text_content("#text-size-label") or ""
                assert label == "Smaller words", f"words size not remembered: {label!r}"

                # 200% browser zoom on a 1280px screen shows 640 CSS px: same check.
                zoomed = browser.new_page(viewport={"width": 640, "height": 900})
                zoomed.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
                zoomed.wait_for_timeout(1200)
                zoomed.screenshot(path=str(OUT / "home-zoom200.png"))
                check_layout(zoomed, "200% zoom")
            finally:
                browser.close()

        if problems:
            print("BROWSER ERRORS FOUND:")
            for problem in problems:
                print(" -", problem)
            return 1

        print("Home check OK: talking works (16 kHz mono WAV sent, words shown), no layout problems. Screenshots in test-output/.")
        return 0
    finally:
        server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
