# Grandma Buddy: product spec

## The pitch

A voice companion for older adults who live alone. She just talks. It checks in every day, reminds her about her pills, keeps a symptom diary for her doctor, keeps her company, keeps her family in the loop, and spots scams.

It never gives medical advice. It listens, writes things down, reminds, and connects her with the people who can help: her family, her doctor, and emergency services.

## Who it is for

- **Grandma (main user).** Lives alone, is often lonely, finds phones hard to use, and deals with a lot of pain. She should never have to type, scroll through menus, or read small text.
- **A family member (helper).** Sets up her medications and contacts once, and receives a short daily update.

The app runs on one computer or tablet for one person. No accounts, no login.

## Hackathon fit

- Meta Global AI Developer Hackathon, Indie developer track, theme "Build for Your World".
- Judged on creativity, technical ambition, and whether it works.
- The guide lists "any project using AI to generate and give medical advice", "AI Mental Health Advisor", and "AI Nutrition Coach" as projects to avoid. This app is designed so the AI never does any of those. See `docs/SAFETY.md`.
- All app code is written during the hackathon (October 26 to November 4, 2026).

## Language

The app speaks and understands English, using Muse Voice Transcribe for speech. Keep the language as one setting (`LANGUAGE` in `.env`) so other languages can be added later.

## How it feels to use

Grandma opens the app. It greets her by name, says the date, and asks how she is feeling today. She taps one giant button, talks, and taps it again when she's done. The app shows what she said in big letters, answers in a warm voice, and shows the answer in big letters too. Everything important is one tap away from the home screen.

## Features in build order

Priority: **P0** must ship, **P1** should ship, **P2** nice to have. If we fall behind, cut from the bottom.

### 1. Voice conversation loop (P0)

- Big "Tap to talk" button. Tap to start, tap to stop (no holding). Recording stops by itself after 2 minutes.
- The backend sends the audio to Muse Voice Transcribe. The transcript appears in big text.
- Medication names and family names are sent as `keywords` so the speech model spells them right.
- The companion's reply appears in big text and is read aloud. A "Say it again" button replays it.
- Done when: a spoken sentence becomes text and a spoken reply in a few seconds, and a friendly message appears if the microphone is blocked or the internet is down.

### 2. Emergency safety net (P0)

- Plain Python rules (not AI) check everything she says for emergency warning signs, crisis words, and medication mix-ups (`docs/SAFETY.md`).
- A match shows a fixed full-screen message right away, with big buttons: Call 911 and Call {family}, Call 988 for crisis words, or Call Poison Control for medication mix-ups.
- It works even if the AI or the internet is down.
- Done when: every safety test phrase in `docs/SAFETY.md` shows the right screen, and the near-miss phrases don't.

### 3. Symptom diary (P0)

- She says "Something hurts" (button or voice) or mentions how she feels in conversation.
- The companion asks up to 3 short follow-up questions, one at a time: where, how bad from 0 to 10, since when, anything new.
- It saves a diary entry in her own words, then says something like: "I've written that down for your doctor. Would you like me to let {family} know?" with big Call {doctor} and Call {family} buttons.
- It never says how serious something is, what might be causing it, or what to do about it.
- If she asks for advice ("Should I go to the doctor?", "What should I take?"), it kindly says it can't give medical advice, offers to call her doctor or family, and offers to add the question to her doctor notes.
- Done when: diary entries save correctly, and the advice-seeking test phrases in `docs/SAFETY.md` get the no-advice answer.

### 4. Pill reminders (P0)

- A family member adds each medication: the name and dose exactly as written on the label, and the times of day.
- At each time, a big banner appears and is read aloud: "It's time for your morning pills: ..." with two big buttons: "I took it" and "Remind me in 10 minutes".
- She can also say "I took my pills" to the companion.
- Missed doses (no answer after 2 hours) are logged and appear in the family update.
- The app only repeats what the label says. It never suggests doses or changes.
- Optional (P2): take a photo of the pill bottle and Muse Spark reads the label to pre-fill the form. A family member must confirm every field before saving.
- Done when: a reminder fires on time while the app is open, and taken and missed doses are logged correctly.

### 5. Daily check-in (P1)

- The first time she opens the app each day, the companion asks three gentle questions, one at a time: how she is feeling, whether anything hurts or feels different, and whether she took her morning pills.
- It saves her mood, adds any symptom to the diary, and marks pills taken, using tools (function calling). No advice.
- Done when: after a check-in, the mood, diary, and pill logs show the right entries.

### 6. Companion chat (P1)

- Warm, patient, simple conversation, like a kind friend. Short sentences, one question at a time.
- It talks about her life, memories, family, hobbies, and the day. It remembers what she shared.
- When she sounds lonely, it listens and gently encourages real connection: "Would you like to call {family} today?" with a big call button.
- It is a friend, not a therapist: no psychological advice or coping techniques. Crisis words trigger the fixed crisis screen from the safety net.
- Feels like a friend she looks forward to talking to: warm, curious, a little playful; it reacts to what she said first, then asks one natural question; 1 to 3 short spoken sentences, varied openers, no lists; gentle jokes if she likes them.
- Remembers her life: people, pets, hobbies, shows, and plans (`remember_fact`), the last few days' talks, and follows up ("Did Tom make it on Sunday?").
- Starts conversations well: at the start of a conversation, "Good afternoon, Rose!" and a follow-up that's due, then it listens.
- Learns her over her first couple of days: while getting to know her it asks gentle questions about her life; then, from what it learned each day ("Prefers short replies", "Loves puns"), it talks the way she likes. She and her family can see and forget anything it learned (Settings).
- Done when: the companion test phrases in `docs/SAFETY.md` behave correctly and a lonely conversation ends with a gentle nudge toward a real person. `scripts/try_companion.py` (8 conversations with the real AI) reads warm, short, and safe.

