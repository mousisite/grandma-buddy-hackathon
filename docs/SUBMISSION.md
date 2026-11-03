# Submission text (ready to paste)

For the form at https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit, due Wednesday, Nov 4, 2026, 9:00 PM Eastern (6:00 PM Pacific). Aim for noon Pacific. Fill the two blanks (your name, the video link) and paste each part into the matching box; shorten where a box has a limit.

## Project name

Grandma Buddy

## One line

A voice companion for an older adult who lives alone: it talks with her, reminds her about her pills, keeps a diary for her doctor, checks scams, and never gives medical advice.

## Track and theme

Indie developer track. Theme "Build for Your World": built for my grandma.

## Team

(your name, as it should appear) — the only member.

## Links

- Code (public): https://github.com/mousisite/grandma-buddy-hackathon
- Demo video (3 minutes): (paste the unlisted YouTube link, tested in a private window)
- Live demo: (paste the Render link if you deploy it, otherwise leave this out)

## Description

Grandma Buddy is a voice companion for an older adult who lives alone. She talks to it; she never types. Every day it checks in on how she feels, reminds her to take her pills, keeps a symptom diary in her own words, writes up plain notes for her next doctor visit, sends a short update to the family member she chose, and checks suspicious letters and messages for scams. It also finds her glasses or keys in a photo of the room, reads her letters and bills aloud, and paints a Memory book from the stories she tells.

The AI never gives medical, mental-health, or food advice. A rules-based safety net runs before any AI call on every message: emergency words open a red "call 911" screen, poison words open Poison Control, crisis words open a calm screen with 988 and her family. Those screens are fixed text, never written by a model. When she asks for advice, Buddy says it can't give any and offers to call her doctor or family, or to add a question to her doctor notes. A second check reads every reply before it is spoken.

Everything runs on her own computer: a small Python server, a plain web page, and a local open voice model (Kokoro) so Buddy sounds the same in every browser and nothing she says leaves the computer except the words Meta's models need. The screens are made for weak eyesight and shaky hands: big type, big buttons, one main action per screen, everything read aloud, light and dark.

## How it uses Meta's models

- **Muse Spark 1.3** is Buddy's mind: the conversation, function calling (logging her mood, symptoms, pills, and diary; opening screens; drafting a message to her family), structured outputs (the scam verdict, the doctor notes, what a letter says), image input (reading bills and letters, describing an old photo for the Memory book), and web search (today's weather and news in two sentences with its sources, and a look-up of a suspicious phone number or website).
- **Muse Voice Transcribe 1.0** hears her: the microphone streams to Meta's realtime endpoint through our server, with her medication and family names as keyword hints, so Buddy talks hands-free and knows when she has finished a sentence. Tap-to-talk uses the batch endpoint.
- **Muse Image 1.0** paints her Memory book pages and the daily postcard her family sees.
- **SAM 3.1** finds her glasses, keys, or remote in a photo of the room and draws a halo around them.

Standard models only (never a contributor model), because the app handles health information.

## How we tested it

Three verification layers, as Meta's workshops put it: mandatory rule checks (plain code before the AI on every message, and again on every reply), an AI judge (Muse Spark with a strict JSON rubric), and a human in the loop (the family checks every pill label, she decides every call, a person read every test reply). A 42-turn test set ran at reasoning effort minimal, low, and medium: minimal was the fastest (3.4 s a reply), the cheapest, as warm as low (4.91 of 5), and after one fix it passed 41 of 42; medium thought six times longer and scored lowest. Buddy uses minimal. The write-up with the chart is docs/EVAL.md. 844 automated tests, every Meta call faked.

## Built during the hackathon

The repository was created on October 26, 2026, the kickoff day, and all of the app's code was written between October 26 and November 4; the commit history shows it. The Day 1 skeleton (server, database, first screen) was made with Muse Code, Meta's coding agent; everything after that with Claude Code. The idea, the plan, and the agent instructions were written before the event. Third-party pieces and their licenses are listed in THIRD_PARTY_NOTICES.md.

## How to try it (Windows)

Clone the repository, put a Meta Model API key in `.env`, and double-click `start.bat`. It makes the Python environment, installs the packages, loads a made-up demo week for "Rose", and opens http://localhost:8000. Tests: `.venv\Scripts\python -m pytest` (815 tests, every Meta call faked).

## Short version (about 90 words)

Grandma Buddy is a voice companion for an older adult living alone, built for my grandma. She just talks: it checks in daily, reminds her about her pills, keeps a symptom diary for her doctor, keeps her company, updates her family, checks scams, reads her letters, and finds her glasses in a photo. Muse Spark thinks, Muse Voice Transcribe listens, Muse Image paints her memory book, SAM finds her things. A rules-based safety net runs before the AI, and the AI never gives medical advice. Everything runs on her own computer.
