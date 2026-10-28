# Grandma Buddy: instructions for the coding agent

Read this whole file at the start of every session. It is the source of truth for how to work in this project. The coding agent is Claude Code, which loads this file through `CLAUDE.md`. (Muse Code built the Day 1 skeleton.)

## Who you are working with

- The builder is a beginner on Windows, using VS Code and PowerShell. Explain each step in plain, short sentences. Any command you give them to run is PowerShell, never Bash.
- After every feature, tell them exactly how to run it and what to click or say to test it by hand.
- If something is ambiguous, ask one short question instead of guessing.

## Your shell

- You can run your own commands in PowerShell or Git Bash, whichever fits the job.
- Python always comes from the project's `.venv`: `.venv\Scripts\python` in PowerShell, `.venv/Scripts/python` in Git Bash. Never `python3`, and never `Activate.ps1`.
- Commands you hand to the user are always PowerShell, even if you tested them in Git Bash.

## What we are building

Grandma Buddy is a voice companion for an older adult who lives alone. She talks to it instead of typing. Every day it checks in on how she's feeling, reminds her to take her pills, keeps a symptom diary for her doctor, keeps her company when she's lonely, writes up notes for her next doctor visit, sends a short update to a family member she chose, and checks suspicious messages for scams. A rules-based safety net shows emergency, crisis, and Poison Control screens when needed.

**The AI never gives medical, mental-health, or food advice.** It records, reminds, and connects her to real people. This is a safety rule and a hackathon rule: the hackathon disqualifies projects where AI gives medical advice.

It's being built for the Meta Global AI Developer Hackathon (Indie developer track, theme "Build for Your World"). Final submissions are due Wednesday, Nov 4, 2026 at 9:00 PM Eastern (6:00 PM Pacific). Judges look at creativity, technical ambition, and whether it works.

## Hackathon rules that affect the code

- All app code must be written during the hackathon (Oct 26 to Nov 4, 2026). Never copy in code from other projects or from before the event.
- The repository will be public. Never commit secrets or personal data.
- Only use code, data, images, and sounds we have the rights to. If you add a library or asset, say what its license is.

## Read these before you work

1. `docs/SPEC.md`: every feature and what "done" means
2. `docs/ARCHITECTURE.md`: stack, file map, data model, API routes, AI design
3. `docs/SAFETY.md`: the no-advice rules, safety net, medication, companionship, and scam rules. Non-negotiable.
4. `docs/DESIGN.md`: senior-friendly screen rules
5. `docs/PLAN.md`: build order and current status. Update it whenever you finish something.

## Skills to use

Before starting any task, check this list and use every skill that applies. Say which skill you're using and why.

Our project skills (in `.claude/skills/`):

| Skill | Use it when |
| --- | --- |
| `/meta-model-api` | writing or changing any code that calls Meta's API |
| `/safety-check` | before calling done any feature that touches symptoms, the diary, medications, mood, loneliness, crisis, the safety net, or scams |
| `/senior-friendly-ui` | before calling any screen done |
| `/demo-prep` | the final two days: demo video and submission |

Helper skills from other projects (also in `.claude/skills/`; see `THIRD_PARTY_NOTICES.md`):

| Skill | Use it when |
| --- | --- |
| `/systematic-debugging` | anything breaks or a test fails: find the real cause before changing code |
| `/test-driven-development` | building backend logic in `app/`, especially `app/safety.py`: write the failing test first. Not needed for HTML or CSS. |
| `/verification-before-completion` | before saying anything works or is done: run the command that proves it and show the result |
| `/webapp-testing` | checking a screen or flow in a real browser: screenshots, clicks, console errors |
| `/web-design-guidelines` | reviewing screens for accessibility and UX problems, before `/senior-friendly-ui` |
| `/requesting-code-review` | after finishing a whole feature from `docs/SPEC.md`: have a fresh reviewer subagent check it |
| `/receiving-code-review` | deciding what to do with review feedback |

