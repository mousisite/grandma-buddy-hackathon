# scripts/browser_checks/home.py
# Opens the app in a real browser, talks to it with a fake microphone,
# checks every flow and the layout, and saves screenshots to test-output/.
#
# Run it by hand: .venv\Scripts\python scripts\browser_checks\home.py
# Needs no API key and never calls Meta: the speech-to-text answer is faked.
# It starts its own test server on port 8001.

import json
import os
import re
import struct
from datetime import datetime, timedelta
import subprocess
import tempfile
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "test-output"
PORT = 8001
SCREENS = ["today", "talk", "diary", "pills", "notes", "scam", "find", "read", "family", "memories", "settings", "help"]
SIZES = [(390, 844), (768, 1024), (1440, 900)]  # phone, tablet, desktop


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
  document.querySelectorAll("button .icon, a .icon").forEach((icon) => {
    const box = icon.getBoundingClientRect();
    if (box.width < box.height - 1) {
      problems.push(`squashed icon on "${icon.parentElement.textContent.trim()}"`);
    }
  });
  // Every button and link is at least 44px tall (docs/DESIGN.md), except a
  // link inside a sentence, like "call 911" in the note at the bottom.
  document.querySelectorAll("button, a").forEach((target) => {
    if (!target.getClientRects().length || getComputedStyle(target).display === "inline") return;
    const height = target.getBoundingClientRect().height;
    if (height < 43.5) problems.push(`too small to tap (${Math.round(height)}px): "${target.textContent.trim()}"`);
  });
  // Words must stay inside their button, link, or label, even with the
  // largest text. Measures each line of text itself.
  document.querySelectorAll("button, a, label").forEach((button) => {
    if (!button.getClientRects().length) return; // hidden screens
    const box = button.getBoundingClientRect();
    const walker = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let spilled = false;
    while (walker.nextNode() && !spilled) {
      if (!walker.currentNode.textContent.trim()) continue;
      if (walker.currentNode.parentElement.closest(".visually-hidden")) continue; // screen readers only
      range.selectNodeContents(walker.currentNode);
      for (const line of range.getClientRects()) {
        if (line.left < box.left - 1 || line.right > box.right + 1) spilled = true;
      }
    }
    if (spilled) {
      problems.push(`words spill out of "${button.textContent.trim()}"`);
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


def let_presses_settle(page) -> None:
    """Wait until nothing just tapped is still moving. A pressed button is
    squeezed (0.96) and springs back over 220ms after the press lets go (a
    44px chip measures 42px meanwhile), and the circle of light it spreads
    (.ripple, twice its size, gone after 700ms) widens its scrollWidth as it
    grows. Measuring during either gives a false "too small" or "spills"."""
    page.wait_for_function(
        "!document.querySelector('[data-pressed], .ripple') && document.getAnimations().every(a => "
        "!(a instanceof CSSTransition && a.transitionProperty === 'transform' && a.playState === 'running'))",
        timeout=3000,
    )


def check_layout(page, where: str) -> None:
    """Fail if the page scrolls sideways, an icon is squashed, a target is
    too small, or words spill out."""
    let_presses_settle(page)
    problems = page.evaluate(LAYOUT_PROBLEMS_JS)
    assert not problems, f"layout problems at {where}: {problems}"


def shown_screen(page) -> str:
    """The name of the one screen on show (all the others must be hidden)."""
    shown = page.eval_on_selector_all("section[data-screen]:not([hidden])", "els => els.map(e => e.dataset.screen)")
    assert len(shown) == 1, f"expected one screen on show, got {shown}"
    return shown[0]


def wait_for_screen(page, screen: str) -> None:
    """Wait until the screen is on show and its View Transition (the
    cross-fade, or the orb's morph) has finished."""
    page.wait_for_function(f"document.querySelector('section[data-screen={screen}]').hidden === false")
    page.wait_for_function(
        "document.getAnimations().every(a => !String(a.effect && a.effect.pseudoElement).startsWith('::view-transition'))"
    )


def visit(page, screen: str) -> None:
    """Open a screen by its address. A new address on the same page swaps
    screens inside a View Transition, a moment later, so wait for it."""
    page.goto(f"http://localhost:{PORT}/#/{screen}", wait_until="networkidle")
    wait_for_screen(page, screen)


def go_today(page) -> None:
    """Back to Home like she would: Done in voice mode, otherwise Home in
    the tab bar (phone) or the sidebar (tablet and up)."""
    screen = shown_screen(page)
    if screen == "talk":
        page.click(".voice-done")
    elif screen != "today":
        page.click("[data-nav='today']:visible")
    wait_for_screen(page, "today")


def open_screen(page, screen: str, title: str) -> None:
    """Open a screen like she would: from the tab bar or sidebar, or for
    Check a message and Doctor notes, from Home."""
    if shown_screen(page) == "talk":
        go_today(page)  # voice mode has no tab bar
    if screen in ("diary", "pills", "family", "settings"):
        page.click(f"[data-nav='{screen}']:visible")
    else:
        go_today(page)
        page.click(f"[data-screen='today'] a[href='#/{screen}']")
    page.wait_for_function(f"document.title === '{title} · Grandma Buddy'")
    assert shown_screen(page) == screen
    current = page.get_attribute(f"[data-nav='{screen}']:visible", "aria-current") if screen in ("diary", "pills", "family", "settings") else "page"
    assert current == "page", f"the tab for {screen} should be marked current"


def part_of_day(hour: int) -> str:
    """The same rule as app/reminders.py and static/app.js."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    return "evening" if 17 <= hour < 21 else "night"


def check_talk(page, uploads: list) -> None:
    """Talk to Buddy on Home opens voice mode listening; her words and
    Buddy's reply show; the reply shows reading progress as it is read; the
    last exchange moves to "Earlier"; tapping the orb when idle goes back."""
    page.click("#start-talk")
    page.wait_for_selector("#talk-button[data-state='listening']")
    assert shown_screen(page) == "talk"
    page.wait_for_function("document.querySelector('.orb--voice').dataset.buddy === 'listening'")
    assert page.text_content("#buddy-label") == "I’m listening"
    assert page.text_content("#talk-label") == "I’m done"
    assert not page.is_visible(".tabbar") and not page.is_visible(".sidebar"), "voice mode is the whole screen"
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "talk-listening.png"))
    page.click("#talk-button")
    page.wait_for_selector("#you-said:not([hidden])")
    said = page.text_content("#you-said-text") or ""
    assert said == "Maria is coming on Sunday", f"unexpected words shown: {said!r}"
    page.wait_for_selector("#talk-button[data-state='idle']")
    check_wav(uploads[0])
    buddy = " ".join((page.text_content("#message") or "").split())
    assert buddy == "What a lovely visit! When is she coming?", f"Buddy's reply not shown: {buddy!r}"
    # Reading progress: up to word 2 of the reply ("lovely") is read.
    said_words = page.evaluate(
        "lastSpoken = document.getElementById('message').dataset.text; highlightWord(2);"
        "[...document.querySelectorAll('#message .word.said')].map(w => w.textContent)"
    )
    assert said_words == ["What", "a", "lovely"], said_words
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / "talk-reply.png"))
    page.evaluate("clearHighlight()")
    # "Add to doctor notes" saves the question (the real route, test database).
    page.click("#actions button")
    page.wait_for_selector("#actions button:has-text('Added to doctor notes')")
    page.wait_for_selector(".toast:has-text('Added to doctor notes')")
    # A second exchange: the first moves to "Earlier". The orb says "I'm done" too.
    page.click("#talk-button")
    page.wait_for_selector("#talk-button[data-state='listening']")
    page.wait_for_timeout(600)
    page.click(".orb--voice", force=True)  # it swells with her voice, so it never holds still
    page.wait_for_selector("#earlier-section:not([hidden])")
    earlier = page.text_content("#earlier li") or ""
    assert "Maria is coming on Sunday" in earlier, earlier
    check_layout(page, "voice mode, desktop")
    # Tapping the orb when Buddy is idle closes voice mode.
    page.wait_for_selector("#talk-button[data-state='idle']")
    page.click(".orb--voice")
    wait_for_screen(page, "today")


def check_settings_form(page, problems: list[str]) -> None:
    """Settings: switches and choices save at once (with a toast); the
    profile saves with its button, a refused entry is named and focused,
    unsaved entries are kept; the theme, text size, voice speed, and Calm
    motion all work."""
    open_screen(page, "settings", "Settings")
    focused = page.evaluate("document.activeElement.id")
    assert focused == "settings-title", f"focus should move to the heading, not {focused!r}"
    # The names and numbers are folded away for a family member: open them.
    assert not page.is_visible("#set-preferred-name"), "the profile should start folded away"
    page.click("#profile-setup summary")

    # Made-up demo people only.
    page.fill("#set-preferred-name", "Rose")
    page.fill("#set-family-name", "Maria")
    page.fill("#set-family-phone", "555-0100")
    page.fill("#set-doctor-name", "Dr. Lee")
    page.fill("#set-doctor-phone", "soon")  # not a phone number
    page.click("#settings-form button[type=submit]")
    page.wait_for_selector("#set-doctor-phone[aria-invalid='true']")
    # The note sits right under the refused entry and says how to fix it.
    note = page.text_content("#set-doctor-phone + .field-problem") or ""
    assert note == "Please check the doctor’s phone number. Use numbers, like 555‑0123.", note
    assert page.evaluate("document.activeElement.id") == "set-doctor-phone", "the refused entry should get focus"
    page.screenshot(path=str(OUT / "settings-refused-entry.png"))
    # The browser logs that refusal as an error. It was expected: remove it.
    problems.remove("Failed to load resource: the server responded with a status of 400 (Bad Request)")

    # Going Home and returning keeps what was typed but not saved.
    go_today(page)
    open_screen(page, "settings", "Settings")
    assert page.input_value("#set-family-name") == "Maria", "unsaved entries were lost"

    # A choice saves at once, without touching the unsaved profile entries.
    page.click("#settings-form label:has-text('Slower')")
    page.wait_for_selector(".toast:has-text('Settings saved')")
    assert page.input_value("#set-family-name") == "Maria", "a switch must not undo typed entries"

    page.fill("#set-doctor-phone", "555-0199")
    page.click("#settings-form button[type=submit]")
    page.wait_for_selector(".toast:has-text('Profile saved')")
    assert not page.query_selector(".field-problem"), "the old problem note should be gone after saving"
    page.screenshot(path=str(OUT / "settings-desktop.png"), full_page=True)
    check_layout(page, "Settings screen, desktop")

    # Buddy's voice: the natural voices first (when set up on this computer),
    # then this browser's own, best first; the Edge hint only when all of
    # them are robotic; her choice is kept on this device.
    voices = page.eval_on_selector_all("#voice-choice option", "options => options.map(o => o.value)")
    natural = page.evaluate("naturalVoice.available")
    assert page.is_visible("#voice-hint") == (not natural and page.evaluate("onlyRoboticVoices()"))
    if natural:
        assert voices[0] == "natural:af_heart", voices
        assert page.evaluate("chosenNatural()") == "af_heart", "the natural voice should be the default"
        # A busy computer can take longer than the page's 6 seconds to make a
        # sentence (then the page rightly uses the browser voice). Here the
        # check is about the page playing the natural voice, so give it time.
        page.evaluate("NATURAL_WAIT_MS = 60000")
        page.select_option("#voice-choice", "natural:af_bella")
        assert page.evaluate("chosenNatural()") == "af_bella"
        # Choosing it says a few words in it: made on this computer, played by the page.
        page.wait_for_function("naturalAudio !== null && !naturalAudio.paused", timeout=60000)
        page.click("#voice-try")
        page.wait_for_function("naturalAudio !== null && !naturalAudio.paused", timeout=60000)
        page.evaluate("stopSpeaking()")
        page.evaluate("NATURAL_WAIT_MS = 6000")
    browser_voices = [value for value in voices if not value.startswith("natural:")]
    if len(browser_voices) > 1:
        assert browser_voices[0] == page.evaluate("englishVoices()[0].name")
        page.select_option("#voice-choice", browser_voices[1])
        assert page.evaluate("localStorage.getItem('buddy-voice')") == browser_voices[1]
        assert page.evaluate("pickVoice(), chosenVoice.name") == browser_voices[1], "the chosen voice wasn't kept"
        assert page.evaluate("chosenNatural()") == "", "a chosen browser voice should be used"
    page.select_option("#voice-choice", voices[0])  # back to the best one
    page.evaluate("stopSpeaking()")

    # Calm motion: on, and the whole page stops moving; off again.
    page.check("input[name=calm_mode]")
    page.wait_for_function("document.documentElement.hasAttribute('data-calm')")
    page.uncheck("input[name=calm_mode]")
    page.wait_for_function("!document.documentElement.hasAttribute('data-calm')")

    # Theme: Dark, then back to Auto (this browser says light).
    page.click("#settings-form label:has-text('Dark')")
    page.wait_for_function("document.documentElement.dataset.theme === 'dark'")
    page.wait_for_function("profile.theme === 'dark'")
    page.screenshot(path=str(OUT / "settings-dark-desktop.png"))
    page.click("#settings-form label:has-text('Auto')")
    page.wait_for_function("document.documentElement.dataset.theme === 'light'")
    page.wait_for_function("profile.theme === 'auto'")

    # Family now has big call buttons for Maria, Daniel (from the welcome), and Dr. Lee.
    open_screen(page, "family", "Family")
    hrefs = page.eval_on_selector_all("#family-calls a", "links => links.map(a => a.getAttribute('href'))")
    assert hrefs == ["tel:555-0100", "tel:555-0144", "tel:555-0199"], hrefs
    assert page.text_content("#family-calls a") == "Call Maria"
    assert not page.is_visible("#family-calls-empty")
    page.screenshot(path=str(OUT / "family-desktop.png"))
    check_layout(page, "Family screen, desktop")

    # The browser's Back button returns, and Home greets her by name.
    go_today(page)
    greeting = page.text_content("#greeting") or ""
    assert greeting.endswith(", Rose"), f"greeting should use her name: {greeting!r}"
    # A fresh visit to Settings shows what was saved, Slower included.
    page.goto(f"http://localhost:{PORT}/#/settings", wait_until="networkidle")
    page.wait_for_function("document.querySelector('#set-family-name').value === 'Maria'")
    assert page.is_checked("input[name=voice_rate][value='0.75']"), "the voice speed was not remembered"


def check_diary_talk(page) -> None:
    """"Something hurts" from the empty Diary screen: Buddy asks what she
    feels in voice mode, her answer goes to /api/chat in diary mode with its
    own conversation id, and diary mode ends once the entry is saved."""
    sent = []

    def fake_chat(route):
        sent.append(route.request.post_data_json)
        route.fulfill(json={"reply": "I've written that down for your doctor.", "show": None,
                            "actions": [], "diary_saved": True, "diary_done": True})

    page.unroute("**/api/chat")
    page.route("**/api/chat", fake_chat)
    open_screen(page, "diary", "My diary")
    page.wait_for_selector("#diary-status:not([hidden])")
    assert "Nothing written down in the last 30 days" in (page.text_content("#diary-status") or "")
    assert page.is_visible("text=I’m an AI helper. I can’t give medical advice.")
    page.screenshot(path=str(OUT / "diary-empty.png"))

    page.click("[data-screen='diary'] [data-start-diary]")
    wait_for_screen(page, "talk")
    page.wait_for_function("document.querySelector('#message').textContent.includes('Tell me what you’re feeling')")
    assert page.text_content("#talk-hint") == "Buddy is writing in your diary"
    page.click("#talk-button")
    page.wait_for_selector("#talk-button[data-state='listening']")
    page.wait_for_timeout(600)
    page.click("#talk-button")
    page.wait_for_function("document.querySelector('#talk-hint').textContent === 'Buddy writes down what you say'")
    assert sent[-1]["mode"] == "diary", sent[-1]
    assert "-diary-" in sent[-1]["conversation_id"], sent[-1]
    page.wait_for_selector(".toast:has-text('Saved to diary')")


def check_memory_talk(page) -> None:
    """The Memory book from Home's chip: empty at first; "Tell Buddy a
    memory" asks for one in voice mode, her answer goes to /api/chat in
    memory mode with its own conversation id, and memory mode ends once it
    is saved. In ordinary talk, "Save it in my memory book" saves it."""
    sent, saved = [], []

    def fake_chat(route):
        sent.append(route.request.post_data_json)
        if sent[-1]["mode"] == "memory":
            route.fulfill(json={"reply": "I'm writing that into your memory book, and painting a picture for it.",
                                "show": None, "memory_saved": 1, "memory_done": True,
                                "actions": [{"type": "open", "screen": "memories", "label": "Open my memory book"}]})
        else:
            route.fulfill(json={"reply": "What a lovely memory. Would you like it in your memory book?", "show": None,
                                "actions": [{"type": "memory", "label": "Save it in my memory book"}]})

    def fake_save(route):
        saved.append(route.request.post_data_json)
        route.fulfill(json={"id": 1})

    page.unroute("**/api/chat")
    page.route("**/api/chat", fake_chat)
    page.route("**/api/memories", lambda route: fake_save(route) if route.request.method == "POST" else route.continue_())
    open_screen(page, "memories", "Memory book")
    page.wait_for_selector("#memories-status:not([hidden])")
    assert "Your memory book is empty" in (page.text_content("#memories-status") or "")

    page.click("[data-start-memory]")
    wait_for_screen(page, "talk")
    page.wait_for_function("document.querySelector('#message').textContent.includes('one of your memories')")
    assert page.text_content("#talk-hint") == "Buddy is listening for your memory book"
    page.click("#talk-button")
    page.wait_for_selector("#talk-button[data-state='listening']")
    page.wait_for_timeout(600)
    page.click("#talk-button")
    page.wait_for_function("document.querySelector('#talk-hint').textContent === 'Buddy writes down what you say'")
    assert sent[-1]["mode"] == "memory", sent[-1]
    assert "-memory-" in sent[-1]["conversation_id"], sent[-1]
    page.wait_for_selector(".toast:has-text('Saved to your memory book')")
    assert page.is_visible("#actions button:has-text('Open my memory book')")

    # Ordinary talk: Buddy offers the button, and it saves this talk's memory.
    page.click("#talk-button")
    page.wait_for_selector("#talk-button[data-state='listening']")
    page.wait_for_timeout(600)
    page.click("#talk-button")
    page.click("#actions button:has-text('Save it in my memory book')")
    page.wait_for_selector("#actions button:has-text('Open my memory book')")
    assert saved[-1]["conversation_id"] == sent[-1]["conversation_id"] and sent[-1]["mode"] == "chat", (saved, sent)
    page.click("#actions button:has-text('Open my memory book')")
    wait_for_screen(page, "memories")
    page.unroute("**/api/memories")


def check_friend(browser, database: str) -> None:
    """Buddy as a friend. Settings shows what Buddy learned (a note on how
    she likes to talk, a fact about her life); "Forget this" asks first and
    Undo brings it back. And "Talk to Buddy" at the start of a conversation
    greets her by name with a follow-up that is due, then listens."""
    import sqlite3

    now = datetime.now()
    connection = sqlite3.connect(database)
    stamp = now.isoformat(timespec="seconds")
    connection.execute("INSERT INTO style_notes (created_at, note) VALUES (?, 'Loves a good pun')", (stamp,))
    connection.execute("INSERT INTO facts (created_at, updated_at, kind, fact, follow_up, follow_up_on) "
                       "VALUES (?, ?, 'event', 'Her grandson Tom visits on Sunday', 'Did Tom make it on Sunday?', ?)",
                       (stamp, stamp, now.date().isoformat()))
    # Her last talk was three hours ago: the next one starts a conversation.
    earlier = (now - timedelta(hours=3)).isoformat(timespec="seconds")
    connection.execute("UPDATE messages SET created_at = ? WHERE created_at > ?", (earlier, earlier))
    connection.commit()
    connection.close()

    page = browser.new_page(viewport={"width": 390, "height": 844}, permissions=["microphone"])
    page.route("**/api/transcribe", lambda route: route.fulfill(json={"transcript": ""}))
    visit(page, "settings")
    page.click("#learned-setup summary")
    page.wait_for_selector("#learned-facts >> text=Her grandson Tom visits on Sunday")
    assert page.is_visible("#learned-notes >> text=Loves a good pun")
    page.eval_on_selector("#learned-setup", "details => details.scrollIntoView()")
    # Measured once its rows have finished rising in (they start at 98% size).
    page.wait_for_function("document.querySelector('#learned-setup .for-family-body').getAnimations()"
                           ".every(a => a.playState === 'finished')")
    page.screenshot(path=str(OUT / "settings-learned-390.png"))
    check_layout(page, "What Buddy has learned")
    page.click("#learned-facts button:has-text('Forget this')")
    page.wait_for_selector("#confirm-dialog[open]")
    assert page.text_content("#confirm-title") == "Forget this?"
    page.click("#confirm-yes")
    page.wait_for_selector("#learned-facts >> text=Her grandson Tom visits on Sunday", state="detached")
    page.click("#learned-undo button:has-text('Undo')")
    page.wait_for_selector("#learned-facts >> text=Her grandson Tom visits on Sunday")

    # The greeting, then listening once Buddy has finished speaking. It asks
    # the oldest follow-up that's due: the demo week's, about Leo.
    page.click("[data-nav='today']:visible")
    wait_for_screen(page, "today")
    page.click("#start-talk")
    wait_for_screen(page, "talk")
    page.wait_for_function("document.getElementById('message').textContent.includes('Did Leo come by on Sunday?')")
    assert (page.text_content("#message") or "").startswith("Good "), "the greeting says good morning, afternoon, or evening"
    page.wait_for_selector("#talk-button[data-state='listening']", timeout=30000)
    page.screenshot(path=str(OUT / "greeting-390.png"))
    page.close()


def check_pills(page, problems: list[str]) -> None:
    """Pills, with the real server and a pill due right now: a refused entry
    is named; the reminder card repeats the label exactly; "I took it" and
    "Remind me in 10 minutes" work; the ring counts; Home follows; Change,
    and Remove with "Are you sure?" and Undo, work; the round check works."""
    now = datetime.now()
    time_now = now.strftime("%H:%M")
    part = part_of_day(now.hour)

    open_screen(page, "pills", "My pills")
    page.wait_for_selector("#pills-today-status:not([hidden])")
    assert "No pills set up yet" in (page.text_content("#pills-today-status") or "")
    # "Set up pills" is folded away for a family member: open it.
    assert not page.is_visible("#pill-name"), "the setup should start folded away"
    page.click("#pills-setup summary")

    # No time chosen: refused, and the note sits under the time box.
    page.fill("#pill-name", "Lisinopril")
    page.fill("#pill-label", "10 mg tablet, take 1 by mouth daily")
    page.click("#pill-save")
    page.wait_for_selector("#pill-times .field-problem")
    problems.remove("Failed to load resource: the server responded with a status of 400 (Bad Request)")

    # Due now: Buddy says it with her name, and the card repeats the label
    # exactly as typed.
    page.fill("#pill-form .time-input", time_now)
    page.click("#pill-save")
    page.wait_for_selector("#pill-banner:not([hidden])")
    words = page.text_content("#pill-banner-words") or ""
    assert words == f"Rose, it’s time for your {part} Lisinopril.", words
    labels = page.eval_on_selector_all(
        "#pill-banner-labels li", "items => items.map(i => [...i.querySelectorAll('p')].map(p => p.textContent))")
    assert labels == [["Lisinopril", "10 mg tablet, take 1 by mouth daily"]], labels
    assert page.text_content("#pill-taken") == "I took it"
    # Spoken one sentence at a time, but a dose like "0.5 mg" is never split.
    parts = page.evaluate("sentencesOf('It’s time for your morning pills: Lorazepam, 0.5 mg tablet; Take 1.5 daily.')")
    assert parts == ["It’s time for your morning pills: Lorazepam, 0.5 mg tablet;", "Take 1.5 daily."], parts
    # Brought into view, even though the page was scrolled down to the form.
    page.wait_for_function("document.getElementById('pill-banner').getBoundingClientRect().top >= 0")
    top = page.evaluate("document.getElementById('pill-banner').getBoundingClientRect().top")
    assert top < 200, f"the card should be on screen, top={top}"
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "pills-banner-desktop.png"))
    check_layout(page, "pill reminder, desktop")
    page.click("#pill-taken")
    page.wait_for_selector("#pill-banner", state="hidden")
    page.wait_for_selector(".toast:has-text('Marked as taken')")
    assert "Taken at" in (page.text_content("#pills-today .check-row--taken .pill-status") or "")
    assert page.text_content("#pills-ring-count") == "1" and page.text_content("#pills-ring-total") == "1"

    # A second pill: "Remind me in 10 minutes".
    page.fill("#pill-name", "Vitamin D")
    page.fill("#pill-label", "1 softgel daily")
    page.fill("#pill-form .time-input", time_now)
    page.click("#pill-save")
    page.wait_for_selector("#pill-banner:not([hidden])")
    page.click("#pill-snooze")
    page.wait_for_selector("#pill-banner", state="hidden")
    assert "Reminding you again at" in (page.text_content("#pills-today .check-row--snoozed .pill-status") or "")
    assert page.text_content("#pills-ring-count") == "1" and page.text_content("#pills-ring-total") == "2"

    # The line on Home follows.
    go_today(page)
    summary = page.text_content("#pills-summary") or ""
    assert summary.startswith("Pill reminder again at"), summary
    open_screen(page, "pills", "My pills")

    # Change a label.
    page.click("[aria-label='Change Vitamin D']")
    assert page.text_content("#pill-form-title") == "Change Vitamin D"
    page.fill("#pill-label", "2 softgels daily")
    page.click("#pill-save")
    page.wait_for_selector("#pills-list .pill-label:has-text('2 softgels daily')")

    # Remove: "Keep it" keeps it; "Yes, remove it" removes it; Undo brings it back.
    page.click("[aria-label='Remove Vitamin D']")
    page.wait_for_selector("#confirm-dialog[open]")
    assert page.evaluate("document.activeElement.id") == "confirm-no", "the cursor should start on Keep it"
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "pills-confirm.png"))
    page.click("#confirm-no")
    assert page.is_visible("[aria-label='Remove Vitamin D']")
    page.click("[aria-label='Remove Vitamin D']")
    page.click("#confirm-yes")
    page.wait_for_selector("#pills-undo:has-text('Removed Vitamin D.')")
    page.wait_for_selector("[aria-label='Remove Vitamin D']", state="detached")  # the list redraws a moment later
    page.click("#pills-undo button")
    page.wait_for_selector("#pills-undo:has-text('Vitamin D is back.')")
    page.wait_for_selector("[aria-label='Remove Vitamin D']")
    # Vitamin D is due again: its own round check in today's list.
    page.click("[aria-label='I took this one: Vitamin D']")
    page.wait_for_selector("#pill-banner", state="hidden")
    page.wait_for_function("document.getElementById('pills-ring-count').textContent === '2'")
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "pills-desktop.png"), full_page=True)
    check_layout(page, "Pills screen, desktop")


def check_home_hero(browser) -> None:
    """Home opens on the greeting, the date, and the whole orb (above the
    tab bar on a phone), with the orb moving: Calm motion starts off. The
    daily check-in is the first row of the Today list. Home has one Talk to
    Buddy button; the sidebar's comes back on the other screens. With
    reduced motion the orb is still there, standing still."""
    for theme, width, height in [("light", 390, 844), ("dark", 390, 844), ("light", 1440, 900), ("dark", 1440, 900)]:
        page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme, reduced_motion="no-preference")
        page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
        page.wait_for_function("document.getElementById('today-check-in').textContent === 'Not done yet'")
        page.wait_for_timeout(1200)  # let Buddy wake up
        page.screenshot(path=str(OUT / f"home-hero-{width}-{theme}.png"))
        check_layout(page, f"Home at {width}px, {theme}")
        orb = page.locator(".hero-orb .orb").bounding_box()
        greeting = page.locator("#greeting").bounding_box()
        bottom = page.locator(".tabbar").bounding_box()["y"] if width < 768 else height
        assert greeting["y"] < orb["y"] and orb["y"] >= 0 and orb["y"] + orb["height"] <= bottom, \
            f"the whole orb should show under the greeting without scrolling at {width}px: {orb}"
        assert not page.evaluate("document.documentElement.hasAttribute('data-calm')"), "Calm motion should start off"
        moving = page.evaluate("getComputedStyle(document.querySelector('.hero-orb .orb-blob')).animationName")
        assert moving != "none", "the orb should move on Home"
        first_row = page.locator(".today .row:not([hidden])").first  # no town here: no weather row
        assert first_row.locator(".row-title").text_content() == "Daily check-in"
        assert first_row.locator("[data-start-check-in]").text_content() == "Start"
        talk = page.get_by_role("button", name="Talk to Buddy", exact=True)
        assert talk.count() == 1 and talk.get_attribute("id") == "start-talk", "Home should have one Talk to Buddy button"
        if width >= 768:
            assert not page.is_visible(".sidebar-talk"), "the sidebar's Talk to Buddy should hide on Home"
            page.click("[data-nav='diary']:visible")
            wait_for_screen(page, "diary")
            assert page.is_visible(".sidebar-talk"), "the sidebar's Talk to Buddy should be back on other screens"
        page.close()

    calm = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    calm.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
    calm.wait_for_timeout(600)
    assert calm.evaluate("document.documentElement.hasAttribute('data-calm')"), "reduced motion should turn on Calm motion"
    assert calm.is_visible(".hero-orb .orb-core"), "the orb should still be there with reduced motion"
    still = calm.evaluate("getComputedStyle(document.querySelector('.hero-orb .orb-blob')).animationName")
    assert still == "none", f"the orb should stand still with reduced motion, not {still!r}"
    calm.screenshot(path=str(OUT / "home-hero-390-reduced-motion.png"))
    calm.close()


def check_check_in(browser) -> None:
    """The daily check-in: "Start" in the Today list opens voice mode with
    Buddy's opening question, sends her answer in "check_in" mode with the
    check-in's own conversation, and goes back to ordinary talk when she
    leaves voice mode."""
    sent = []

    def fake_chat(route):
        sent.append(route.request.post_data_json)
        route.fulfill(json={"reply": "I'm glad. Does anything hurt or feel different today?", "show": None,
                            "actions": [], "diary_saved": False, "diary_done": False})

    page = browser.new_page(viewport={"width": 390, "height": 844}, permissions=["microphone"])
    page.route("**/api/transcribe", lambda route: route.fulfill(json={"transcript": "I'm feeling pretty good"}))
    page.route("**/api/chat", fake_chat)
    page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
    page.click(".row [data-start-check-in]")
    wait_for_screen(page, "talk")
    page.wait_for_function("document.getElementById('message').textContent.includes('How are you feeling today?')")
    assert (page.text_content("#message") or "").startswith("Good "), "the opening greets her"
    assert page.text_content("#talk-hint") == "Your daily check-in"
    page.click("#talk-button")
    page.wait_for_selector("#talk-button[data-state='listening']")
    page.wait_for_timeout(600)
    page.click("#talk-button")
    page.wait_for_function("document.getElementById('message').textContent.includes('Does anything hurt')")
    assert sent[-1]["mode"] == "check_in", sent[-1]
    assert sent[-1]["conversation_id"].endswith("-check-in"), sent[-1]
    page.screenshot(path=str(OUT / "check-in-talk-390.png"))
    check_layout(page, "check-in in voice mode")
    # Leaving voice mode ends the check-in.
    page.click(".voice-done")
    wait_for_screen(page, "today")
    assert page.evaluate("talkMode") == "chat", "the check-in should end when she leaves voice mode"
    page.close()


GRANDSON_SCAM = "Grandma it's me, I'm in jail, send $2,000 in gift cards and don't tell mom"


def check_scam(browser) -> None:
    """Check a message, with the real /api/scam-check. The test server has no
    API key, so the AI is "down" and the plain rules answer (as they would
    with no internet). Paste, read it out loud (faked speech-to-text), and a
    photo; the verdict card with words and an icon, the fixed "what to do",
    the call buttons, and "Check another message"."""
    for theme, width, height in [("light", 390, 844), ("dark", 1440, 900)]:
        page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme,
                                permissions=["microphone"])
        page.route("**/api/transcribe", lambda route: route.fulfill(json={"transcript": GRANDSON_SCAM}))
        visit(page, "scam")
        # Nothing to check yet: a kind nudge.
        page.click("#scam-check")
        page.wait_for_selector("#scam-status:has-text('Please paste the message')")

        # Pasted: the gift-card scam.
        page.fill("#scam-text", GRANDSON_SCAM)
        page.click("#scam-check")
        page.wait_for_selector("#scam-result:not([hidden])")
        assert page.text_content("#scam-verdict") == "Likely scam"
        assert page.locator("#scam-verdict .icon").count() == 1, "a verdict needs its icon, never color alone"
        assert page.evaluate("document.activeElement.id") == "scam-verdict"
        todo = page.eval_on_selector_all("#scam-todo li", "items => items.map(i => i.textContent)")
        assert todo[0] == "Don't click links, reply, or call numbers in the message.", todo
        assert len(todo) == 3
        hrefs = page.eval_on_selector_all("#scam-actions a", "links => links.map(a => a.getAttribute('href'))")
        assert "tel:18333728311" in hrefs, hrefs
        page.click("#scam-paid summary")
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / f"scam-verdict-{width}-{theme}.png"), full_page=True)
        check_layout(page, f"scam verdict at {width}px, {theme}")

        # "Check another message": an empty box, ready to type.
        page.click("#scam-another")
        assert page.input_value("#scam-text") == ""
        assert page.evaluate("document.activeElement.id") == "scam-text"

        if width == 390:
            # Read it out loud: her voice is written down, then checked.
            page.click("#scam-read")
            page.wait_for_selector("#scam-read-label:has-text('I’m done reading')")
            page.wait_for_timeout(600)
            page.click("#scam-read")
            page.wait_for_selector("#scam-result:not([hidden])")
            assert page.text_content("#scam-verdict") == "Likely scam"
            assert page.input_value("#scam-text") == GRANDSON_SCAM
            page.click("#scam-another")

            # A photo: with the AI down, Buddy can't read it, so it says so.
            picture = OUT / "scam-photo-sample.png"
            page.screenshot(path=str(picture), clip={"x": 0, "y": 0, "width": 390, "height": 300})
            page.set_input_files("#scam-photo-input", str(picture))
            page.wait_for_selector("#scam-result:not([hidden])")
            assert page.text_content("#scam-verdict") == "Suspicious"
            assert (page.text_content("#scam-explanation") or "").startswith("I'm not sure about this one.")
            assert page.is_visible("#scam-checked-photo")
            page.wait_for_timeout(500)  # the card has finished rising in
            page.screenshot(path=str(OUT / "scam-photo-390.png"), full_page=True)
        page.close()


def found_in_the_middle(route) -> None:
    """A stand-in for /api/find (no AI here): her thing is in the middle of
    whatever photo the page sent, in that photo's own pixels."""
    sent = route.request.post_data_json
    width, height = sent["width"], sent["height"]
    route.fulfill(json={
        "found": True, "thing": "keys", "sentence": "Your keys are on the counter, next to the fruit bowl.",
        "box": {"x1": width * 4 // 10, "y1": height * 4 // 10, "x2": width * 6 // 10, "y2": height * 6 // 10},
        "width": width, "height": height,
    })


ONE_LINE_JS = """sel => [...document.querySelectorAll(sel)].filter(b => b.offsetParent).filter(b => {
  const words = [...b.childNodes].find(n => n.nodeType === 3 && n.textContent.trim()) || b.querySelector('span');
  const range = document.createRange();
  range.selectNodeContents(words);
  const lines = new Set([...range.getClientRects()].filter(r => r.width > 1).map(r => Math.round(r.top))).size;
  return lines !== 1 || b.scrollWidth > b.clientWidth + 1;
}).map(b => b.textContent.trim())"""


def one_line_buttons(page, selector: str, where: str) -> None:
    """Every button's words on one line, none cut off ("Take a photo" must
    never wrap; the buttons hide overflow, so check_layout can't see it)."""
    let_presses_settle(page)
    broken = page.evaluate(ONE_LINE_JS, selector)
    assert not broken, f"button words wrap or spill at {where}: {broken}"


def check_find(browser) -> None:
    """Find my things, with /api/find faked (the real SAM 3.1 runs only in
    scripts/check_find.py): the Home chip, "say what you're looking for
    first", a quick pick, a photo, then the halo, Buddy's sentence (the
    photo's description, with focus on it), and the buttons; nothing found;
    the safety net on her words (real, no AI); and "Buddy, where are my
    glasses?" opening Find with "glasses" filled in."""
    painted = ROOT / "scripts" / "find_photos" / "kitchen.webp"
    for theme, width, height in [("light", 390, 844), ("dark", 1440, 900)]:
        page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
        visit(page, "today")
        page.click(".chips a[href='#/find']")
        wait_for_screen(page, "find")
        picture = painted if painted.exists() else OUT / "find-photo-sample.png"
        if not painted.exists():
            page.screenshot(path=str(picture), clip={"x": 0, "y": 0, "width": 390, "height": 300})
        # No photo before she says what she's looking for.
        page.click("#find-ask button[type=submit]")
        page.wait_for_selector("#find-ask-problem")
        page.click("[data-find-pick='keys']")
        assert page.input_value("#find-thing") == "keys"
        assert page.get_attribute("[data-find-pick='keys']", "aria-pressed") == "true"
        check_layout(page, f"find, asking at {width}px")
        one_line_buttons(page, ".find-actions .pill-button", f"find at {width}px")

        page.route("**/api/find", found_in_the_middle)
        page.set_input_files("#find-camera", str(picture))
        page.wait_for_selector("#find-after:not([hidden])")
        page.wait_for_timeout(1200)  # the halo has finished drawing
        assert page.get_attribute("#find-photo", "data-state") == "found"
        assert page.locator("#find-halo .find-ring").count() == 1
        sentence = "Your keys are on the counter, next to the fruit bowl."
        assert page.text_content("#find-answer") == sentence
        assert page.get_attribute("#find-image", "alt") == sentence, "a screen reader hears where it is"
        assert page.evaluate("document.activeElement.id") == "find-answer"
        check_layout(page, f"find, found at {width}px")
        one_line_buttons(page, ".find-actions .pill-button", f"find, found at {width}px")
        page.screenshot(path=str(OUT / f"find-found-{width}-{theme}.png"), full_page=True)

        # Nothing found: no halo, a kind sentence, and "Try another photo".
        page.unroute("**/api/find")
        page.route("**/api/find", lambda route: route.fulfill(json={
            "found": False, "thing": "keys",
            "sentence": "I couldn't spot your keys in this photo. Could you take another one, maybe from a different "
                        "spot with the lights on?"}))
        page.set_input_files("#find-camera", str(picture))
        page.wait_for_function("document.getElementById('find-photo').dataset.state === 'missing'")
        assert page.locator("#find-halo ellipse").count() == 0
        assert page.is_visible("#find-retake")
        page.unroute("**/api/find")

        if width == 390:
            # The safety net first (the real route; no AI is needed for it).
            page.click("#find-other")
            page.fill("#find-thing", "I took my pills twice by accident")
            page.set_input_files("#find-camera", str(picture))
            page.wait_for_selector("#safety-screen[open][data-kind='poison_control']")
            page.click("#safety-close")
            # "Buddy, where are my glasses?" gives a "Find my glasses" button (voice mode).
            visit(page, "talk")
            page.evaluate("showActions([{type: 'find', thing: 'glasses', label: 'Find my glasses'}])")
            page.click("#actions button:has-text('Find my glasses')")
            wait_for_screen(page, "find")
            assert page.input_value("#find-thing") == "glasses"
            assert page.get_attribute("[data-find-pick='glasses']", "aria-pressed") == "true"
        page.close()


# Stand-ins for /api/read (no AI here), shaped like app/reader.py's answers,
# for the made-up papers scripts/check_read.py photographs.
READ_BILL_SAYS = "This is your electric bill for October. It says you owe $84.20, to be paid by November 15, 2026."
READ_BILL = {
    "kind": "bill", "title": "A bill from Riverside Power & Light", "summary": READ_BILL_SAYS, "note": "",
    "facts": [{"label": "Amount due", "value": "$84.20"}, {"label": "Pay by", "value": "November 15, 2026"}],
    "words": "Riverside Power & Light\nPO Box 4410, Portland, OR\nRose Demo\nAccount number a long number\n"
             "Statement date October 28, 2026\nElectricity used in October 612 kWh\nAmount due $84.20\n"
             "Please pay by November 15, 2026\nPay online at riversidepower.example/pay-your-bill-online-with-autopay, "
             "by phone, or by mail. Thank you for being our customer.",
    "spoken": READ_BILL_SAYS, "scam": None,
}
READ_CLINIC_NOTE = ("This looks like a letter about your health from Riverside Family Clinic. I can read it to you "
                    "word for word. If you have questions about it, Dr. Lee is the right person to ask.")
READ_CLINIC = {
    "kind": "medical", "title": "A letter about your health from Riverside Family Clinic", "summary": "",
    "note": READ_CLINIC_NOTE, "facts": [],
    "words": "Riverside Family Clinic. Dr. Lee. Dear Rose Demo, Your lab results from October 20 are ready. "
             "Total cholesterol: 212 mg/dL. LDL: 141 mg/dL. Please call our office to talk about these results at "
             "your next visit on November 3 at 2 PM. Sincerely, Riverside Family Clinic.",
    "spoken": READ_CLINIC_NOTE, "scam": None,
}
READ_SCAM_SAYS = ("It says you won $5,000 and asks you to send a $50 processing fee in gift cards within 24 hours, "
                  "and to call the number.")
READ_SCAM = {
    "kind": "letter", "title": "A letter from National Prize Center", "summary": READ_SCAM_SAYS, "note": "",
    "facts": [],  # a likely scam's "fee" is never shown as an amount due
    "words": "NATIONAL PRIZE CENTER. Official Winner Notice. CONGRATULATIONS! YOU HAVE WON $5,000! To claim your "
             "prize, send a $50 processing fee in gift cards within 24 hours. Call the number now. Do not tell "
             "anyone until your prize arrives.",
    "spoken": READ_SCAM_SAYS + " It has signs of a scam.",
    "scam": {"verdict": "likely_scam", "flags": ["Asks to be paid with gift cards", "Asks you to keep it secret",
                                                  "Pushes you to act right now", "Says you won a prize"]},
}
READ_UNREADABLE = {
    "kind": "unreadable", "title": "", "summary": "", "facts": [], "words": "", "scam": None,
    "note": "I couldn’t read this one. Could you take another photo, a little closer, with good light?",
    "spoken": "I couldn’t read this one. Could you take another photo, a little closer, with good light?",
}


def paper_photo(name: str, page) -> Path:
    """A made-up paper's photo from scripts/check_read.py, or a stand-in."""
    photo = ROOT / "scripts" / "read_docs" / f"{name}.png"
    if not photo.exists():
        photo = OUT / "read-photo-sample.png"
        page.screenshot(path=str(photo), clip={"x": 0, "y": 0, "width": 390, "height": 500})
    return photo


def read_paper(page, name: str, answer: dict) -> None:
    """Take a photo of a paper; /api/read answers with the stand-in."""
    page.unroute("**/api/read")
    page.route("**/api/read", lambda route: route.fulfill(json=answer))
    page.set_input_files("#read-camera", str(paper_photo(name, page)))
    page.wait_for_selector("#read-result:not([hidden])")
    page.wait_for_timeout(500)  # the card has finished rising in


def check_read(browser) -> None:
    """Read it to me on the demo week, with /api/read faked (the real Muse
    Spark runs only in scripts/check_read.py): the Home chip, the orb on the
    photo while Buddy reads it, a bill (what it is, the amount and the date,
    focus on the title), word for word with Stop, a health letter (never
    explained, doctor's call first), a likely scam (the warning in words,
    Check it for a scam runs the real scam checker with the words, Back
    keeps the paper), a photo it can't read, and Meta down."""
    for theme, width, height in [("light", 390, 844), ("dark", 1440, 900)]:
        page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
        visit(page, "today")
        page.click(".chips a[href='#/read']")
        wait_for_screen(page, "read")
        check_layout(page, f"read, start at {width}px")
        one_line_buttons(page, ".read-start .pill-button", f"read at {width}px")

        # While Buddy reads it: the photo, quiet, with the orb thinking on top.
        held = []
        page.route("**/api/read", lambda route: held.append(route))
        page.set_input_files("#read-camera", str(paper_photo("bill", page)))
        page.wait_for_selector("#read-photo:not([hidden])")
        for _ in range(100):
            if held:
                break
            page.wait_for_timeout(100)
        assert held, "the photo was never sent to /api/read"
        assert held[0].request.post_data_json["image"].startswith("data:image/jpeg;base64,")
        assert page.text_content("#read-status") == "Buddy is reading it…"
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / f"read-reading-{width}-{theme}.png"))
        held[0].fulfill(json=READ_BILL)

        # A bill: what it is, what it says, the amount and the date.
        page.wait_for_selector("#read-result:not([hidden])")
        page.wait_for_timeout(500)
        assert page.is_hidden("#read-photo") and page.is_hidden("#read-start")
        assert page.text_content("#read-kind") == "A bill from Riverside Power & Light"
        assert page.text_content("#read-summary") == READ_BILL_SAYS
        facts = page.eval_on_selector_all("#read-facts > div", "rows => rows.map(r => r.innerText.replace(/\\s+/g, ' '))")
        assert facts == ["Amount due $84.20", "Pay by November 15, 2026"], facts
        assert page.is_hidden("#read-scam") and page.is_hidden("#read-text")
        assert page.evaluate("document.activeElement.id") == "read-kind"
        assert page.text_content("#read-more a") == "Call Maria", "a bill: call her family"
        check_layout(page, f"read, a bill at {width}px")
        one_line_buttons(page, ".read-result .find-actions .pill-button", f"read, a bill at {width}px")
        page.screenshot(path=str(OUT / f"read-bill-{width}-{theme}.png"), full_page=True)

        # Word for word: the words show big under the button, which stays where
        # her finger is and says Stop while they are read.
        before = page.locator("#read-words").bounding_box()
        page.click("#read-words")
        assert page.text_content("#read-text") == READ_BILL["words"]
        after = page.locator("#read-words").bounding_box()
        assert abs(after["y"] - before["y"]) < 1, "the Stop button must not move under her finger"
        lines = page.evaluate("document.getElementById('read-text').innerText.split('\\n').length")
        assert lines == 9, f"the paper's 9 lines show as lines, not {lines}"
        said = page.evaluate("linesToSay(readAnswer.words)")
        assert said.startswith("Riverside Power & Light. PO Box 4410, Portland, OR. Rose Demo."), said
        check_layout(page, f"read, word for word at {width}px")  # a long link never pushes the page sideways
        assert page.text_content("#read-words-label") == "Stop reading"
        page.click("#read-words")
        assert page.text_content("#read-words-label") == "Read it word for word"
        assert page.is_visible("#read-text"), "the words stay on the screen"

        # A letter about her health: never explained; her doctor's call button first.
        page.click("#read-another")
        assert page.evaluate("document.activeElement.id") == "read-title"
        read_paper(page, "clinic", READ_CLINIC)
        assert page.text_content("#read-summary") == READ_CLINIC_NOTE
        assert page.is_hidden("#read-facts") and page.is_hidden("#read-scam")
        assert page.eval_on_selector_all("#read-more a", "links => links.map(l => l.textContent)") == ["Call Dr. Lee", "Call Maria"]
        assert page.get_attribute("#read-more a", "href") == "tel:555-0199"
        page.screenshot(path=str(OUT / f"read-clinic-{width}-{theme}.png"), full_page=True)

        # A likely scam: the warning in words and an icon.
        page.click("#read-another")
        read_paper(page, "scam", READ_SCAM)
        assert page.is_visible("#read-scam")
        assert page.eval_on_selector_all("#read-scam-flags li", "items => items.length") == 4
        check_layout(page, f"read, a scam at {width}px")
        page.screenshot(path=str(OUT / f"read-scam-{width}-{theme}.png"), full_page=True)

        if width == 390:
            # Check it for a scam: the real scam checker (no AI here), with the words.
            page.click("#read-check-scam")
            wait_for_screen(page, "scam")
            page.wait_for_selector("#scam-result:not([hidden])")
            assert page.input_value("#scam-text") == READ_SCAM["words"]
            assert page.text_content("#scam-verdict") == "Likely scam"
            # Back: the paper is still there.
            page.go_back()
            wait_for_screen(page, "read")
            assert page.is_visible("#read-result")
            assert page.text_content("#read-kind") == "A letter from National Prize Center"

            # A photo it can't read: only Take another photo.
            page.click("#read-another")
            read_paper(page, "bill", READ_UNREADABLE)
            assert page.is_hidden("#read-kind") and page.is_hidden("#read-words") and page.is_hidden("#read-check-scam")
            assert page.is_visible("#read-retake")
            assert page.text_content("#read-summary") == READ_UNREADABLE["note"]

            # Meta down: a kind word, and the photo buttons again.
            page.click("#read-another")
            page.unroute("**/api/read")
            page.route("**/api/read", lambda route: route.fulfill(
                status=503, json={"detail": "I couldn’t read it just now. Please try again in a moment."}))
            page.set_input_files("#read-camera", str(paper_photo("bill", page)))
            page.wait_for_function("document.getElementById('read-status').textContent.startsWith('I couldn’t')")
            assert page.is_visible("#read-take") and page.is_hidden("#read-photo")
        page.close()


def check_landing(browser) -> None:
    """The landing (/about), Privacy, and Terms, for the family member who
    sets Buddy up: at phone and desktop width, light and dark, every picture
    loads, the questions open, Open Buddy goes to the app, and no layout
    problems (the same 44px targets and no sideways scrolling as the app)."""
    for theme, width, height in [("light", 390, 844), ("dark", 1440, 900)]:
        page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
        page.goto(f"http://localhost:{PORT}/about", wait_until="networkidle")
        assert page.title().startswith("Grandma Buddy")
        assert page.get_attribute("html", "data-theme") == theme
        # The lower screens load as she scrolls (and sideways, on a phone):
        # ask for all of them now, then every picture must be there.
        page.evaluate("[...document.images].forEach(i => { i.loading = 'eager'; })")
        page.wait_for_function("[...document.images].every(i => i.complete)")
        broken = page.evaluate("[...document.images].filter(i => !i.naturalWidth).map(i => i.src)")
        assert not broken, f"pictures that didn't load: {broken}"
        assert page.locator(".closing .orb .orb-core").count() == 1, "Buddy's orb should be alive at the end"
        first = page.locator(".faq-item").first
        first.locator("summary").click()
        assert first.locator(".faq-answer").is_visible()
        assert page.locator("a.pill-button[href='/']").first.text_content().strip() == "Open Buddy"
        check_layout(page, f"the landing at {width}px, {theme}")
        page.screenshot(path=str(OUT / f"landing-{width}-{theme}.png"), full_page=True)
        for name in ("privacy", "terms"):
            page.goto(f"http://localhost:{PORT}/{name}", wait_until="networkidle")
            assert page.locator("h1").text_content().startswith(name.capitalize())
            check_layout(page, f"{name} at {width}px, {theme}")
            page.screenshot(path=str(OUT / f"{name}-{width}-{theme}.png"), full_page=True)
        page.close()

    # From the app: Help links to the three pages.
    page = browser.new_page(viewport={"width": 390, "height": 844})
    visit(page, "help")
    assert page.eval_on_selector_all(".help-links a", "links => links.map(l => l.getAttribute('href'))") == \
        ["/about", "/privacy", "/terms"]
    check_layout(page, "Help's links at 390px")
    page.close()


# A stand-in for the browser's Notification, which a test browser can't show:
# it writes down each one instead, and always gives permission.
NOTIFICATION_STUB = """
  window.notified = [];
  class FakeNotification {
    constructor(title, options) {
      this.title = title;
      window.notified.push({ title: title, body: (options || {}).body || "" });
    }
    addEventListener() {}
    close() {}
    static requestPermission() { return Promise.resolve("granted"); }
    static get permission() { return "granted"; }
  }
  window.Notification = FakeNotification;
"""


def check_family_accounts(browser) -> None:
    """Family accounts on the demo week. Rose's Settings: the seeded Maria,
    an invite code, her sharing switches. The family page in a second
    browser (Daniel's own phone): joining with the code, her day as she
    shares it, Yesterday's missed pill, a notification for a new alert,
    sign out, a wrong password, sign in. Rose's side: a pill reminder as a
    notification while Buddy is hidden. Then Remove ends Daniel's session."""
    rose = browser.new_page(viewport={"width": 390, "height": 844})
    rose.add_init_script(NOTIFICATION_STUB)
    visit(rose, "settings")
    rose.evaluate("document.getElementById('family-setup').open = true")
    rose.wait_for_selector("#family-accounts .group-row")
    assert "Maria" in (rose.text_content("#family-accounts") or ""), "the demo week has Maria's account"
    rose.click("#family-invite")
    rose.wait_for_selector("#family-invite-card:not([hidden])")
    code = (rose.text_content("#family-invite-code") or "").strip()
    assert re.fullmatch(r"[A-HJ-NP-Z]{6}", code), code
    # She keeps her mood to herself for now (the demo week shares her diary).
    rose.click("#settings-form label:has-text('Her mood')")
    rose.wait_for_function("profile.share_mood === false")  # saved (a toast may still be an older one)
    check_layout(rose, "Settings, Family accounts at 390px")
    rose.screenshot(path=str(OUT / "settings-family-390.png"), full_page=True)

    daniel = browser.new_page(viewport={"width": 390, "height": 844})  # a new browser: his own phone
    daniel.add_init_script(NOTIFICATION_STUB)
    daniel.goto(f"http://localhost:{PORT}/family", wait_until="networkidle")
    daniel.wait_for_selector("#family-signin:not([hidden])")
    daniel.click("#show-join")
    daniel.wait_for_selector("#family-join:not([hidden])")
    daniel.fill("#join-code", code)
    daniel.fill("#join-name", "Daniel")
    daniel.fill("#join-email", "daniel@example.com")
    daniel.fill("#join-password", "blueberries-1958")
    daniel.click("#join-form button[type=submit]")
    daniel.wait_for_selector("#family-day:not([hidden])")
    daniel.wait_for_function("document.getElementById('day-title').textContent === 'Rose’s day'")
    assert re.search(r"\d+ of \d+ taken|No pill reminders", daniel.text_content("#pills") or "")
    assert (daniel.text_content("#mood") or "").startswith("Rose hasn’t shared her mood")
    daniel.wait_for_selector("#diary-list .entry")
    assert "My knee feels much better today" in (daniel.text_content("#diary-list") or "")
    check_layout(daniel, "the family page, today at 390px")
    daniel.screenshot(path=str(OUT / "family-today-390.png"), full_page=True)

    # Yesterday: the missed Lisinopril needs a look.
    daniel.click("#family-day label:has-text('Yesterday')")
    daniel.wait_for_selector("#alerts:not([hidden])")
    daniel.wait_for_function("document.getElementById('alerts-list').textContent.includes('Lisinopril')")
    assert "Missed: Lisinopril at 8:00 AM" in (daniel.text_content("#alerts-list") or "")
    check_layout(daniel, "the family page, yesterday at 390px")
    daniel.screenshot(path=str(OUT / "family-yesterday-390.png"), full_page=True)

    # A new alert while the page is open: a notification on his device.
    daniel.click("#family-day label:has-text('Today')")
    daniel.wait_for_function("document.querySelector('input[name=family-day]:checked').value === '0'")
    daniel.click("#notify-switch")
    daniel.wait_for_function("localStorage.getItem('buddy-family-notify') === 'on'")

    def with_a_new_alert(route):
        body = route.fetch().json()
        body["alerts"].append({"time": "9:41 PM", "words": "Missed: Metformin at 9:41 PM"})
        route.fulfill(json=body)

    daniel.route("**/api/family/dashboard*", with_a_new_alert)
    daniel.evaluate("loadDay()")
    daniel.wait_for_function("window.notified.length > 0")
    note = daniel.evaluate("window.notified[0]")
    assert note["title"] == "Rose needs a look" and "Metformin at 9:41 PM" in note["body"], note
    daniel.unroute("**/api/family/dashboard*")

    # Sign out; a wrong password is refused kindly; the right one signs in.
    daniel.click("#sign-out")
    daniel.wait_for_selector("#family-signin:not([hidden])")
    daniel.fill("#signin-email", "daniel@example.com")
    daniel.fill("#signin-password", "not-it")
    daniel.click("#signin-form button[type=submit]")
    daniel.wait_for_function("document.getElementById('signin-status').textContent === 'That email and password don’t match.'")
    daniel.fill("#signin-password", "blueberries-1958")
    daniel.click("#signin-form button[type=submit]")
    daniel.wait_for_selector("#family-day:not([hidden])")

    # The sign-in page on a desktop, dark.
    wide = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    wide.goto(f"http://localhost:{PORT}/family", wait_until="networkidle")
    wide.wait_for_selector("#family-signin:not([hidden])")
    wide.click("#show-join")
    check_layout(wide, "the family page, joining at 1440px, dark")
    wide.screenshot(path=str(OUT / "family-join-1440-dark.png"), full_page=True)
    wide.close()

    # Rose: a pill reminder as a notification while Buddy is hidden.
    rose.click("#settings-form label:has-text('Remind me even when Buddy is hidden')")
    rose.wait_for_function("profile.notify_hidden === true")  # saved once the (stubbed) permission is given

    def due_now(route):
        body = route.fetch().json()
        if body["reminders"]:
            body["reminders"][0]["status"] = "due"
        else:
            body["reminders"] = [{"id": 1, "medication_id": 1, "due_at": "2026-10-30T18:00:00", "status": "due",
                                  "snooze_until": None, "acted_at": None, "name": "Metformin", "label_dose": "500 mg tablet"}]
        body["due_title"] = "Rose, it’s time for your evening Metformin."
        body["due_words"] = body["due_title"]
        body["has_pills"] = True
        route.fulfill(json=body)

    rose.route("**/api/reminders", due_now)
    rose.evaluate("Object.defineProperty(document, 'hidden', { get: () => true, configurable: true }); loadReminders()")
    rose.wait_for_function("window.notified.length > 0")
    first = rose.evaluate("window.notified[0]")
    assert first["title"] == "Rose, it’s time for your evening Metformin.", first
    rose.unroute("**/api/reminders")

    # Remove Daniel's account from her Settings: his session ends at once.
    rose.reload(wait_until="networkidle")  # a fresh list (Daniel joined after it was drawn)
    wait_for_screen(rose, "settings")
    rose.evaluate("document.getElementById('family-setup').open = true")
    remove = "#family-accounts button[aria-label='Remove Daniel’s account']"
    rose.wait_for_selector(remove)
    rose.click(remove)
    rose.wait_for_selector("#confirm-dialog[open]")
    rose.click("#confirm-yes")
    rose.wait_for_function(f"!document.querySelector(\"{remove}\")")
    daniel.evaluate("loadDay()")
    daniel.wait_for_selector("#family-signin:not([hidden])")
    # Her mood is shared again for the checks that follow.
    rose.click("#settings-form label:has-text('Her mood')")
    rose.wait_for_function("profile.share_mood === true")
    daniel.close()
    rose.close()


def check_billing(browser) -> None:
    """The Family plan on the family page, in demo mode (the test server has
    no Stripe key): Maria signs in, sees the Free plan, taps Start, gets the
    demo box with NO card fields, starts the plan, then cancels it at the
    end of the period."""
    maria = browser.new_page(viewport={"width": 390, "height": 844})
    maria.goto(f"http://localhost:{PORT}/family", wait_until="networkidle")
    maria.wait_for_selector("#family-signin:not([hidden])")
    maria.fill("#signin-email", "maria@example.com")
    maria.fill("#signin-password", "rose-garden-2026")  # the demo week's made-up password
    maria.click("#signin-form button[type=submit]")
    maria.wait_for_selector("#family-day:not([hidden])")
    maria.wait_for_function("document.getElementById('plan-name').textContent === 'Free plan'")
    assert "Demo mode" in (maria.text_content("#plan-words") or "")
    maria.click("#plan-start")
    maria.wait_for_selector("#plan-demo:not([hidden])")
    assert maria.locator("#billing input").count() == 0, "no card fields, ever"
    assert maria.text_content("#plan-demo .plan-demo-title") == "Demo mode, no real charge"
    check_layout(maria, "the Family plan's demo box at 390px")
    maria.screenshot(path=str(OUT / "family-plan-demo-390.png"), full_page=True)
    maria.click("#plan-demo-start")
    maria.wait_for_function("document.getElementById('plan-name').textContent.startsWith('Family plan (demo mode')")
    assert (maria.text_content("#plan-words") or "").startswith("Renews on ")
    assert maria.is_visible("#plan-cancel") and maria.is_hidden("#plan-start")
    maria.click("#plan-cancel")
    maria.wait_for_selector("#plan-cancel-ask:not([hidden])")
    maria.click("#plan-cancel-yes")
    maria.wait_for_function("document.getElementById('plan-words').textContent.startsWith('It stays on until ')")
    assert maria.text_content("#plan-status") == "Cancelled."
    assert maria.is_hidden("#plan-cancel")
    check_layout(maria, "the Family plan, cancelled, at 390px")
    maria.screenshot(path=str(OUT / "family-plan-390.png"), full_page=True)
    maria.close()


def seed_demo_week(database: str) -> None:
    """Fill the test server's database with the made-up demo week
    (scripts/seed_demo.py --reset, which keeps a backup first; no paintings)."""
    env = dict(os.environ, DATABASE_PATH=database)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_demo.py"), "--reset", "--no-paint"], cwd=ROOT,
                   env=env, check=True, stdout=subprocess.DEVNULL)


def say_it(page, form: str, heard: str) -> None:
    """ "Say it" in the welcome, with the fake microphone, and the words
    the fake speech-to-text hears."""
    page.unroute("**/api/transcribe")
    page.route("**/api/transcribe", lambda route: route.fulfill(json={"transcript": heard}))
    page.click(f"{form} [data-say-it]")
    page.wait_for_selector(f"{form} [data-say-it][data-state='listening']")
    page.wait_for_timeout(600)
    page.click(f"{form} [data-say-it]")
    page.wait_for_selector(f"{form} [data-say-it][data-state='idle']")


def check_welcome(browser) -> None:
    """The first time (no name saved), the welcome opens instead of Home:
    no tab bar; "Let's begin", then her name (said: "My name is Rose"), her
    family (typed, and said: "My son Daniel, 555 0144"; a refused number is
    named under its field), and pills Later. Then Home greets her by name.
    "Say it" goes through the safety net first: a crisis phrase shows the
    crisis screen."""
    wide = browser.new_page(viewport={"width": 1440, "height": 900}, permissions=["microphone"])
    wide.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
    wait_for_screen(wide, "welcome")
    wide.wait_for_timeout(800)
    wide.screenshot(path=str(OUT / "welcome-0-1440.png"))
    wide.click("#welcome-begin")
    wide.wait_for_selector("#welcome-name-form:not([hidden])")
    # (A crisis phrase: it is never stored, so later checks find an empty diary.)
    say_it(wide, "#welcome-name-form", "I wish I wasn't here anymore")
    wide.wait_for_selector("#safety-screen[open][data-kind='crisis']")
    wide.click("#safety-close")
    wide.screenshot(path=str(OUT / "welcome-1-1440.png"))
    check_layout(wide, "welcome at 1440px")
    wide.close()

    page = browser.new_page(viewport={"width": 390, "height": 844}, permissions=["microphone"])
    page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
    wait_for_screen(page, "welcome")
    assert not page.is_visible(".tabbar"), "the welcome is the whole screen"
    assert page.is_visible(".footnote-call"), "call 911 stays one tap away"
    page.wait_for_timeout(800)
    page.screenshot(path=str(OUT / "welcome-0-390.png"))
    check_layout(page, "welcome, the start")
    page.click("#welcome-begin")
    assert page.text_content("#welcome-count") == "Step 1 of 3"
    assert not page.is_visible("#welcome-back"), "no Back on the first question"
    say_it(page, "#welcome-name-form", "My name is Rose")
    assert page.input_value("#welcome-name") == "Rose"
    page.screenshot(path=str(OUT / "welcome-1-390.png"))
    check_layout(page, "welcome, her name")
    page.click("#welcome-name-form button[type=submit]")
    page.wait_for_selector("#welcome-family-form:not([hidden])")
    assert "Who should I call" in (page.text_content("#welcome-title") or "")
    assert page.text_content("#welcome-count") == "Step 2 of 3"
    # Back (top left) returns to her name, still filled in; Next comes back here.
    back = page.locator("#welcome-back").bounding_box()
    assert back and back["height"] >= 48 and back["y"] < 120, f"Back is a big target at the top: {back}"
    page.click("#welcome-back")
    page.wait_for_selector("#welcome-name-form:not([hidden])")
    assert page.input_value("#welcome-name") == "Rose"
    page.click("#welcome-name-form button[type=submit]")
    page.wait_for_selector("#welcome-family-form:not([hidden])")
    page.fill("#welcome-family-name", "Maria")
    page.fill("#welcome-family-phone", "555-0100")
    say_it(page, "#welcome-family-form", "My son Daniel, 555 0144")
    assert (page.input_value("#welcome-family2-name"), page.input_value("#welcome-family2-phone")) == ("Daniel", "555 0144")
    page.screenshot(path=str(OUT / "welcome-2-390.png"), full_page=True)
    check_layout(page, "welcome, her family")
    page.fill("#welcome-family2-phone", "call him")
    page.click("#welcome-family-form button[type=submit]")
    page.wait_for_selector("#welcome-family-form-problem")
    assert "second family member" in (page.text_content("#welcome-family-form-problem") or "")
    page.fill("#welcome-family2-phone", "555-0144")
    page.click("#welcome-family-form button[type=submit]")
    page.wait_for_selector("[data-step='3']:not([hidden])")
    assert page.text_content("#welcome-count") == "Step 3 of 3"
    assert page.is_visible("#welcome-back")
    page.screenshot(path=str(OUT / "welcome-3-390.png"))
    check_layout(page, "welcome, her pills")
    page.click("#welcome-later")
    wait_for_screen(page, "today")
    page.wait_for_function("document.getElementById('greeting').textContent.endsWith(', Rose')")
    page.close()


def check_notes(browser) -> None:
    """Doctor notes on the demo week, with the AI down (the test server has no
    key), so entries are grouped by where she said it hurts. Every section,
    Asked and Undo, Add a question, the 7/14/30 days choice, and the printed
    page: a week fits on ONE page (docs/SPEC.md feature 8)."""
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    visit(page, "notes")
    page.wait_for_selector("#notes-doc .doc-title")
    assert page.text_content("#notes-doc .doc-title") == "Notes for Dr. Lee"
    assert (page.text_content("#notes-doc .doc-meta") or "").startswith("Rose, ")
    assert page.is_visible("[data-screen='notes'] >> text=I’m an AI helper. I can’t give medical advice.")
    topics = page.eval_on_selector_all("#notes-doc .doc-topic", "items => items.map(i => i.textContent)")
    assert topics == ["Knee"], topics  # one knee that comes and goes
    words = page.eval_on_selector_all("#notes-doc .doc-words", "items => items.map(i => i.textContent)")
    assert "“My knee is sore when I walk, about a 4”" in words, words
    counts = page.eval_on_selector_all("#notes-doc .doc-count", "items => items.map(i => i.textContent)")
    assert all(count.startswith("Taken ") for count in counts), counts
    assert page.locator("#notes-doc .doc-missed").count() == 2, "the two missed doses should show"
    assert page.locator("#notes-doc .doc-moods li").count() == 5

    # A week of notes prints on one page.
    pdf = page.pdf(format="Letter", print_background=True)
    pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf))
    (OUT / "doctor-notes-7-days.pdf").write_bytes(pdf)
    assert pages == 1, f"a week of doctor notes should print on one page, not {pages}"

    # "Mark as asked": the question stays, with a check and "Asked", and the
    # cursor stays on it (on Undo). Undo makes it a question to ask again.
    questions = "#notes-doc .doc-questions li"
    assert page.locator(questions).count() == 2
    first = page.locator(questions).first
    assert first.locator("button").text_content() == "Mark as asked"
    first.locator("button").click()
    page.wait_for_selector(f"{questions} >> nth=0 >> .doc-asked")
    page.wait_for_selector(".toast:has-text('Marked as asked')")
    assert page.locator(questions).count() == 2, "an asked question stays on the page"
    assert (page.text_content(f"{questions} >> nth=0 >> .doc-asked") or "").strip() == "Asked"
    assert page.evaluate("document.activeElement.textContent") == "Undo", "the cursor should stay on the question"
    page.click(f"{questions} >> nth=0 >> .doc-undo")
    page.wait_for_selector(f"{questions} >> nth=0 >> button:has-text('Mark as asked')")
    assert page.locator(f"{questions} .doc-asked").count() == 0

    # Add a question.
    page.fill("#question-text", "Can I go swimming with my knee?")
    page.click("#question-form button[type=submit]")
    page.wait_for_selector(".toast:has-text('Added to doctor notes')")
    page.wait_for_function(f"document.querySelectorAll('{questions}').length === 3")

    # 14 days: a longer period.
    page.click(".notes-controls label:has-text('14 days')")
    page.wait_for_function("document.querySelector('#notes-doc .doc-meta').textContent.includes(' to ')")
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / "doctor-notes-1440.png"), full_page=True)
    check_layout(page, "Doctor notes at 1440px")
    page.close()