### 7. Scam checker (P1)

- She reads a strange text or email out loud, pastes it, or takes a photo of it (Muse Spark can read images).
- Result: **Likely scam**, **Suspicious**, or **Looks safe**, with the red flags in plain words and what to do.
- Always: never share passwords, bank numbers, or Social Security numbers; hang up and call the real number yourself; call family before sending money.
- Done when: the scam test messages in `docs/SAFETY.md` get the right verdicts.

### 8. Doctor visit notes (P1)

- She or a family member picks a time range (last 7, 14, or 30 days).
- Muse Spark turns the diary, mood, and medication logs into one clear page: her symptoms by date in her own words with pain levels, missed doses, how her mood has been, and the questions she wants to ask.
- It only organizes what she said. It never adds interpretation, guesses at causes, or suggests treatment.
- She can add a question any time by saying "I want to ask my doctor about ...".
- Print button prints the page (or saves it as a PDF).
- Done when: notes for a week of demo data fit on one printed page and contain only facts from the logs.

### 9. Family updates (P2)

- A daily summary: mood, pills taken or missed, new diary entries, and any safety-net events.
- "Send to {family}" opens her email app with the summary already written (a `mailto:` link), so no email passwords are stored. A "Copy" button is there too.
- Done when: the summary for a demo day is accurate and the email opens pre-filled.

### 10. Memory book (P1)

- She tells Buddy a story from her life: from "Tell Buddy a memory" on the Memory book screen, or in ordinary talk ("I want to tell you a memory"), where Buddy offers to save it.
- Buddy listens and asks one or two gentle questions, one at a time (when was it, who was there).
- Muse Spark writes a short page in her own voice: a title and 2 or 3 warm paragraphs. It keeps her details and never invents facts. Plain code checks that every name and number came up in her talk with Buddy (so "Was Maria there?" "Yes!" keeps Maria).
- Muse Image paints one picture for it, always in the same soft watercolor-storybook style. No photorealistic faces of real people.
- The Memory book shows the pages newest first as cards (picture, title, date). Each opens as a full page with "Send to {family}" (the family update's email link) and "Print". New pages appear in the family update.
- It fights loneliness by turning her stories into a keepsake for her family. No advice of any kind, and the safety net still runs first on everything she says.
- Done when: a told memory becomes a page with a painting; a page with a name or number she never said, or with advice, falls back to her own words; and the family update names new pages.

### 11. First-time welcome and the demo week (P1)

- The first time (no name saved), Buddy's orb greets her and three short steps set her up, by voice ("Say it") or by typing: her name; one or two family members with phone numbers; pills now or later. Then Home says "Good evening, Rose".
- `scripts/seed_demo.py` fills every screen with a made-up week for Rose: two pills (mostly taken), two family contacts with 555 numbers, 5 check-ins with mixed moods, a knee pain that comes and goes in her own words, two doctor questions, one checked scam text, two painted Memory book pages, and what Buddy has learned about her. `--reset` saves a backup, then wipes and reseeds.
- Done when: the welcome works on a fresh database, and after seeding every screen is filled in.

### 12. Find my things (P1)

- She can't find her glasses, keys, TV remote, or pill bottle. From the "Find my things" chip on Home, or by voice ("Buddy, where are my glasses?" gives a "Find my glasses" button), she says or types what she's looking for (quick picks for the usual things), then takes or chooses a photo of the room.
- SAM 3.1 finds the thing from a short text prompt ("glasses"). The photo shows with a soft glowing halo in Buddy's orb colors around it (not a box), and the rest of the room dims a little.
- Muse Spark 1.3 looks at the photo and says where it is in one plain sentence, read aloud: "Your glasses are on the side table, next to the lamp." If Spark is down, or its sentence isn't right for her, plain code says where in the photo it is instead.
- If nothing is found, Buddy says so kindly and asks for another photo, maybe from a different spot with the lights on.
- The safety net runs first on what she said. Her photo is never saved (and is sent to Meta with `store=false`). Buddy never reads labels, never says anything about medicines or health, and never describes people.
- Done when: it works on 3 made-up test photos with the real SAM 3.1 (`scripts/check_find.py`), every Meta call has a mocked test, and the result screen is checked in a browser.

## Not building (out of scope)

- Any medical advice: saying how serious a symptom is, what causes it, or what to do about it
- Food, diet, exercise, or home-remedy advice
- Mental-health advice, therapy, or coping techniques
- Diagnosing anything, prescribing, or suggesting medication or dose changes
- Calling 911 by itself (it shows a big button that dials; she decides)
- Storing passwords, bank details, or Social Security numbers
- Location tracking, logins, or multiple users
- A phone app from an app store (it is a web page)

## Demo story (3 minutes maximum)

1. Morning check-in by voice. She mentions her knee hurts. The companion asks two follow-ups and writes it in her diary.
2. Pill reminder pops up and is read aloud. She taps "I took it".
3. She asks "Should I take something for it?" The companion doesn't give advice. It offers to call her doctor and adds the question to her doctor notes.
4. The safety net: "my chest feels tight" goes straight to the Call 911 screen, with no AI involved.
5. She reads a fake "your grandson is in jail, send gift cards" text. Verdict: likely scam.
6. Print the doctor notes. Show the family update.
7. Close on why: built for my grandma, and built during the hackathon.
