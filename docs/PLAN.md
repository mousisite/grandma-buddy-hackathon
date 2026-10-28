# Grandma Buddy: build plan

This project started on Monday, October 26, 2026, the hackathon's kickoff day. Final submissions are due **Wednesday, November 4 at 9:00 PM Eastern (6:00 PM Pacific)**. Our goal is to submit by noon Pacific that day.

The coding agent updates the checkboxes and the status log as work gets done. If we fall behind, cut from the bottom of the priority list in `docs/SPEC.md` (P2 first), never from safety.

## Day by day

### Day 1: Mon, Oct 26 (kickoff)
- [x] New project folder and GitHub repository, created today.
- [x] Language decided: English.
- [x] Skeleton: `requirements.txt` installed into `.venv`, `app/config.py`, `app/db.py` (all tables), `app/main.py` with `/api/ping`, home screen in `static/` (Talk button not wired yet).
- [x] `scripts/check_meta.py`: one tiny real call to Muse Spark that confirms the API key and billing work. Written and compiles; the user runs it by hand once `.env` has a real key.
- [x] The app runs at http://localhost:8000 and `.venv\Scripts\python -m pytest` passes.

### Day 2: Tue, Oct 27 (voice in)
- [ ] Watch the "Agents 101: Build a Multimodal AI Agent" workshop (9:00 AM Pacific, or the recording).
- [x] `static/recorder.js`: microphone to 16 kHz mono WAV, tap to start and stop, 2-minute limit.
- [x] `app/meta_client.py` `transcribe()` and `/api/transcribe`, with keywords from medications and family names.
- [x] What she says shows up in big text. Tests with the Meta call mocked.

### Day 3: Wed, Oct 28 (safety net, talking back)
- [ ] Watch the "Agents 102: Best Practices for Verifiable Agents" workshop (9:00 AM Pacific, or the recording).
- [x] `app/safety.py` with every rule and test phrase in `docs/SAFETY.md`, plus the emergency, Poison Control, and crisis screens. (Done early, Oct 26.)
- [x] Companion prompt and `/api/chat` with conversation history. Replies are read aloud with `static/speech.js`. (Done early, Oct 26.)
- [x] `/safety-check` passes.

### Day 4: Thu, Oct 29 (symptom diary)
- [ ] Diary mode: "Something hurts" button, up to 3 follow-up questions by voice, `log_symptom`, call buttons, the no-advice answer.
- [ ] Diary list screen. `/safety-check` and `/senior-friendly-ui` pass.

### Day 5: Fri, Oct 30 (pills)
- [ ] Medication screen (add, edit, remove with confirmation).
- [ ] Reminder banner, spoken reminder, "I took it", "Remind me in 10 minutes", missed after 2 hours.
- [ ] Companion tools: `get_pills_due`, `mark_pill_taken`.

### Day 6: Sat, Oct 31 (check-in and companion)
- [ ] Daily check-in on first open each day: feeling, anything hurting or different, morning pills.
- [ ] Tools: `log_mood`, `add_doctor_question`, `show_call_buttons`, `suggest_calling_family`.
- [ ] Lonely conversations end with a gentle nudge to call family. `/safety-check` passes.

### Day 7: Sun, Nov 1 (scam checker)
- [ ] `/api/scam-check` for spoken, pasted, and photographed messages. Scam test messages pass.

### Day 8: Mon, Nov 2 (doctor notes and family)
- [ ] `/api/doctor-notes`, printable one-page notes, add-a-question by voice.
- [ ] `/api/family/summary`, "Send to {family}" email link, Copy button.
- [ ] `scripts/seed_demo.py` with a week of made-up data for "Rose".

### Day 9: Tue, Nov 3 (polish and demo)
- [ ] `/taste`, `/web-design-guidelines`, and `/senior-friendly-ui` on every screen.
- [ ] Fresh-eyes test: use every screen as if you were an older adult who's new to apps (voice first, no squinting at small text, slow taps). Write down the 3 most confusing moments and fix them.
- [ ] `/demo-prep`: README, secrets sweep, make the repository public, demo script, record the demo video (3 minutes maximum).
- [ ] Last full day for help in Discord, so ask any questions today.

### Day 10: Wed, Nov 4 (submit)
- [ ] Final check from a fresh copy of the repository.
- [ ] Submit by noon Pacific. The deadline is 6:00 PM Pacific.

## Submission requirements (from the Participant Guide)