def check_demo_reminder(browser) -> None:
    """On the demo week: Home shows today's check-in as done (a check and
    "Done", no Start), and the hidden ?demo=reminder pops up the reminder
    card for her next pill 2 seconds after the first tap. Buddy says it with
    her name; "I took it" thanks her and closes it, and nothing is saved."""
    page = browser.new_page(viewport={"width": 390, "height": 844})
    # Not "networkidle": the demo makes its voice ahead (warmVoice), which keeps the network busy.
    page.goto(f"http://localhost:{PORT}/?demo=reminder#/", wait_until="load")
    wait_for_screen(page, "today")
    page.wait_for_function("pillState.reminders.length > 0")
    due = page.evaluate("pillState.reminders.filter(r => r.status === 'due').map(r => r.id)")
    if due:  # run between 6 and 8 PM, her real evening pill is due: snooze it, so the demo's card shows
        page.evaluate(f"api('/api/reminders/snooze', 'POST', {{ ids: {due} }})")
        page.reload(wait_until="load")
        wait_for_screen(page, "today")
        page.wait_for_function("pillState.reminders.length > 0")
    page.wait_for_selector("#check-in-done:not([hidden])")
    assert page.is_hidden("#check-in-start"), "a done check-in shows no Start"
    assert (page.text_content("#today-check-in") or "").startswith("Feeling great, at ")
    # (Ends with 0: Playwright would call a snippet that ends in a function.)
    page.evaluate("window.spokenWords = []; var realSpeak = speak;"
                  "window.speak = function (text, options) { spokenWords.push(text); return realSpeak(text, options); }; 0")
    before = page.evaluate("JSON.stringify(pillState.reminders.map(r => [r.id, r.status]))")
    page.mouse.click(5, 300)  # the first tap, on an empty spot
    page.wait_for_selector("#pill-banner:not([hidden])", timeout=10000)
    title = page.text_content("#pill-banner-words") or ""
    assert title.startswith("Rose, it’s time for your "), title
    page.wait_for_function("spokenWords.length > 0")
    assert page.evaluate("spokenWords[0]").startswith(title), "Buddy should say the reminder as it pops up"
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / "pill-reminder-demo-390.png"))
    check_layout(page, "the demo pill reminder at 390px")
    page.click("#pill-taken")
    page.wait_for_selector("#pill-banner", state="hidden")
    page.wait_for_selector(".toast:has-text('Marked as taken')")
    page.evaluate("loadReminders()")
    page.wait_for_timeout(500)
    after = page.evaluate("JSON.stringify(pillState.reminders.map(r => [r.id, r.status]))")
    assert after == before, "the demo reminder must not change her real reminders"
    page.close()


