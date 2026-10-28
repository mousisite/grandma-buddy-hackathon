# Grandma Buddy

A voice companion for older adults who live alone, built with Meta's Muse models during the Meta Global AI Developer Hackathon (Indie developer track, "Build for Your World").

> Draft. Finish this on Day 9 with screenshots, run instructions, and the demo link (see `.claude/skills/demo-prep/SKILL.md`).

## Why

I'm building this for my grandma. She is often lonely, struggles to use her phone, and deals with a lot of pain. I want her to have help every day, just by talking.

## What it does

- **Talks with her.** She taps one big button and speaks. It answers in a warm voice and in big text.
- **Daily check-in.** Asks how she feels, whether anything hurts, and whether she took her pills.
- **Symptom diary.** She describes what she's feeling, and it writes it down in her own words for her doctor and family.
- **Pill reminders.** Spoken reminders with "I took it" and "Remind me in 10 minutes".
- **Companion.** Keeps her company and encourages her to call family.
- **Scam checker.** Reads a suspicious text, email, or photo of one, and explains whether it looks like a scam.
- **Doctor visit notes.** Turns the week's diary, pills, and mood into one printable page.
- **Family updates.** A short daily summary for a family member she chooses.
- **Safety net.** If she mentions emergency warning signs, crisis words, or a medication mix-up, a fixed screen with big Call 911, Call 988, or Call Poison Control buttons appears.

## It never gives medical advice

The AI listens, writes things down, reminds, and connects her to real people: family, her doctor, and emergency services. It never says how serious something is, what causes it, or what to do about it. The safety-net screens use fixed text from plain rules, not AI.

## How it uses Meta's models

- **Muse Voice Transcribe** turns her speech into text, with keyword biasing so her medication and family names come out right.
- **Muse Spark 1.3** runs the conversation, calls tools to write diary entries, track pills, and save doctor questions (function calling), returns scam verdicts and doctor notes as structured JSON, and reads photos of messages and pill labels.

## How it was built

- The Day 1 skeleton (server, database, first home screen) was made with **Muse Code**, Meta's coding agent.
- Everything after that is built with **Claude Code**, Anthropic's coding agent.
- Both used the same plan in `docs/` and the helper skills credited in `THIRD_PARTY_NOTICES.md`.

## Built during the hackathon

This repository was created on October 26, 2026, the hackathon's kickoff day. I planned the idea and set up my tools before the event. The plan is in `docs/`, and the coding agent's instructions are in `AGENTS.md` (loaded through `CLAUDE.md`) and `.claude/skills/`. All of the app's code was written during the hackathon (October 26 to November 4, 2026), and the commit history shows it.

## Privacy

Her data stays in a database file on her own computer. The app uses Meta's standard models, which aren't trained on her conversations.

## Run it

Coming on Day 9.

## License

MIT. See `LICENSE`.