- **Where:** https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit by Nov 4, 9:00 PM Eastern. Late submissions aren't considered.
- **Repository:** must be public, with everyone who worked on it listed on the submission page.
- **Demo video:** 3 minutes maximum, showing only features, code, and functionality built during the hackathon. The link must work for anyone. Judges use the video, the code, and the live product.
- **New work only:** everything presented must be built during the event, and that must be clear in the submission.
- **Must use Meta's models:** Muse Spark and Muse Voice Transcribe through the Meta Model API.
- **Avoid "anti-projects":** nothing where AI gives medical, mental-health, or nutrition advice (see `docs/SAFETY.md`).
- **Judging:** Stage 1 is pass/fail (fits the theme and uses Meta's models). Stage 2 scores 0 to 10 on a rubric. The top 5 per track go to live finals on Nov 9.
- **Help:** Discord #office-hours on weekdays from 7:00 to 8:00 AM Pacific. Nov 3 is the last full day for troubleshooting.

## Status log

Newest first. One line per finished piece of work: date, what changed, how it was tested.

- Oct 27: App shell and Family & settings screen. One page with a section per screen (Today, My diary, My pills, Doctor notes, Scam check, Family); the address names the screen (`#/family`), so Back works, focus moves to each screen's heading, and the tab title changes. Sidebar and cards are real links; phones get a "Menu" drawer (Close, Escape, tap beside it; the page behind can't be reached while it's open). Buddy's "Open …" buttons now open real screens. Family screen: Call {family} and Call {doctor} buttons, and a "Set up Buddy" form (her names, family name/phone/email, doctor name/phone, voice on/off, Slower/Normal/Faster). The server names a refused entry and how to fix it ("Use numbers, like 555‑0123."), shown right under it; unsaved entries are kept when moving between screens. Diary, Pills, Notes, and Scam screens say honestly that they're coming soon. Skip link, 16px between all tap targets. `static/screens.js` added; docs/DESIGN.md rewritten for the AI-app look. 200/200 pytest; browser check covers moving between screens, the phone menu, saving and refusing on the form, Back, and layout at 360, 375 (biggest words), 640, 768, and 1280. `/web-design-guidelines` and `/senior-friendly-ui` pass after fixes.

- Oct 26 (Day 3 work, done early): Buddy talks back (Features 1 and 6). `meta_client.chat()` (Muse Spark 1.3, low reasoning, one retry mechanism, kind message if the AI or key fails); `app/prompts.py` companion prompt (no advice of any kind, AI-helper honesty, one question at a time, loneliness → a real person, diary and check-in modes, gentle note after a crisis); `app/tools.py` (log_mood, log_symptom saving her own words, add_doctor_question, show_call_buttons, suggest_calling_family, open_screen); `app/companion.py` tool loop (max 3 rounds, Meta's message order); `app/guard.py` advice guard with fixed replies; `/api/doctor-questions`; memory of the last 20 messages across days. Safety net hardened after a code review: 33 missed phrasings and 12 false alarms fixed, checked before the database, multi-turn merge, crisis words never stored, 988 added when crisis words come with an emergency, Call 911/family on every failure, "call 911" link always on screen. 199/199 pytest (113 safety phrases, 49 guard cases incl. 17 normal replies that must pass, companion tests with a strict fake AI). Real checks: `scripts/check_advice.py` (8 SAFETY.md phrases, the real model gave no advice) and one real voice-to-reply run.
- Oct 26 (Day 3 work, done early): Safety net (Feature 2). `app/safety.py`: plain rules from SAFETY.md §3–4 (body part + problem together, harmless phrases like "chest of drawers" ignored), fixed messages word for word, `check_recent()` catches a symptom told across two answers. `/api/chat` runs it first in every mode and never calls the AI on a match; saves `safety_events` and an emergency diary entry. Profile API (`/api/profile`). Full-screen `<dialog>` safety screens (red Emergency and Poison Control, calm crisis) with big call buttons, read aloud (`static/speech.js`), staying until "Go back"; call buttons stay under Buddy's words afterward; offline shows Call 911 and Call family. JS split into `app.js`, `talk.js`, `speech.js`. 78/78 pytest (59 safety phrases incl. near misses, AI-never-called per mode), browser check with a real emergency phrase end to end, crisis and Poison Control screens checked by screenshot. The browser check now uses a throwaway database and no API key.
- Oct 26: Motion pass (impeccable `animate`): opening sequence under 1 second, a breathing invite ring behind the Talk plate, turning sun rays and a rocking moon, a kitchen-timer arc while her words are written down, a happy settle and rising "You said" card when they arrive, lifting canister lids, easing-in messages, and smooth Bigger words. Reduced motion keeps fades only (checked in the browser). Found and fixed: rings hidden behind the tiled wall (`isolation: isolate` on the Talk area). The words-spill check in `home.py` now measures the text itself (confirmed it still catches a squeezed canister). Browser check passes; 9/9 pytest. Motion rules recorded in docs/DESIGN.md.
- Oct 26: New style, "The Kitchen Canister Set", chosen by the user from four mocked-up directions (impeccable design plugin; `PRODUCT.md` added). Turquoise tiled wall by day and deep blue at night, Buddy's sun or moon face, a big white plate with a sunflower center to talk, colored canisters with lids for "Something hurts" and "Is this a scam?", flat white cards for reading, raised keys that sink, and a bottom tab bar (Home, Pills, Diary, Family) so it reads as a real app. While listening, a ring around the plate grows with her voice and everything else fades back. Font: Atkinson Hyperlegible Next, self-hosted (SIL OFL 1.1, credited in THIRD_PARTY_NOTICES.md). Contrast re-measured (lowest 7.8:1). A fresh finish reviewer ran two fix rounds (phone first viewport, tab gaps, 32px headings, honest "coming soon" copy, lids, touch hover, tablet canister size). `home.py` now also fails if words spill out of any button. Browser check passes at 1280, 1024, 768, 390, 375, 360, biggest words, night, and listening; 9/9 pytest.
- Oct 26 (Day 2 work, done early): Voice in. `static/recorder.js` records with MediaRecorder and converts to 16 kHz mono 16-bit WAV; Talk button has listening and "One moment…" states, a 2-minute limit, and kind messages for a blocked or missing microphone, no internet, or not catching it. `app/meta_client.py` `transcribe()` (429 retries, 60 s timeout), `/api/transcribe` in `app/routes/companion.py` with family, doctor, and active pill names as keywords; audio is never saved and transcripts are never logged. 9/9 pytest (Meta mocked; `tests/conftest.py` blocks real calls and uses a temporary database). Browser check with a fake microphone confirms the uploaded WAV format and the "You said" card. One real end-to-end run with a made-up sentence spoken by Windows' voice came back word for word.
- Oct 26: Home screen polish: sky matches the time of day (sun by day, moon and stars at night), buttons are raised keys that sink when pressed, "Bigger words" moved under the date with action labels and a remembered choice, left-aligned big buttons, invitation under the Talk button, bandage icon for "Something hurts", curly apostrophes. docs/DESIGN.md updated. Browser check passes (desktop, tablet, 375px, biggest words, reload remembers size, 200% zoom, day and night), 3/3 pytest, `/web-design-guidelines` and `/senior-friendly-ui` pass.
- Oct 26: Home screen fixes: icons no longer get squashed by long words, the small-button row stacks one per line when two don't fit (phones, bigger words), and stars stay beside the page instead of showing through the greeting. `scripts/browser_checks/home.py` now fails on squashed icons or stars behind words (confirmed it catches the old CSS). Browser check passes at desktop, tablet (768 and 1024), 375px, biggest words, and 200% zoom. Screen check passes.
- Oct 26: Coding agent switched from Muse Code to Claude Code: `CLAUDE.md` loads `AGENTS.md`, skills moved to `.claude/skills/`, AGENTS.md and README updated. Re-checked: 3/3 pytest, home browser check passes (desktop, 375px, biggest words, 200% zoom), contrast numbers in docs/DESIGN.md re-measured and correct.
- Oct 26: Home restyled dark and gold (inspired by highlightstudio.app, all original code): night sky with moon, stars, and glows; pill buttons; gold Talk button. Colors in docs/DESIGN.md updated. 3/3 pytest plus browser check (desktop, 375px, biggest words, 200% zoom). Screen and safety reviews pass.
- Oct 26: Home screen redesigned: warm animated sky (sun, clouds, birds, balloon, sparkles), icons on all buttons, time-based greeting, Words normal/big/biggest button. 3/3 pytest plus browser check (desktop, 375px, biggest words, 200% zoom). Screen and safety reviews pass.
- Oct 26: Day 1 skeleton done: requirements installed, config/db/main with `/api/ping`, home screen, `check_meta.py`, `.env.*` git-ignored. Tested with 3/3 pytest passing plus a Playwright browser check (desktop, 375px, 200% zoom, no errors). `/web-design-guidelines`, `/senior-friendly-ui`, and a Day 1 `/safety-check` all pass.
- Oct 26: Project created. Plan, safety rules, and coding-agent setup written. No app code yet.