def check_family(browser) -> None:
    """The family update on the demo week: exactly the words on screen go in
    the email, addressed to Maria; Copy copies them; Yesterday switches day."""
    context = browser.new_context(viewport={"width": 1440, "height": 900},
                                  permissions=["clipboard-read", "clipboard-write"])
    page = context.new_page()
    visit(page, "family")
    page.wait_for_function("document.getElementById('update-text').textContent.startsWith('Hi Maria,')")
    assert page.text_content("#update-title") == "Today’s update for Maria"
    assert page.text_content("#update-send") == "Send to Maria"
    shown = page.text_content("#update-text") or ""
    assert "Mood: " in shown and "Pills: " in shown and "Diary: " in shown and "Safety screens" in shown, shown
    # The pills count is the Pills screen's ring, pills still to come included.
    ring = page.evaluate("[pillState.reminders.filter(r => r.status === 'taken').length, pillState.reminders.length]")
    assert f"Pills: {ring[0]} of {ring[1]} taken." in shown, (ring, shown)
    link = urlsplit(page.get_attribute("#update-send", "href") or "")
    assert link.scheme == "mailto" and unquote(link.path) == "maria@example.com", link
    body = parse_qs(link.query)["body"][0].replace("\r\n", "\n")
    assert body == shown, "the email must hold exactly the words on screen"
    assert not page.is_visible("#update-no-email")

    page.click("#update-copy")
    page.wait_for_selector(".toast:has-text('Copied')")
    copied = page.evaluate("navigator.clipboard.readText()")
    # Windows keeps line breaks in the clipboard as \r\n.
    assert copied.replace("\r\n", "\n") == shown, "Copy must copy exactly the words on screen"

    page.click(".family-update label:has-text('Yesterday')")
    page.wait_for_function("document.getElementById('update-title').textContent.startsWith('Yesterday’s')")
    page.wait_for_function(f"document.getElementById('update-text').textContent !== {shown!r}")
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / "family-update-1440.png"), full_page=True)
    check_layout(page, "family update at 1440px")
    context.close()


