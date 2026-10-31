# Grandma Buddy

A voice companion for older adults who live alone, built with Meta's Muse models during the Meta Global AI Developer Hackathon (Indie developer track, "Build for Your World").

> Draft. Finish this on Day 9 with screenshots, run instructions, and the demo link (see `.claude/skills/demo-prep/SKILL.md`).

## Why

I'm building this for my grandma. She is often lonely, struggles to use her phone, and deals with a lot of pain. I want her to have help every day, just by talking.

## What it does

- **Talks with her, hands-free.** She taps one big button once and just talks: her words appear as she says them, Buddy answers when she stops (in a warm voice and big text), then listens again. Buddy never listens while it is talking itself, and she can pause any time.
- **Daily check-in.** Asks how she feels, whether anything hurts, and whether she took her pills.
- **Symptom diary.** She describes what she's feeling, and it writes it down in her own words for her doctor and family.
- **Pill reminders.** Spoken reminders with "I took it" and "Remind me in 10 minutes".
- **Companion.** Keeps her company and encourages her to call family.
- **Scam checker.** Reads a suspicious text, email, or photo of one, and explains whether it looks like a scam.
- **Doctor visit notes.** Turns the week's diary, pills, and mood into one printable page.
- **Family updates.** A short daily summary for a family member she chooses.
- **Memory book.** She tells Buddy a story from her life; it becomes a page in her own words with a painting, to share with her family.
- **Find my things.** Can't find her glasses, keys, or TV remote? She says what she's looking for and takes a photo of the room. Buddy circles it with a soft glow and tells her where it is: "Your glasses are on the side table, next to the lamp."
- **Read it to me.** A letter, a bill, or a form she can't read well? She takes a photo, and Buddy says what it is and what it says ("an electricity bill, $84.20 due by November 15"), or reads it word for word, big on the screen. A letter about her health is never explained, only read to her, and a letter with the signs of a scam says so out loud.
- **Today's weather and news.** "What's the weather today?" or "Anything happening in town?": Buddy looks it up on the web near her town and says it in a sentence or two, showing where it read it. Home starts its Today list with the weather. Never anything about health.
- **Help and how Buddy works.** Shows every feature with the Meta model behind it (read from the app's own settings), what Buddy never does, privacy in plain words, and common questions.
- **Safety net.** If she mentions emergency warning signs, crisis words, or a medication mix-up, a fixed screen with big Call 911, Call 988, or Call Poison Control buttons appears.

## It never gives medical advice

The AI listens, writes things down, reminds, and connects her to real people: family, her doctor, and emergency services. It never says how serious something is, what causes it, or what to do about it. The safety-net screens use fixed text from plain rules, not AI.

## How it uses Meta's models

- **Muse Voice Transcribe** turns her speech into text, with keyword biasing so her medication and family names come out right. Live, over Meta's realtime WebSocket in ENDPOINTING mode: her words stream back as she speaks, and Meta hears when she has finished her turn, so she never has to tap. The key stays on our server, which relays her microphone.
- **Muse Spark 1.3** runs the conversation, calls tools to write diary entries, track pills, save doctor questions, remember her life, and open Find my things (function calling), returns scam verdicts, doctor notes, and Memory book pages as structured JSON, and looks at photos: messages she wants checked, the room where she lost something (to say where it is in plain words), and letters and bills she wants read to her (into a strict form that plain code checks before she hears a word).
- **SAM 3.1** (Segment Anything) finds the thing she lost in her photo from a short text prompt ("glasses"), so Buddy can draw a glowing halo in its own orb colors right around it. Her photo is sent with `store=false` and is never saved.
- **Muse Image** paints one soft watercolor picture for each Memory book page.
- **Meta's web search** (the Responses API's built-in `web_search` tool, with Muse Spark) grounds "what's happening today" in today's web: the weather, a cheerful local event, and sports scores, with their sources shown. Only her town is sent, and only those three topics can be searched.

Each model does the job it's best at, and plain Python rules (the safety net and the advice guard) check her words before any AI and Buddy's words after.

## How it was built

- The Day 1 skeleton (server, database, first home screen) was made with **Muse Code**, Meta's coding agent.
- Everything after that is built with **Claude Code**, Anthropic's coding agent.
- Both used the same plan in `docs/` and the helper skills credited in `THIRD_PARTY_NOTICES.md`.

## Built during the hackathon

This repository was created on October 26, 2026, the hackathon's kickoff day. I planned the idea and set up my tools before the event. The plan is in `docs/`, and the coding agent's instructions are in `AGENTS.md` (loaded through `CLAUDE.md`) and `.claude/skills/`. All of the app's code was written during the hackathon (October 26 to November 4, 2026), and the commit history shows it.

## Privacy

Her data stays in a database file on her own computer. The app uses Meta's standard models, which aren't trained on her conversations. Only Buddy's own page can use the app: requests that another website sends to it are refused.

## Run it

Coming on Day 9.

## License

MIT. See `LICENSE`.
