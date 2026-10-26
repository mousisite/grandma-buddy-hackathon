# Grandma Buddy: build plan

This project started on Monday, October 26, 2026, the hackathon's kickoff day. Final submissions are due **Wednesday, November 4 at 9:00 PM Eastern (6:00 PM Pacific)**. Our goal is to submit by noon Pacific that day.

The coding agent updates the checkboxes and the status log as work gets done. If we fall behind, cut from the bottom of the priority list in `docs/SPEC.md` (P2 first), never from safety.

## Day by day

### Day 1: Mon, Oct 26 (kickoff)
- [x] New project folder and GitHub repository, created today.
- [x] Language decided: English.
- [ ] Skeleton: `requirements.txt` installed into `.venv`, `app/config.py`, `app/db.py` (all tables), `app/main.py` with `/api/ping`, home screen in `static/` (Talk button not wired yet).
- [ ] `scripts/check_meta.py`: one tiny real call to Muse Spark that confirms the API key and billing work.
- [ ] The app runs at http://localhost:8000 and `.venv\Scripts\python -m pytest` passes.

### Day 2: Tue, Oct 27 (voice in)
- [ ] Watch the "Agents 101: Build a Multimodal AI Agent" workshop (9:00 AM Pacific, or the recording).
- [ ] `static/recorder.js`: microphone to 16 kHz mono WAV, tap to start and stop, 2-minute limit.
- [ ] `app/meta_client.py` `transcribe()` and `/api/transcribe`, with keywords from medications and family names.
- [ ] What she says shows up in big text. Tests with the Meta call mocked.

### Day 3: Wed, Oct 28 (safety net, talking back)
- [ ] Watch the "Agents 102: Best Practices for Verifiable Agents" workshop (9:00 AM Pacific, or the recording).
- [ ] `app/safety.py` with every rule and test phrase in `docs/SAFETY.md`, plus the emergency, Poison Control, and crisis screens.
- [ ] Companion prompt and `/api/chat` with conversation history. Replies are read aloud with `static/speech.js`.
- [ ] `/safety-check` passes.

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

- Oct 26: Project created. Plan, safety rules, and coding-agent setup written. No app code yet.