def check_greeting_and_theme(browser) -> None:
    """Home in the morning, afternoon, evening, and night (a fake clock):
    the greeting follows the time. Auto theme follows the computer, and when
    the computer says neither light nor dark, it is dark from 7 PM to 7 AM."""
    for hour, greeting in [(9, "Good morning"), (14, "Good afternoon"), (19, "Good evening"), (22, "Good evening")]:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.clock.set_fixed_time(datetime(2026, 10, 28, hour, 0))
        page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
        assert (page.text_content("#greeting") or "").startswith(greeting)
        assert page.text_content("#today-date") == "Wednesday, October 28"
        page.close()
    # Chrome always says light or dark, so "neither" is made up here: the
    # page's question about light or dark gets "no" both times.
    says_neither = """const ask = window.matchMedia.bind(window);
      window.matchMedia = (query) => query.includes('prefers-color-scheme')
        ? { matches: false, media: query, addEventListener() {}, removeEventListener() {} } : ask(query);"""
    for scheme, hour, theme in [("dark", 12, "dark"), ("light", 22, "light"), ("neither", 22, "dark"), ("neither", 9, "light")]:
        page = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme=None if scheme == "neither" else scheme)
        if scheme == "neither":
            page.add_init_script(says_neither)
        page.clock.set_fixed_time(datetime(2026, 10, 28, hour, 0))
        page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
        shown = page.get_attribute("html", "data-theme")
        assert shown == theme, f"Auto with {scheme} at {hour}:00 should be {theme}, not {shown}"
        page.close()


