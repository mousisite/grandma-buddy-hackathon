# scripts/browser_checks/home.py
# Opens the app in a real browser, talks to it with a fake microphone,
# checks every flow and the layout, and saves screenshots to test-output/.
#
# Run it by hand: .venv\Scripts\python scripts\browser_checks\home.py
# Needs no API key and never calls Meta: the speech-to-text answer is faked.
# It starts its own test server on port 8001.

import os
import struct
from datetime import datetime
import subprocess
import tempfile
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "test-output"
PORT = 8001
SCREENS = ["today", "talk", "diary", "pills", "notes", "scam", "family", "settings"]
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


def check_layout(page, where: str) -> None:
    """Fail if the page scrolls sideways, an icon is squashed, a target is
    too small, or words spill out."""
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

    # Family now has big call buttons for Maria and Dr. Lee.
    open_screen(page, "family", "Family")
    hrefs = page.eval_on_selector_all("#family-calls a", "links => links.map(a => a.getAttribute('href'))")
    assert hrefs == ["tel:555-0100", "tel:555-0199"], hrefs
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

    # Due now: the card repeats the label exactly as typed.
    page.fill("#pill-form .time-input", time_now)
    page.click("#pill-save")
    page.wait_for_selector("#pill-banner:not([hidden])")
    words = page.text_content("#pill-banner-words") or ""
    assert words == f"It’s time for your {part} pill: Lisinopril, 10 mg tablet, take 1 by mouth daily.", words
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


def check_check_in(browser) -> None:
    """The daily check-in on a fresh day: the card on Home (light, dark,
    desktop), "Not today" hides it, and "Start" in the Today list opens
    voice mode with Buddy's opening question, sends her answer in
    "check_in" mode with the check-in's own conversation, and goes back to
    ordinary talk when she leaves voice mode."""
    for theme, width, height in [("light", 390, 844), ("dark", 390, 844), ("light", 1440, 900)]:
        page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
        page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
        page.wait_for_selector("#check-in-card:not([hidden])")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / f"check-in-card-{width}-{theme}.png"))
        check_layout(page, f"check-in card at {width}px, {theme}")
        page.close()

    sent = []

    def fake_chat(route):
        sent.append(route.request.post_data_json)
        route.fulfill(json={"reply": "I'm glad. Does anything hurt or feel different today?", "show": None,
                            "actions": [], "diary_saved": False, "diary_done": False})

    page = browser.new_page(viewport={"width": 390, "height": 844}, permissions=["microphone"])
    page.route("**/api/transcribe", lambda route: route.fulfill(json={"transcript": "I'm feeling pretty good"}))
    page.route("**/api/chat", fake_chat)
    page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
    page.wait_for_selector("#check-in-card:not([hidden])")
    # "Not today": the card goes, and stays gone after a reload.
    page.click("#check-in-skip")
    page.wait_for_selector("#check-in-card", state="hidden")
    page.wait_for_selector(".toast:has-text('Okay, maybe tomorrow')")
    page.reload(wait_until="networkidle")
    page.wait_for_function("document.getElementById('today-check-in').textContent === 'Done for today'")
    assert not page.is_visible("#check-in-card"), "the card came back after Not today"

    # "Start" in the Today list still runs it (and in the demo).
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
                page = browser.new_page(viewport={"width": 1280, "height": 900}, permissions=["microphone"])
                page.on("console", lambda msg: problems.append(msg.text) if msg.type == "error" else None)
                page.on("pageerror", lambda err: problems.append(str(err)))

                page.goto(f"http://localhost:{PORT}/", wait_until="networkidle")
                page.wait_for_timeout(1200)  # let Buddy wake up
                page.screenshot(path=str(OUT / "home-desktop.png"))
                check_layout(page, "desktop")
                check_check_in(browser)

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
                check_pills(page, problems)

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

                # The narrowest phones (360px).
                narrow = browser.new_page(viewport={"width": 360, "height": 780})
                for name in SCREENS:
                    visit(narrow, name)
                    narrow.wait_for_timeout(400)
                    check_layout(narrow, f"{name} screen at 360px")
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
            "progress, Earlier, the orb finishes and closes), the daily check-in (card, Not today, Start, check_in "
            "mode with its own talk), Settings saves choices at once and names a refused "
            "entry, theme, text size, and Calm motion work, \"Something hurts\" talks in diary mode, pill reminders "
            "work (card, I took it, remind me, ring, round check, change, remove, undo), the emergency screen never "
            "moves, Auto theme follows the computer and the evening, every screen at 390/768/1440px in light and "
            "dark, the orb's states and reduced motion look right, no layout problems. Screenshots in test-output/."
        )
        return 0
    finally:
        server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