Claude Code tools that replace the old Muse Code built-ins: plan mode for anything bigger than one small change, and to stress-test a plan (was `/plan` and `/grill`); the task list for multi-step work (was `/goal`); the `frontend-design` skill to polish screens (was `/taste`).

Rules for the helper skills:

- The hard rules below always win over any skill.
- If a skill says to commit, push, create branches, or use git worktrees, skip that part. The user saves progress with GitHub Desktop. Read-only git commands like `git diff`, `git log`, and `git show` are fine.
- Follow "Your shell" above when a skill shows a command (some skills were written for Mac or Linux).

## Stack (do not change without asking)

- Python environment: packages go in a virtual environment in `.venv` inside the project. Call `.venv\Scripts\python` directly. Don't run `Activate.ps1`, because PowerShell may block scripts.
- Backend: Python 3.12 or newer, FastAPI, Uvicorn. SQLite through Python's built-in `sqlite3`. The official `openai` Python package pointed at Meta's API for chat. `requests` for speech-to-text.
- Frontend: plain HTML, CSS, and JavaScript in `static/`, served by FastAPI. No React, no npm, no build step.
- Voice in: the browser records the microphone, converts it to 16 kHz mono 16-bit WAV in JavaScript, and posts it to our backend, which calls Muse Voice Transcribe.
- Voice out: the browser's built-in `speechSynthesis`. Meta has no text-to-speech model.
- Models in the app: `muse-spark-1.3` for conversation and reasoning, `muse-voice-transcribe-1.0` for speech-to-text. Standard models only. Never use a `-contributor` model in the app, because it handles health information.
- Every call to Meta lives in `app/meta_client.py`. Nothing else talks to `api.meta.ai`.

## Hard rules

- Never give medical, mental-health, or food advice in any prompt, reply, screen, or fixed message, beyond the fixed safety-net messages in `docs/SAFETY.md`.
- Never open, print, copy, or edit `.env`. The API key lives there. Read settings only through `app/config.py`. If a new setting is needed, tell the user exactly what line to add to `.env` and why.
- Never put API keys or personal data in code, logs, commits, test files, or the frontend. All Meta API calls happen in the backend.
- Follow `docs/SAFETY.md` exactly. `app/safety.py` runs before the AI on every message, and its fixed messages are never replaced by AI text.
- Ask before adding any new Python package, and keep `requirements.txt` up to date.
- Build one feature at a time. Get it working end to end and tested, then move on.
- Write pytest tests in `tests/` for backend logic, especially `app/safety.py`. Mock every Meta API call in tests. Tests must never call the real API. The only real call is `scripts/check_meta.py`, run by hand.
- Do not commit or push. The user saves progress with GitHub Desktop. Remind them to commit after each working feature.
- Use made-up demo data only. Never put real health information in code, seeds, tests, or docs.
- Before running a command that needs the internet (installing packages, calling `api.meta.ai`), say what it is and why.
- Keep code simple and well commented. A beginner has to understand it well enough to explain it to judges.

## How to run (once the app exists)

```powershell
python -m venv .venv                                     # once: create the project's Python environment
.venv\Scripts\python -m pip install -r requirements.txt  # install packages
.venv\Scripts\python scripts\check_meta.py               # check the API key and billing (one tiny real call)
.venv\Scripts\python -m uvicorn app.main:app --reload    # start the app
.venv\Scripts\python -m pytest                           # run tests
```

Then open http://localhost:8000 in Chrome or Edge and allow the microphone.

## Definition of done for any feature

- It works in the browser end to end, including by voice where it applies. Screens are checked with `/webapp-testing`.
- You ran the commands that prove it works and showed the results (`/verification-before-completion`).
- It passes `/safety-check` (if it touches health, mood, meds, the safety net, or scams), and `/web-design-guidelines` plus `/senior-friendly-ui` (if it has a screen).
- Its backend logic has tests, and `.venv\Scripts\python -m pytest` passes.
- `docs/PLAN.md` is updated.
- You told the user how to test it by hand and reminded them to commit.