WEATHER = {"text": "Sunny, with a high of 62 and a low of 48.", "sites": ["weather.gov"]}  # made up


def check_today_rows(browser) -> None:
    """Home's Today list on the demo week: today's weather (faked: the test
    server has no key), read aloud by a tap anywhere on its row; a tap on a
    row's words opens its screen, like its link. In voice mode, where Buddy
    read the news shows under its words."""
    page = browser.new_page(viewport={"width": 390, "height": 844}, permissions=["microphone"])
    page.route("**/api/briefing/weather", lambda route: route.fulfill(json=WEATHER))
    visit(page, "today")
    page.wait_for_selector("#today-weather:not([hidden])")
    assert page.text_content("#today-weather-text") == WEATHER["text"]
    assert page.text_content("#today-weather-from") == "From weather.gov"
    # Doctor notes names the memory page's own button apart from "Read it to me".
    assert page.locator("#memory-read").text_content().strip() == "Read it aloud"
    page.evaluate("window.spokenWords = []; var realSpeak = speak;"
                  "window.speak = function (text, options) { spokenWords.push(text); return realSpeak(text, options); }; 0")
    page.click("#today-weather-text")  # the words, not the button
    page.wait_for_function("spokenWords.includes('Sunny, with a high of 62 and a low of 48.')")
    # The doctor-notes row says how many questions are still to ask (the demo week has some).
    page.wait_for_function("/^\\d+ questions? to ask$/.test(document.getElementById('today-questions').textContent)")
    page.click("#today-diary")  # a tap on the diary row's words opens the diary
    wait_for_screen(page, "diary")

    # "Anything happening in town?": the reply shows where Buddy read it.
    page.route("**/api/transcribe", lambda route: route.fulfill(json={"transcript": "Anything happening in town?"}))
    page.route("**/api/chat", lambda route: route.fulfill(json={
        "reply": "There's a night market on Saturday, from 2 to 10.", "show": None,
        "actions": [{"type": "sources", "sites": ["pdxpipeline.com", "jambase.com"]}]}))
    visit(page, "talk")
    page.click("#talk-button")
    page.wait_for_selector("#talk-button[data-state='listening']")
    page.wait_for_timeout(600)
    page.click("#talk-button")
    page.wait_for_selector("#actions .sources")
    assert page.text_content("#actions .sources") == "From the web: pdxpipeline.com, jambase.com"
    check_layout(page, "a reply with its sources at 390px")
    page.screenshot(path=str(OUT / "talk-sources-390.png"))
    page.close()


