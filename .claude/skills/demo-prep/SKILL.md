---
name: demo-prep
description: Get Grandma Buddy ready for the Meta hackathon submission - final checks, secrets sweep, public repository, README, demo data, a demo video of 3 minutes or less, and the submission form. Use on Nov 3 and Nov 4, 2026, or when the user says it's time to prepare the demo or submit.
---

# Demo prep

The deadline is Wednesday, Nov 4, 2026 at 9:00 PM Eastern (6:00 PM Pacific). Aim to submit by noon Pacific. The Indie track is judged on creativity, technical ambition, and whether it works. Judges use the demo video, the code, and the live product.

## 1. Re-read the rules

Read "Submission requirements" in `docs/PLAN.md`. The key ones:

- The repository must be public.
- The demo video is 3 minutes or less and shows only what was built during the hackathon.
- Everything presented must be built during the event, and that must be clear.
- Submit at https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit and list everyone who worked on it.

## 2. Make sure it works from scratch

- `.venv\Scripts\python -m pytest` passes.
- Ask the user to make a fresh copy of the repository (clone it with GitHub Desktop into a new folder), copy their `.env` in, create the environment with `python -m venv .venv`, install with `.venv\Scripts\python -m pip install -r requirements.txt`, and run the app. Fix anything that breaks.
- Walk through every P0 and P1 feature in `docs/SPEC.md` by voice.
- Run `/safety-check` one last time. Ask two advice questions by voice and confirm there's no advice in the replies.

## 3. Secrets and privacy sweep (before making it public)

- `.env` is not in the repository. Check GitHub Desktop's History tab and the files on GitHub.
- Search the code for anything that looks like a key. In PowerShell: `Get-ChildItem app, static, scripts, tests -Recurse -File | Select-String -Pattern "MODEL_API_KEY=|Bearer [A-Za-z0-9]"`. It should find nothing. Only `app/config.py` reads the key, and it reads it from the environment.
- No real health information anywhere: code, seeds, tests, screenshots, or the video.
- `data/`, `.venv/`, `test-output/`, and any `.db` files are not committed.
- Then ask the user to make the repository public: on github.com, open the repository, then Settings, then the "Danger Zone" section, then "Change visibility" to Public.

## 4. Demo data

Run `scripts/seed_demo.py` to load a made-up week for "Rose": two medications, a few check-ins, a knee pain that comes and goes, one low-mood day, one scam text. Never use real people's information.

## 5. README for judges

Update `README.md` so it covers:

- What it is and who it's for (the grandma story in 2 or 3 sentences)
- Features, with a screenshot of each main screen
- How it uses Meta's models: Muse Voice Transcribe (speech, with keyword biasing for medication and family names), Muse Spark 1.3 (conversation, function calling, structured outputs, image input)
- Safety design: rules-based safety net, no medical advice by design, standard models only
- "Built during the hackathon": the plan and coding-agent setup were written first, and all app code was written between Oct 26 and Nov 4, 2026, which the commit history shows
- How to run it (Windows steps) and how to run the tests
- What's next (ideas we didn't have time for)
- Built with coding agents: the Day 1 skeleton with Muse Code, everything after with Claude Code, plus the helper skills listed in `THIRD_PARTY_NOTICES.md`

## 6. Demo script (3 minutes maximum)

Use the demo story at the end of `docs/SPEC.md`. Write the exact lines the user will say into the microphone, with a rough time for each part, and practice once before recording. Show the voice loop in the first 20 seconds, show the safety net and the no-advice answer, and end on the "why". Only show features built during the hackathon.

## 7. Recording tips (Windows)

- Record with OBS Studio (free) or the Snipping Tool's screen recording.
- Close other windows and notifications. Zoom the browser to 125% so text is readable in the video.
- Record the microphone so judges hear the voice conversation and the spoken replies.
- Upload to YouTube as Unlisted (or another host), then open the link in a private window to make sure anyone can watch it.

## 8. Final checklist

- [ ] Tests pass and the app runs from a fresh copy
- [ ] No secrets or real health data in the repository or video
- [ ] Repository is public, and `LICENSE` is in place
- [ ] README complete, with screenshots and the "built during the hackathon" section
- [ ] Demo video is 3 minutes or less, and the link works for anyone
- [ ] Submitted at the Cerebral Valley link, with everyone listed, and the confirmation saved
