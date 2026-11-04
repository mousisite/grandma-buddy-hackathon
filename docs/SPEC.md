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
- At each time, a calm card pops up at the top of whatever screen is open (never red) and Buddy reads it aloud with her name: "Rose, it's time for your evening Metformin. The label says: ...". The card shows Buddy's small orb, each label exactly as typed, and two big buttons: "I took it" and "Remind me in 10 minutes". A reminder that comes before her first tap on the page (browsers stay silent until then) is read right after that tap.
- For the demo video, `?demo=reminder` in the address (for example `http://localhost:8000/?demo=reminder`) pops up the card for her next pill 2 seconds after the first tap, as if it were due now. It saves nothing: her real reminders don't change, so it can be shown again and again.
- She can also say "I took my pills" to the companion.
- On the Pills screen, every pill of the day has a round check she can tick or untick, the ones still to come included: a tap marks it taken (on time, a little early, or late); a tap on a filled check undoes a tick made by mistake, and the pill goes back to what the clock says (later today, time to take it now, so the card comes back, or not taken 2 hours later with no answer). Nothing of the mistake is kept, and her family's page and update count it the same way.
- Missed doses (no answer after 2 hours) are logged and appear in the family update. A daily pill repeats every day: on the days after it was set up, every time of the day is there, and a dose she never marked shows as "Not taken" on her Pills screen, even if Buddy wasn't open at the time (a pill added today only gets the times from then on).
- The app only repeats what the label says. It never suggests doses or changes.
- **A photo of the bottle** (in Set up pills, "Take a photo of the bottle"): Muse Spark reads the name and the label as printed into the form; a box under each says "I checked this against the bottle", and Save waits until both are ticked. The times are always typed by the family. A photo Buddy can't read, or Buddy being down, says so kindly and leaves the form to be typed.
- Done when: a reminder fires on time while the app is open, taken and missed doses are logged correctly, and the bottle photo fills the form (tested with Meta faked: trimmed to the form's limits, nothing stored, bad photos refused kindly) with the browser check proving Save waits for both boxes.

### 5. Daily check-in (P1)

- The first time she opens the app each day, the companion asks three gentle questions, one at a time: how she is feeling, whether anything hurts or feels different, and whether she took her morning pills.
- It saves her mood, adds any symptom to the diary, and marks pills taken, using tools (function calling). No advice.
- Home's Today list shows it as done once she has said how she feels in today's check-in: her mood, a check, and "Done" instead of "Start". "Not today" shows "Skipped for today", and she can still start it.
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
- A phone number or web address in the message is looked up on the web while the AI reads it: "The phone number in it has been reported as a scam online." (and the verdict becomes Likely scam) or "Nothing was found online about the website in it. That doesn't make it safe.", with the sites named. The number or address itself is never read back to her; a photo is never looked up.
- Done when: the scam test messages in `docs/SAFETY.md` get the right verdicts, and the lookup can only make a verdict stronger, never repeats the number, counts toward the day's searches, and is skipped for photos and when the web is down (all tested with Meta faked).

### 8. Doctor visit notes (P1)

- She or a family member picks a time range (last 7, 14, or 30 days).
- Muse Spark turns the diary, mood, and medication logs into one clear page: her symptoms by date in her own words with pain levels, missed doses, how her mood has been, and the questions she wants to ask.
- It only organizes what she said. It never adds interpretation, guesses at causes, or suggests treatment.
- She can add a question any time by saying "I want to ask my doctor about ...".
- Each question still to ask has a quiet "Mark as asked" button. An asked question stays on the page for the days shown, with a check and "Asked" (and Undo); it is never deleted.
- Print button prints the page (or saves it as a PDF).
- Done when: notes for a week of demo data fit on one printed page and contain only facts from the logs.

### 9. Family updates (P2)

- A daily summary: mood, pills taken or missed, new diary entries, and any safety-net events.
- The pills line counts the same reminders as the Pills screen, those still to come included: "Pills: 2 of 3 taken. Still to come: Metformin at 6:00 PM." Each pill not taken is named with its time: missed, due now, or still to come.
- "Email to {family}" opens her email app with the summary already written (a `mailto:` link), so no email passwords are stored. A "Copy" button is there too.
- Done when: the summary for a demo day is accurate and the email opens pre-filled.

### 10. Memory book (P1)

- She tells Buddy a story from her life: from "Tell Buddy a memory" on the Memory book screen, or in ordinary talk ("I want to tell you a memory"), where Buddy offers to save it.
- Buddy listens and asks one or two gentle questions, one at a time (when was it, who was there).
- Muse Spark writes a short page in her own voice: a title and 2 or 3 warm paragraphs. It keeps her details and never invents facts. Plain code checks that every name and number came up in her talk with Buddy (so "Was Maria there?" "Yes!" keeps Maria).
- Muse Image paints one picture for it, always in the same soft watercolor-storybook style. No photorealistic faces of real people.
- The Memory book shows the pages newest first as cards (picture, title, date). Cards side by side are the same height, a title takes up to two even lines, and the dates line up. Each opens as a full page with "Send to {family}" (the family update's email link) and "Print". New pages appear in the family update.
- It fights loneliness by turning her stories into a keepsake for her family. No advice of any kind, and the safety net still runs first on everything she says.
- Done when: a told memory becomes a page with a painting; a page with a name or number she never said, or with advice, falls back to her own words; and the family update names new pages.

### 11. First-time welcome and the demo week (P1)

- The first time (no name saved), Buddy's orb greets her and three short steps set her up, by voice ("Say it") or by typing: her name; one or two family members with phone numbers; pills now or later. Then Home says "Good evening, Rose".
- `scripts/seed_demo.py` fills every screen with a made-up week for Rose: three pills (mostly taken), two family contacts with 555 numbers, 5 check-ins with mixed moods, a knee pain that comes and goes in her own words, two doctor questions, one checked scam text, two painted Memory book pages, and what Buddy has learned about her. `--reset` saves a backup, then wipes and reseeds.
- Done when: the welcome works on a fresh database, and after seeding every screen is filled in.

### 12. Find my things (P1)

- She can't find her glasses, keys, TV remote, or pill bottle. From the "Find my things" chip on Home, or by voice ("Buddy, where are my glasses?" gives a "Find my glasses" button), she says or types what she's looking for (quick picks for the usual things), then takes or chooses a photo of the room.
- SAM 3.1 finds the thing from a short text prompt ("glasses"). The photo shows with a soft glowing halo in Buddy's orb colors around it (not a box), and the rest of the room dims a little.
- Muse Spark 1.3 looks at the photo and says where it is in one plain sentence, read aloud: "Your glasses are on the side table, next to the lamp." If Spark is down, or its sentence isn't right for her, plain code says where in the photo it is instead.
- If nothing is found, Buddy says so kindly and asks for another photo, maybe from a different spot with the lights on.
- The safety net runs first on what she said. Her photo is never saved (and is sent to Meta with `store=false`). Buddy never reads labels, never says anything about medicines or health, and never describes people.
- Done when: it works on 3 made-up test photos with the real SAM 3.1 (`scripts/check_find.py`), every Meta call has a mocked test, and the result screen is checked in a browser.

### 13. Help and how Buddy works (P1)

- A Help screen (sidebar on desktop; Settings, "Help and how Buddy works", on phones; or by voice: "How do you work?" opens it).
- "How Buddy works": the 4 Meta models with what each does, then every feature with the models behind it, or "No AI" for the parts that run on this computer only (the safety net, pill reminders, the family update). The model names come from the app's settings (`/api/how`), so the page always says what really runs.
- "What Buddy never does", "Your privacy, in short", common questions that open one at a time, and a Call {family} button.
- The app refuses to start with a `-contributor` model in its settings.
- Done when: the page lists exactly the models in the settings (tested), the questions open, and it is checked in a browser at every width.

### 14. Today's weather, news, and sports (P1)

- "What's the weather today?": the forecast for her town from Open-Meteo (free, no key, the same source every time), said in plain words from a fixed table ("Cloudy today, with a high of 48 and a low of 41."), with "Weather from Open-Meteo.com" under it. "Anything happening in town?", "How did the Blazers do?": Buddy looks it up on the web with Meta's web search (the Responses API's `web_search` tool) near her town, and says it in one or two warm sentences, with where it read it under its words ("From the web: kgw.com").
- Home's Today list starts with today's weather ("Cloudy today, with a high of 48 and a low of 41." and a small "Weather from Open-Meteo.com" line), read aloud by a tap anywhere on its row. Every Today row is tappable as a whole, with a chevron on its link.
- A family member types her town in Settings, under Names and phone numbers. Only the town is sent.
- Only the weather, local news, and sports can be looked up (never health, medicine, or food), and every answer is checked by plain code first (docs/SAFETY.md section 8c).
- Done when: the request and the checks are tested with a fake Meta, and `scripts/check_briefing.py` gets real answers with sources for all three.

### 15. Talking without tapping (P1)

- In voice mode Buddy listens on its own: her words show live under the orb as she says them; when she stops talking (Meta's realtime speech-to-text hears the end of her turn), Buddy answers, then listens again. No tapping between turns.
- Buddy and she never talk at once: while Buddy thinks or speaks, only silence is sent. The talk button says what a tap does now: "Pause" while Buddy listens, "Stop and talk" while Buddy speaks (Buddy stops and listens).
- It stops after a minute of quiet, when she taps Pause, leaves the talk screen, puts the page in the background, or a safety screen opens. Settings has "Talk without tapping" (on); turned off, or where it can't work, it is tap to talk as before.
- Done when: the relay is tested with a fake Meta, `scripts/check_realtime.py --relay` hears two real turns through our relay, and the browser check covers live words, a turn, silence while Buddy speaks, listening again, Pause, and the fallback.

### 16. Read it to me (P1)

- A letter, a bill, or a form she can't read well. From the "Read it to me" tile on Home, or by voice ("Buddy, can you read this letter?" gives an "Open Read it to me" button), she takes or chooses a photo of it.
- Muse Spark 1.3 reads the photo; plain code decides what she hears (docs/SAFETY.md section 8d). Buddy says what it is and what it says, in plain words: "This is an electricity bill from Riverside Power & Light. It shows an amount due of $84.20 by November 15, 2026." The amount and the date show big, only when they are printed on the paper.
- "Read it word for word" shows the words big, line by line as printed, and reads them aloud ("Stop reading" while it does). "Say it again" repeats what Buddy said.
- A paper about her health (a doctor's letter, test results, an appointment, a pill label) is never explained: Buddy offers to read it word for word and says who is the right person to ask, with Call {doctor} first.
- A likely scam is said out loud, with its warning signs; its phone number and link are never read out. "Check it for a scam" checks the words in one tap. Every paper has Call {family}.
- Her photo is never saved, and nothing from the paper is kept. The last paper stays on the screen until she taps "Read another paper".
- Done when: the checks are tested with a fake Meta, `scripts/check_read.py` reads three made-up papers right with the real model (a bill, a clinic letter, a prize scam), and the browser check covers the screen at every width.

### 17. The landing, Privacy, and Terms (P1)

- `/about` is for the family member who sets Buddy up: what Buddy does (with real screens of the made-up demo week), the four Meta models behind it, the promise (no medical advice, real people first, her data stays with her), two plans (Buddy on her computer, free; Family, $9 a month, coming in November, in Stripe's test mode only), questions, and Open Buddy. The app's own design system, with Buddy's orb alive at the end.
- `/privacy` and `/terms`, in plain words: what the app keeps and where, what goes to Meta and why, what is never kept, what her family sees, and what Buddy is not (a doctor, an emergency service). Help links to all three.
- The pages make no claim the app can't keep, and ask for nothing: no form, no card.
- Done when: the pages are served and tested (every model name comes from the settings, every picture is in the repository, no form fields), and the browser check covers them at phone and desktop width, light and dark.

### 18. Family accounts, the family page, and notifications (P1)

- In her Settings, under "Family accounts" (for a family member): an invite code (six letters, 24 hours, one use), the list of who can sign in with Remove, and "What your family can see": her mood, her pills, her diary and memory book pages in her own words, and safety screens (mood, pills, and safety on from the start; the diary off until she turns it on). The switches shape the family page; on her own computer, anyone using Buddy already sees everything, and the Settings copy says so.
- The family page (`/family`): join with the code, a name, an email, and a password (never stored: an scrypt hash), or sign in. Then her day, today or the two days before: what needs a look (a missed pill, a safety screen), whether she talked with Buddy, her mood, her pills (taken of all, and each not taken), her diary in her words, and her memory book pages, each only as she shares it. It asks again every 30 seconds.
- Notifications, plain words from the app: on her side, a pill reminder as a system notification while Buddy is hidden ("Remind me even when Buddy is hidden" in Settings, which asks the browser first); on the family's side, "Rose needs a look" when something new appears while the page is open ("Notify me on this device").
- Safety screens reach the family as a kind and a time with a fixed sentence, never her words (docs/SAFETY.md 9a). Five wrong passwords in 15 minutes lock that email for 15 minutes. Another website can't sign in or read her day.
- Done when: the accounts, sessions, lock, sharing switches, and the day's facts are tested (no Meta involved), `scripts/seed_demo.py` adds Maria's account, and the browser check covers the invite, joining, her day, Yesterday's alert, the switches, sign out and in, both notifications, and Remove.

### 19. The Family plan: checkout and billing (P1)

- On the family page, "Your plan": the Free plan (everything Buddy does for her), or the Family plan, $9 a month, with when it renews and "Cancel at the end of the period" (it stays until then).
- Payments go through Stripe's hosted Checkout in TEST MODE only: our app opens a session and sends the family member to Stripe's own page, so it never sees a card number. Back at `/billing/return`, the app asks Stripe about the session (never the address bar) and records the plan only if it is a test-mode session, finished, paid, this family member's, a subscription, and $9. The same session twice records it once. A key that isn't a test key (`sk_test_…`) refuses to start.
- With no key, demo mode: "Demo mode, no real charge", the plan starts with one tap for 30 days, and there are no card fields anywhere.
- Nothing Buddy does for her is ever behind the plan (a test checks that no file of hers even mentions billing).
- Done when: the checkout request, the return checks (each way a session can fail to check out), demo mode, cancelling, and the live-key refusal are tested with Stripe faked; `scripts/check_stripe.py` opens one real test-mode session; and the browser check covers demo mode with no card fields.

### 20. A memory page from an old photo (P1)

- In the Memory book, "Start from an old photo": she picks a photo; Buddy says what it shows and asks one question ("A sunny kitchen with a blue teapot on the table. What do you remember about this kitchen?"), and a memory talk begins. She tells the story as usual; the page is written from her words.
- SAM 3.1 checks the photo for people. With people, her own photo is the page's picture, kept on this computer and never repainted; without, the book's watercolor is painted and her photo shows under the story. Unsure counts as people (docs/SAFETY.md 8e).
- Buddy never says who anyone is, never reads writing in the photo, and never mentions health, age, or looks; a description that breaks a rule is dropped for fixed words.
- Done when: the person check (both ways, and SAM down), the description's checks, the page from a photo, and the day-old cleanup are tested with Meta faked; `scripts/check_photo_memory.py` runs the real SAM and Spark on two made-up photos; and the browser check covers the button, the talk's opening, and the finished page.

### 21. An installable app, offline states, and her data (P1)

- Buddy installs like an app: a manifest with icons drawn from Buddy's own orb, opening full screen from her home screen or desktop ("Install app" in Chrome or Edge). A service worker keeps the app shell (the page, styles, scripts, fonts, icons) on the device, network first, so a change arrives at once; it never keeps anything under `/api/`. When the app's own server isn't running, a plain page says so ("Buddy isn't running right now") with the 911 note.
- No internet: a calm line at the top says what still works (pill reminders, the safety net) and what doesn't (talking with Buddy). Each feature keeps its own kind words when the internet or the AI is down.
- "Her data" in Settings, for a family member: **Export everything** (one zip: a whole copy of the database, her memory book pictures and photos, and a README; never `.env`, never backups) and **Delete everything** (a sheet that asks for the word DELETE, typed; then every table emptied, ids from 1 again, the file shrunk, pictures, photos, and old backups gone, this device's remembered choices cleared, and Buddy opens on the welcome).
- Done when: export and delete are tested (the zip's contents, the exact word, the empty tables and the shrunk file, another website refused), the manifest's icons exist and the service worker never caches `/api`, and the browser check covers the worker on duty with the shell kept, the offline note, a real download, and the delete sheet ending on the welcome.

### 22. Message Maria and the daily postcard (P1)

- On the Family screen (and from Home's "Message Maria" chip, by her family member's name): she says a message (or types it), Buddy reads it back, and she taps **Send to Maria**. The safety net runs on it first; a message that needs a safety screen shows it and is never sent. It lands on the family page under "Messages from Rose" (with a notification for a family member who asked for them), and "Sent today" shows it under the box. Nothing is emailed or texted: the family page is where it goes, and Buddy never sends anything by itself.
- In a talk, "Tell Maria the tulips came up" makes Buddy show **Send this to Maria** with her words; it opens the Family screen with them in the box, to read over and send. The words are always hers (`tools.her_own_words`), never the AI's.
- **Maria writes back** from the family page ("Write to Rose"). Her Family screen shows the thread both ways, newest first; a new one from the family is marked New, Buddy reads it to her as their words ("Maria wrote: …"), and it then counts as seen. Home's Today list starts with "A message from Maria" while one waits, and Buddy's greeting says a message is waiting (without reading it). Unseen messages from the last 7 days stay on her screen until she has seen them.
- **A voice message.** On the family page, "Record a voice message": tap, speak, tap "I'm done". The recording (a small WAV, kept on this computer) reaches her Family screen as **Hear Maria**; Buddy says "Maria sent you a voice message." and plays it, in Maria's own voice. Muse Voice Transcribe writes down what it heard so the words show under it too (the voice still arrives when it can't). Home says "A voice message from Maria" while one waits. Her voice goes the other way too: after "Say it", her recording travels with the words she read over ("Maria will hear your voice too", or "Just the words"), and Maria's page plays it.
- **Today's postcard**: once a day, one cheerful thing she said to Buddy that day, word for word, with a picture painted for it in the Memory book's style. Plain code drops every line about health first; Muse Spark only picks the line and describes a scene; plain code checks both; Muse Image paints, once a day. It is made the first time the Family screen is opened that day (the wash shimmers meanwhile). "Nothing nice to paint yet today" until she has talked; **Try again** when painting didn't work. **Send to Maria** puts it on the family page as "Her postcard"; before that the family doesn't see it.
- Done when: the message route runs the safety net first and never sends a flagged message, the tool offers only her words, a family member's reply or voice message needs a sign-in and reaches her as theirs (new until seen, named in the greeting and on Home; the recording kept, served, exported, and deleted with her data), the postcard is one painting a day from a checked line and scene (health lines never reach the picker, a bad pick or scene makes no postcard, a failed painting keeps nothing), the family page shows messages and only a sent postcard, `scripts/seed_demo.py` adds messages, yesterday's postcard, and a morning talk for today's, and the browser check covers the chip, Say it, Send, an emergency message, Try again, the postcard, Send to Maria, the talk button, and Maria's page with a notification.

## Not building (out of scope)

- Any medical advice: saying how serious a symptom is, what causes it, or what to do about it
- Food, diet, exercise, or home-remedy advice
- Mental-health advice, therapy, or coping techniques
- Diagnosing anything, prescribing, or suggesting medication or dose changes
- Calling 911 by itself (it shows a big button that dials; she decides)
- Storing her passwords, bank details, or Social Security numbers (a family member's sign-in keeps only a salted scrypt hash, never the password)
- Location tracking (the weather uses only the town a family member typed), or a sign-in for her: she never signs in, pays, or sets anything up; the family does, on the family page
- A phone app from an app store (it is a web page)

## Demo story (3 minutes maximum)

1. Morning check-in, hands-free: Buddy asks, she just talks, her words appear as she says them. She mentions her knee hurts; two follow-ups, and it's in her diary.
2. The pill reminder pops up and is read aloud with the label word for word. She taps "I took it".
3. She asks "Should I take something for it?" No advice: Buddy offers to call her doctor and adds the question to her doctor notes.
4. The safety net: "my chest feels tight" goes straight to the Call 911 screen, with no AI involved.
5. "Read it to me": a photo of a bill, Buddy says what it is and the amount due. Then a "your grandson is in jail, send gift cards" text: likely scam, and the web lookup says the number in it is reported.
6. "Find my things": a photo of the room, a glowing halo around her glasses, "on the side table, next to the lamp".
7. "Tell Maria the tulips came up": the Send this to Maria button, her words read back, sent to Maria's family page. Today's postcard, painted from what she said, sent too; Maria's page shows her day, the message, and the postcard.
8. Close on why: built for my grandma, during the hackathon, with Muse Spark, Voice Transcribe, Muse Image, SAM, and Meta's web search each doing the job it's best at.