def check_hands_free(browser) -> None:
    """Hands-free talking, with the relay to Meta faked (Playwright stands in
    for /api/listen): Talk to Buddy opens the microphone and the relay; her
    words show live as she talks; her finished turn goes to /api/chat (the
    safety net first) and Buddy answers; while Buddy speaks, only silence is
    sent (the microphone never hears Buddy); then it listens again; Pause
    stops it. Without live speech-to-text, it falls back to tap-to-talk."""
    page = browser.new_page(viewport={"width": 390, "height": 844}, permissions=["microphone"])
    chats = []

    def fake_chat(route):
        chats.append(route.request.post_data_json)
        route.fulfill(json={"reply": "It's sunny today, with a high of 62.", "show": None, "actions": []})

    page.route("**/api/chat", fake_chat)
    page.route("**/api/greeting", lambda route: route.fulfill(json={"greeting": ""}))
    frames = {"her": 0, "silence": 0}
    relay = {}

    def fake_relay(socket):
        relay["socket"] = socket
        socket.send(json.dumps({"type": "ready"}))

        def heard(message):
            if isinstance(message, bytes):
                frames["her" if any(message) else "silence"] += 1  # all zeros is silence

        socket.on_message(heard)

    page.route_web_socket("**/api/listen", fake_relay)
    page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
    # Buddy's voice, faked: 1.5 seconds of "speaking" for each reply.
    page.evaluate(
        "window.fakeSpeaking = false;"
        "window.isSpeaking = function () { return fakeSpeaking; };"
        "window.speak = function (text, options) {"
        "  fakeSpeaking = true;"
        "  setTimeout(function () { fakeSpeaking = false; if (options && options.onEnd) { options.onEnd(); } }, 1500);"
        "}; 0")
    page.click("#start-talk")
    page.wait_for_function("handsFreeOn() && talkState === 'listening'", timeout=15000)
    assert page.text_content("#talk-label") == "Pause"
    # The fake microphone beeps about once a second (silent between beeps).
    def her_sound_after(count: int) -> bool:
        for _ in range(50):
            if frames["her"] > count:
                return True
            page.wait_for_timeout(100)
        return False

    assert her_sound_after(0), f"her sound should go to the relay: {frames}"

    # She talks: her words show live, then her finished turn goes to Buddy.
    relay["socket"].send(json.dumps({"type": "hearing"}))
    relay["socket"].send(json.dumps({"type": "live", "text": "What is the weather"}))
    page.wait_for_function("document.getElementById('you-said-text').textContent === 'What is the weather'")
    assert "live" in (page.get_attribute("#you-said", "class") or "")
    page.screenshot(path=str(OUT / "hands-free-live-390.png"))
    relay["socket"].send(json.dumps({"type": "turn", "text": "What is the weather today?"}))
    page.wait_for_function("document.getElementById('message').textContent.includes('sunny')")
    assert chats[-1]["text"] == "What is the weather today?", chats[-1]
    # While Buddy speaks, only silence goes out.
    page.wait_for_function("fakeSpeaking === true")
    before = dict(frames)
    page.wait_for_timeout(700)
    assert frames["her"] == before["her"] and frames["silence"] > before["silence"], (before, frames)
    assert page.text_content("#talk-label") == "Stop and talk"
    # Then it listens again by itself.
    page.wait_for_function("talkState === 'listening' && !fakeSpeaking", timeout=10000)
    assert her_sound_after(before["her"]), "listening again after Buddy spoke"
    check_layout(page, "hands-free listening at 390px")
    # A pause in the middle of a sentence: Meta may end her turn at the
    # pause. The two parts reach Buddy together, so the safety net sees the
    # whole sentence ("my chest" … "hurts a lot").
    relay["socket"].send(json.dumps({"type": "turn", "text": "My knee"}))
    page.wait_for_timeout(300)
    relay["socket"].send(json.dumps({"type": "hearing"}))
    relay["socket"].send(json.dumps({"type": "turn", "text": "hurts when I walk"}))
    page.wait_for_function(f"document.getElementById('message').textContent.includes('sunny')")
    page.wait_for_timeout(1200)
    assert chats[-1]["text"] == "My knee hurts when I walk", chats[-1]
    # A turn that arrives while Buddy is thinking waits its turn: never lost.
    # (The chat holds each request until the check answers it.)
    page.wait_for_function("talkState === 'listening' && !fakeSpeaking", timeout=10000)
    held = []
    page.unroute("**/api/chat")
    page.route("**/api/chat", lambda route: held.append(route))

    def held_count(count: int) -> None:
        for _ in range(100):
            if len(held) >= count:
                return
            page.wait_for_timeout(100)
        raise AssertionError(f"expected {count} chat requests, got {len(held)}")

    relay["socket"].send(json.dumps({"type": "turn", "text": "What day is it?"}))
    held_count(1)
    assert page.evaluate("talkState") == "working"
    relay["socket"].send(json.dumps({"type": "turn", "text": "And is it raining?"}))
    page.wait_for_timeout(300)
    held[0].fulfill(json={"reply": "It's Friday.", "show": None, "actions": []})
    held_count(2)
    assert [route.request.post_data_json["text"] for route in held] == ["What day is it?", "And is it raining?"]
    held[1].fulfill(json={"reply": "No rain today.", "show": None, "actions": []})
    page.unroute("**/api/chat")
    page.route("**/api/chat", fake_chat)

    # Pause: the microphone goes off, and "Tap to talk" is back.
    page.wait_for_function("talkState === 'listening'", timeout=15000)
    page.click("#talk-button")
    page.wait_for_function("!handsFreeOn() && talkState === 'idle'")
    assert page.text_content("#talk-label") == "Tap to talk"

    # A turn that needs the emergency screen: the screen opens, and the
    # microphone goes off (she has a call to make).
    page.unroute("**/api/chat")
    page.route("**/api/chat", lambda route: route.fulfill(json={
        "reply": "This could be an emergency. If it is, please call 911 right now.", "show": "emergency",
        "actions": [{"label": "Call 911", "href": "tel:911"}]}))
    page.click("#talk-button")
    page.wait_for_function("handsFreeOn() && talkState === 'listening'", timeout=15000)
    relay["socket"].send(json.dumps({"type": "turn", "text": "my chest feels really tight"}))
    page.wait_for_selector("#safety-screen[open][data-kind='emergency']")
    page.wait_for_function("!handsFreeOn()")
    page.close()

    # Where live speech-to-text can't be used, she simply taps to talk.
    tap = browser.new_page(viewport={"width": 390, "height": 844}, permissions=["microphone"])
    tap.route("**/api/greeting", lambda route: route.fulfill(json={"greeting": ""}))
    tap.route_web_socket("**/api/listen", lambda socket: socket.send(json.dumps({"type": "unavailable"})))
    tap.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
    tap.click("#start-talk")
    tap.wait_for_selector("#talk-button[data-state='listening']")
    assert not tap.evaluate("handsFreeOn()")
    assert tap.text_content("#talk-label") == "I’m done"
    tap.close()


def check_help(browser) -> None:
    """Help on the demo week: opened from Settings on a phone (the tab bar
    keeps Settings lit), the 4 Meta models from the app's settings, every
    feature with its models or "No AI", questions that open, and Call Maria.
    On a desktop the sidebar has Help."""
    page = browser.new_page(viewport={"width": 390, "height": 844})
    visit(page, "settings")
    page.click("text=Help and how Buddy works")
    wait_for_screen(page, "help")
    assert page.get_attribute(".tabbar [data-nav='settings']", "aria-current") == "page"
    page.wait_for_selector("#help-models .help-model")
    names = page.eval_on_selector_all(".help-model-name", "items => items.map(i => i.textContent)")
    assert names == ["Muse Spark 1.3", "Muse Voice Transcribe 1.0", "Muse Image 1.0", "SAM 3.1"], names
    assert page.locator(".help-feature").count() >= 9
    safety_net = page.locator(".help-feature", has_text="The safety net")
    assert safety_net.locator(".tag").all_text_contents() == ["No AI"], "the safety net uses no AI"
    first = page.locator(".faq-item").first
    first.locator("summary").click()
    assert first.locator(".faq-answer").is_visible()
    assert page.text_content("#help-call-label") == "Call Maria"
    assert page.get_attribute("#help-call-family", "href") == "tel:555-0100"
    check_layout(page, "Help at 390px")
    page.close()

    wide = browser.new_page(viewport={"width": 1440, "height": 900})
    visit(wide, "today")
    wide.click("[data-nav='help']:visible")
    wait_for_screen(wide, "help")
    assert wide.get_attribute(".sidebar [data-nav='help']", "aria-current") == "page"
    wide.close()


def check_every_screen(browser) -> None:
    """Every screen at a phone, a tablet, and a desktop, light and dark:
    screenshots, and no layout problems."""
    for theme in ("light", "dark"):
        for width, height in SIZES:
            page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
            for name in SCREENS:
                visit(page, name)
                assert shown_screen(page) == name
                assert page.get_attribute("html", "data-theme") == theme
                page.wait_for_timeout(1200 if name == "today" else 500)
                page.screenshot(path=str(OUT / f"{name}-{width}-{theme}.png"), full_page=True)
                check_layout(page, f"{name} at {width}px, {theme}")
            page.close()


def check_buddy_states(browser) -> None:
    """The orb in each state, in voice mode with its words, light and dark,
    plus reduced motion (the computer's setting), where it stands still but
    keeps its glow."""
    labels = {"idle": "", "listening": "I’m listening", "thinking": "Let me think…", "speaking": ""}
    for theme in ("light", "dark"):
        page = browser.new_page(viewport={"width": 768, "height": 1024}, color_scheme=theme)
        page.goto(f"http://localhost:{PORT}/#/talk", wait_until="networkidle")
        for state, label in labels.items():
            page.evaluate(f"setBuddyState('{state}')")
            page.wait_for_timeout(900)
            assert page.text_content("#buddy-label") == label, state
            page.locator(".voice-stage").screenshot(path=str(OUT / f"orb-{state}-{theme}.png"))
        page.close()

    calm = browser.new_page(viewport={"width": 768, "height": 1024}, reduced_motion="reduce")
    calm.goto(f"http://localhost:{PORT}/#/talk", wait_until="networkidle")
    assert calm.evaluate("document.documentElement.hasAttribute('data-calm')"), "reduced motion should turn on Calm motion"
    calm.evaluate("setBuddyState('listening')")
    calm.wait_for_timeout(500)
    still = calm.evaluate("getComputedStyle(document.querySelector('.orb--voice .orb-blob')).animationName")
    assert still == "none", f"the orb should stand still with reduced motion, not {still!r}"
    calm.locator(".voice-stage").screenshot(path=str(OUT / "orb-listening-reduced-motion.png"))
    calm.close()


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
                check_welcome(browser)  # first, while the test database has no name
                page = browser.new_page(viewport={"width": 1280, "height": 900}, permissions=["microphone"])
                page.on("console", lambda msg: problems.append(msg.text) if msg.type == "error" else None)
                page.on("pageerror", lambda err: problems.append(str(err)))

                page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
                page.wait_for_timeout(1200)  # let Buddy wake up
                page.screenshot(path=str(OUT / "home-desktop.png"))
                check_layout(page, "desktop")
                check_home_hero(browser)
                check_check_in(browser)
                check_hands_free(browser)

                # Talk: speech-to-text and Buddy's AI reply are faked, so Meta
                # is never called.
                uploads = []

                def fake_transcribe(route):
                    uploads.append(route.request.post_data_buffer)
                    route.fulfill(json={"transcript": "Maria is coming on Sunday"})

                page.route("**/api/transcribe", fake_transcribe)
                page.route("**/api/chat", lambda route: route.fulfill(json={
                    "reply": "What a lovely visit! When is she coming?",
                    "show": None,
                    "actions": [{"type": "add_question", "label": "Add to doctor notes", "question": "Is it okay to walk more?"}],
                }))
                check_talk(page, uploads)
                check_settings_form(page, problems)
                check_diary_talk(page)
                check_memory_talk(page)
                check_pills(page, problems)
                check_scam(browser)
                check_find(browser)

                # The safety net, end to end: she says an emergency warning sign
                # (faked speech-to-text), the real /api/chat answers with no AI,
                # and the red full-screen message with Call 911 appears at once.
                safety_page = browser.new_page(viewport={"width": 390, "height": 844}, permissions=["microphone"])
                safety_page.on("pageerror", lambda err: problems.append(str(err)))
                safety_page.route("**/api/transcribe", lambda route: route.fulfill(json={"transcript": "my chest feels really tight"}))
                safety_page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
                safety_page.click("#start-talk")
                safety_page.wait_for_selector("#talk-button[data-state='listening']")
                safety_page.wait_for_timeout(600)
                safety_page.click("#talk-button")
                safety_page.wait_for_selector("#safety-screen[open][data-kind='emergency']")
                message = safety_page.text_content("#safety-message") or ""
                assert message == "This could be an emergency. If it is, please call 911 right now.", message
                assert safety_page.get_attribute("#safety-actions a", "href") == "tel:911"
                motion = safety_page.evaluate("getComputedStyle(document.getElementById('safety-screen')).animationName")
                assert motion == "none", f"emergency screens never move, not {motion!r}"
                safety_page.screenshot(path=str(OUT / "safety-emergency.png"))
                safety_page.click("#safety-close")
                assert not safety_page.is_visible("#safety-screen"), "the safety screen did not close"
                # Behind it, the Call 911 button stays under Buddy's words.
                assert safety_page.get_attribute("#actions a", "href") == "tel:911"
                # Her words went into the diary, marked as an emergency screen.
                safety_page.goto(f"http://localhost:{PORT}/#/diary", wait_until="networkidle")
                safety_page.wait_for_selector(".entries .entry")
                assert safety_page.text_content(".day-heading") == "Today"
                assert safety_page.text_content(".entry-words") == "“my chest feels really tight”"
                assert safety_page.text_content(".entry-note") == "Buddy showed the emergency screen."
                safety_page.screenshot(path=str(OUT / "diary-390px.png"), full_page=True)
                check_layout(safety_page, "Diary screen at 390px")
                # Home's diary row shows it too.
                safety_page.click("[data-nav='today']:visible")
                safety_page.wait_for_function("document.getElementById('today-diary').textContent.includes('chest')")

                # Phone: the tab bar and Home's rows open screens; Back returns.
                phone = browser.new_page(viewport={"width": 390, "height": 844})
                phone.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
                phone.wait_for_timeout(1200)
                phone.screenshot(path=str(OUT / "home-390px.png"))
                check_layout(phone, "390px")
                # A first visit starts with Large text, so it is easy to read.
                assert phone.evaluate("document.documentElement.style.fontSize") == "118%", "first visit should be Large"
                # A press shows the moment it lands: squeezed, with a circle of light.
                phone.eval_on_selector(".row-link[href='#/notes']", "link => link.scrollIntoView({ block: 'center' })")
                box = phone.locator(".row-link[href='#/notes']").bounding_box()
                phone.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                phone.mouse.down()
                assert phone.get_attribute(".row-link[href='#/notes']", "data-pressed") == ""
                assert phone.locator(".row-link[href='#/notes'] .ripple").count() == 1, "no circle of light on press"
                phone.wait_for_timeout(120)
                phone.screenshot(path=str(OUT / "press-390px.png"))
                phone.mouse.up()
                phone.wait_for_function("document.title === 'Doctor notes · Grandma Buddy'")
                go_today(phone)
                phone.click(".row-link[href='#/diary']")
                phone.wait_for_function("document.title === 'My diary · Grandma Buddy'")
                phone.go_back()
                wait_for_screen(phone, "today")
                open_screen(phone, "pills", "My pills")

                # Text size in Settings: Largest grows everything, nothing spills.
                open_screen(phone, "settings", "Settings")
                phone.click("#settings-form label:has-text('Largest')")
                phone.wait_for_function("document.documentElement.style.fontSize === '135%'")
                # Remembered: after a reload the words are still largest.
                phone.reload(wait_until="networkidle")
                assert phone.evaluate("document.documentElement.style.fontSize") == "135%", "text size not remembered"
                assert phone.is_checked("input[name=text_size][value='2']")

                # Every screen at phone width with the largest text.
                for name in SCREENS:
                    visit(phone, name)
                    assert shown_screen(phone) == name
                    phone.wait_for_timeout(500)
                    check_layout(phone, f"{name} screen, 390px with the largest text")
                    phone.screenshot(path=str(OUT / f"{name}-390-largest.png"), full_page=True)

                # The narrowest phones (360px), with the largest text: the
                # tightest fit there is, like the tab bar's "Settings".
                narrow = browser.new_page(viewport={"width": 360, "height": 780})
                narrow.add_init_script("localStorage.setItem('words', '2')")
                for name in SCREENS:
                    visit(narrow, name)
                    narrow.wait_for_timeout(400)
                    check_layout(narrow, f"{name} screen at 360px with the largest text")
                narrow.screenshot(path=str(OUT / "tabbar-360-largest.png"), clip={"x": 0, "y": 680, "width": 360, "height": 100})
                narrow.close()

                # 200% browser zoom on a 1280px screen shows 640 CSS px: same check.
                zoomed = browser.new_page(viewport={"width": 640, "height": 450})
                for name in SCREENS:
                    visit(zoomed, name)
                    zoomed.wait_for_timeout(400)
                    check_layout(zoomed, f"{name} at 200% zoom")
                zoomed.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
                zoomed.wait_for_timeout(1200)
                zoomed.screenshot(path=str(OUT / "home-zoom200.png"))

                check_greeting_and_theme(browser)
                # The made-up demo week: the doctor notes, then every screen with real-looking data.
                seed_demo_week(test_env["DATABASE_PATH"])
                check_notes(browser)
                check_family(browser)
                check_demo_reminder(browser)
                check_help(browser)
                check_read(browser)
                check_landing(browser)
                check_family_accounts(browser)
                check_billing(browser)
                check_today_rows(browser)
                check_friend(browser, test_env["DATABASE_PATH"])
                check_every_screen(browser)
                check_buddy_states(browser)
            finally:
                browser.close()

        if problems:
            print("BROWSER ERRORS FOUND:")
            for problem in problems:
                print(" -", problem)
            return 1

        print(
            "Home check OK: Talk to Buddy opens voice mode (16 kHz mono WAV sent, words and reply shown, reading "
            "progress, Earlier, the orb finishes and closes), Home opens on the greeting and the whole moving orb with "
            "one Talk to Buddy, the daily check-in (first Today row, Start, check_in mode with its own talk), Settings saves choices at once and names a refused "
            "entry, theme, text size, and Calm motion work, \"Something hurts\" talks in diary mode, the Memory book "
            "(chip, empty book, memory talk in memory mode, Save it in my memory book), pill reminders "
            "work (card, I took it, remind me, ring, round check, change, remove, undo), Check a message (paste, "
            "read aloud, photo, verdict card, fixed what-to-do, works with the AI down), Find my things (chip, \"What "
            "are you looking for?\" first, quick pick, photo, halo and sentence, nothing found, safety net first, the "
            "Find my glasses button), Read it to me (chip, the orb on the photo while Buddy reads, a bill's amount "
            "and date, word for word with Stop, a health letter never explained with the doctor's call first, a "
            "likely scam's warning, Check it for a scam with the words, Back keeps the paper, a photo it can't read, "
            "Meta down), the landing, Privacy, and Terms (every picture loads, the orb alive, questions open, Open "
            "Buddy, Help's links), family accounts (Maria seeded, an invite code, the sharing switches, joining on "
            "another browser, her day as she shares it, Yesterday's missed pill, a notification for a new alert, sign out "
            "and in, a wrong password, the pill reminder as a notification while Buddy is hidden, Remove ending the "
            "session), the Family plan in demo mode (no card fields, start, cancel at the end of the period), the "
            "welcome (Step 1 of 3, Back on top), Doctor notes on the demo week "
            "(sections, Mark as asked and Undo in place, Add a question, 14 days, prints on one page), the family update "
            "(the email holds exactly the words on screen, its pills count matches the Pills ring, Copy, Yesterday), "
            "the demo week's done check-in and the hidden ?demo=reminder card (pops up after the first tap, said with "
            "her name, saves nothing), Help (from Settings and the sidebar, the 4 Meta models, "
            "every feature with its models or No AI, questions open, Call Maria), Home's weather row (read aloud by "
            "a tap anywhere on it) and whole-row taps, a reply's web sources, hands-free talking (live words, her "
            "turn to the chat, only silence while Buddy speaks, listens again, Pause, tap-to-talk without it), the "
            "emergency screen never "
            "moves, Auto theme follows the computer and the evening, every screen at 390/768/1440px in light and "
            "dark, the orb's states and reduced motion look right, no layout problems. Screenshots in test-output/."
        )
        return 0
    finally:
        server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
