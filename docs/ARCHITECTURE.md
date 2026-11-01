# Grandma Buddy: architecture

## The big picture

```
 Grandma's browser (Chrome or Edge)                Our backend (Python, FastAPI)            Meta Model API
 ----------------------------------                -----------------------------            --------------
 Tap to talk -> recorder.js makes a WAV  --POST-->  /api/transcribe  ---------------------->  Muse Voice Transcribe
 Big text, read aloud                    <--JSON--  /api/chat
 Buddy's natural voice, one sentence     <--WAV---  /api/speak: Kokoro on this computer (no internet;
   at a time (browser voice as backup)                Meta has no text-to-speech model)
                                                      1. safety.py checks for warning signs
                                                         (plain rules, no AI, works offline)
                                                      2. companion prompt + tools  -------->  Muse Spark 1.3
                                                      3. tools read/write SQLite             (function calling,
                                                                                              structured outputs,
 Pill banner (checks every 30 seconds)   <--JSON--  /api/reminders                            image input)
 Diary, pills, scam, notes, family       <--JSON--  feature routes
 Memory book (shimmer, then the picture) <--JSON--  /api/memories
                                                      background: memories.make_page  ---->  Muse Spark 1.3 (writes the page)
                                                                                       ---->  Muse Image 1.0 (paints it)
 Find my things: a photo + "glasses"  --POST-->  /api/find (safety net first)
   the halo around it, the sentence    <--JSON--    finder.find  ----------------------->  SAM 3.1 (finds it: a box)
                                                                  ----------------------->  Muse Spark 1.3 (says where)
 Read it to me: a photo of a letter   --POST-->  /api/read
   what it is, what it says, read aloud <--JSON--   reader.read  ----------------------->  Muse Spark 1.3 (reads it into a form)
                                                    SQLite file: data/grandma_buddy.db
                                                    Pictures: data/memories/<id>.webp
```

Key ideas:

- The browser never talks to Meta directly. The API key stays on the backend.
- The safety net is plain Python that runs before any AI. Emergencies are caught even if the AI or the internet is down, and its messages are fixed text, never AI-generated.
- One AI "companion" handles conversation and uses tools to do things: write a diary entry, mark a pill taken, add a doctor question, show a call button. That is what makes it an agent, not just a chatbot.
- The AI never gives medical advice (`docs/SAFETY.md`). It records, reminds, and connects her to people.
- Reports (scam verdict, doctor notes, Memory book pages) use structured outputs (JSON schemas), so the screen can show clean cards instead of walls of text.
- The Memory book uses two Meta models together: Muse Spark writes her story as a page in her own words, and Muse Image paints its picture in one fixed watercolor style. Plain code checks the page first.
- Find my things also uses two together: SAM 3.1 finds her thing in the photo from a short text prompt, and Muse Spark looks at the same photo and says where it is ("next to the lamp"). The page draws the halo from SAM's box.

## Folder map

The plan and agent setup come first. All app code (`app/`, `static/`, `scripts/`, `tests/`) is written during the hackathon.

```
grandma-buddy-hackathon/
  AGENTS.md                  instructions the coding agent reads every session
  CLAUDE.md                  one line (@AGENTS.md) so Claude Code loads AGENTS.md
  README.md                  project description for GitHub and judges (finish on Day 9)
  LICENSE                    MIT license (the repo must be public and open source)
  THIRD_PARTY_NOTICES.md     credits for the helper skills from other projects
  .env                       YOU copy it in. Holds the API key. Never shared.
  .env.example               shows which settings go in .env
  .gitignore                 keeps .env, .venv, the database, and recordings off GitHub
  requirements.txt           Python packages
  PRODUCT.md                 who the app is for and its brand commitments (used by the design plugin)
  .impeccable/               design plugin settings (its mockups and review screenshots are git-ignored)
  docs/                      SPEC, ARCHITECTURE, SAFETY, DESIGN, PLAN
  .claude/skills/            project skills for the coding agent (Claude Code)
  app/
    __init__.py
    main.py                  creates the FastAPI app, serves static/, includes the routes
    config.py                reads settings from .env (only place that does); refuses a `-contributor` model
    security.py              only Buddy's own page may use /api: requests another website sends (Sec-Fetch-Site, Origin) and other host names are refused
    how.py                   "How Buddy works" for Help: every feature, the Meta models behind it (from the settings), what runs on this computer
    db.py                    SQLite connection, creates tables, small query helpers
    meta_client.py           ALL calls to Meta: chat(), structured() (a strict JSON form, with photos), paint() (Muse Image), segment() (SAM 3.1), search() (Muse Spark with Meta's web search), transcribe(), open_listening() (live speech-to-text over a WebSocket)
    safety.py                emergency, crisis, and medication mix-up rules with fixed messages
    prompts.py               system prompts for companion, diary, scam, notes, family
    family.py                the family update: one day in plain words (plain code, no AI) and its mailto: link
    memories.py              the Memory book: write the page (checked: only her names and numbers, no advice), paint it, the picture style
    briefing.py              today's weather, a cheerful local story, or sports, looked up on the web for her town (our code writes the question), checked (no links, no health or advice, 2 sentences), kept 3 hours, 30 searches a day at most
    finder.py                Find my things: what she's looking for as a short noun phrase, SAM's answer line, the surest match, Spark's sentence (checked) or plain words
    postcards.py             the daily postcard: her lines that day (every health line dropped first), Spark's pick (a number and a scene, checked), Muse Image's painting, one a day, shared only when she sends it
    voice_messages.py        a family member's voice message: the recording kept in data/voice-messages/ and served as it is, Voice Transcribe's words for the screen
    demo.py                  the demo week: Rose's made-up week, built relative to today (seed), a backup-and-wipe, reset; demo mode = no Stripe key
    her_data.py              export everything (a whole copy of the database by SQLite's own backup, her pictures, a README) and delete everything (tables emptied, VACUUM, pictures, backups, the voice's cache)
    billing.py               the Family plan: Stripe's hosted Checkout in test mode only (a session opened, the return checked with Stripe before the plan is recorded, cancel at the end of the period), or demo mode with no key
    accounts.py              family accounts: invite codes (six letters, 24 hours, one use), scrypt password hashes, session tokens (hashed, 30 days), five tries then 15 minutes
    reader.py                Read it to me: Spark reads a photo of a paper into a strict form; plain code decides what she hears (health papers never explained, every summary sentence checked, printed numbers only, scam signs said, a scam's number never read out)
    voice.py                 Buddy's natural voice: Kokoro (kokoro-onnx) on this computer, the voices on offer, WAV making, a cache of recent words
    notes.py                 Doctor notes: facts straight from the logs (plain code); the AI only groups, checked
    scam.py                  Check a message: red-flag rules (a floor the AI can't lower), the AI's verdict, fixed what-to-do, and the web lookup of a number or address in it (one word read by plain code, fixed words shown, never the number)
    tools.py                 companion tool definitions and what each one does
    reminders.py             pill reminder rules (upcoming, due, snoozed, taken, missed) with a clock tests can set
    labels.py                a pill from a photo of its bottle: Spark reads the name and the label as printed (strict form), plain code trims them; a suggestion the family checks, never saved here
    routes/
      companion.py           /api/chat, /api/transcribe
      diary.py               /api/diary
      meds.py                /api/meds, /api/reminders, /api/meds/label (a photo of the bottle: the name and the label as printed, to fill in the form)
      scam.py                /api/scam-check (the verdict, with `lookup`: what the web said about a number or address in it)
      notes.py               /api/doctor-notes, /api/doctor-questions (how many to ask, add, asked, reopen)
      family.py              /api/family/summary
      memories.py            /api/memories (the pages, a picture, save, paint again)
      find.py                /api/find (safety net first, then finder.find; the photo is never saved)
      read.py                /api/read (reader.read; the photo and the paper's words are never saved)
      family_accounts.py     /api/family/invite, accounts (Rose's Settings); /api/family/account, sign-in, sign-out, me, dashboard (the family page)
      billing.py             /api/billing (the plan), /checkout, /demo, /cancel; GET /billing/return (back from Stripe's page)
      data.py                /api/data/export (one zip of everything), /api/data/delete (with the word DELETE)
      demo.py                /api/demo (demo mode? the week loaded?), /api/demo/reset (the week over, demo mode only)
      messages.py            /api/messages (Send to Maria: safety net first, kept for the family page; today's list), /api/postcard/today (made now if it isn't yet), /send, /{id}/picture
      briefing.py            /api/briefing/{weather,news,sports} for Home's weather row
      listen.py              /api/listen (WebSocket): hands-free talking, her microphone live to Meta's realtime speech-to-text and her words back; only Buddy's own page, one at a time, 15 minutes at most
      voice.py               /api/voice (is the natural voice here, which voices), /api/speak (words in, WAV out)
      learned.py             /api/learned: what Buddy remembers and learned about her (Settings), forget, undo
      profile.py             /api/profile
      checkin.py             /api/check-in (the daily check-in: due today? start, skip)
  static/
    index.html               one page, one <section data-screen> per screen: today, talk, diary, pills, notes, scam, find (#/find/glasses), family, memories, memory (one page, #/memory/3), settings, welcome
    styles.css               the design system: tokens (light and dark), the orb, every screen, motion, Calm motion, print (see docs/DESIGN.md)
    app.js                   page shell: greeting, theme (Auto/Light/Dark), text size, Calm motion, api() helper, router with View Transitions (#/talk…)
    buddy.js                 Buddy, the living orb: drifting color blobs and its states (idle, listening, thinking, speaking)
    talk.js                  voice mode: listening, /api/chat, latest and earlier exchanges, reading progress, chime, call buttons, safety screens
    welcome.js               the first-time welcome: "Step 1 of 3", name, family, pills now or later; typed or said ("Say it")
    sayit.js                 "Say it" buttons for forms (the welcome, Find my things): record, write down, the safety net first (/api/check-words), then fill the form
    find.js                  Find my things: what she's looking for (quick picks, "Say it"), the photo, the halo (an SVG in the photo's own pixels) and Buddy's sentence
    read.js                  Read it to me: the photo, the orb while Buddy reads it, the card (what it is, Buddy's words, amount and date, scam signs), word for word with Stop, Check it for a scam, call buttons
    about.html               the landing page (/about), for the family member who sets Buddy up: what it does, Meta's models, the promise, plans, questions
    privacy.html, terms.html /privacy and /terms, in plain words
    landing.css              the layout of those three pages (tokens, fonts, buttons, and the orb come from styles.css)
    landing/                 the landing's phone screens: PNGs of the made-up demo week, made by scripts/landing_shots.py
    family.html, family.js, family.css  the family page (/family): join with a code or sign in, then her day as she shares it, with notifications on that device
    herdata.js               Settings, "Her data": the delete sheet that asks for the word DELETE (export is a plain link)
    sw.js                    the service worker (served at /sw.js): the app shell kept on the device, network first, never /api; the "Buddy isn't running" page when the server is down
    offline.html             that page
    manifest.webmanifest, icons/  the installable app's name and icons (Buddy's orb, drawn by scripts/make_icons.py)
    sharing.js               Settings, "Family accounts": the invite code, who can sign in (Remove), the hidden-reminder switch's permission, and the pill notification while Buddy is hidden
    screens.js               the other screens: diary timeline, pills (ring, round checks) and reminder card, family, Memory book, settings, toasts
    recorder.js              microphone -> 16 kHz mono 16-bit WAV
    speech.js                read-aloud: Buddy's natural voice (/api/speak, one sentence at a time, the next made while one plays, the highlight estimated from how far it has played), else the browser's speechSynthesis (her choice in Settings, else the best English voice); any trouble falls back to the browser voice
    fonts/                   Figtree (all text) and Newsreader (greeting and documents), with their licenses
    LICENSE-lucide.txt       license for the Lucide icons inlined in index.html and the scripts
  scripts/
    check_meta.py            one tiny real call to confirm the API key and billing work
    check_advice.py          hand-run: SAFETY.md advice phrases through the real AI (no advice given?)
    check_diary.py           hand-run: two "Something hurts" talks through the real AI (entry saved, no advice?)
    check_pills.py           hand-run: pill questions through the real AI (no doses said, "I took my pills" recorded?)
    check_checkin.py         hand-run: a whole daily check-in through the real AI (mood, diary entry, pill taken, no advice?)
    check_scam.py            hand-run: the SAFETY.md scam messages and one photo through the real AI (right verdicts?)
    check_notes.py           hand-run: the demo week's doctor notes grouped by the real AI (labels in her words?)
    check_memory.py          hand-run: two made-up memories written and painted by the real AI (about 3 cents), then screenshots
    check_realtime.py        hand-run: a spoken clip in Buddy's own voice streamed to Meta's realtime speech-to-text (live words, end of each turn); `--relay` goes through our /api/listen (about $0.0005)
    check_briefing.py        hand-run: 3 real web searches (weather, local news, sports) for the demo town, Meta's answers and what Buddy would say after its checks (about 1 cent)
    check_find.py            hand-run: Find my things end to end in a browser with the real SAM 3.1 and Muse Spark on 4 test photos (about 2 cents; 4 more the first time, to paint them), then screenshots; `--only desk-glasses` runs one look
    find_photos/             the 4 test photos for check_find.py, painted with Muse Image for this project (rooms and a desk only, no people)
    landing_shots.py         the landing's phone screens, from a fresh seeded demo week (the memory page painted with the real Muse Image when a key is set, about 3 cents; faked otherwise)
    check_read.py            hand-run: Read it to me with the real Muse Spark on 3 made-up papers (a bill, a clinic letter, a prize scam), what Buddy would say after its checks, saved next to each photo for the demo screenshots (about 1 cent); `--only scam` reads one
    read_docs/               the 3 made-up papers as photos (made by check_read.py from small web pages, no AI) and the real answers
    demo_screenshots.py      hand-run, free: every screen with the demo week at 390 and 1440px, on a COPY of the app's database (no AI), plus the welcome's 3 steps
    try_companion.py         hand-run: 8 made-up conversations with the real AI (about 25 cents), incl. a returning chat after real daily learning
    get_voice.py             hand-run once: downloads Buddy's natural voice model (Kokoro, about 354 MB) into models/
    check_contrast.py        measures the contrast of every color pair the screens use
    seed_demo.py             a made-up week for "Rose" that fills every screen (pills, check-ins, knee diary, questions, a scam check, 2 painted Memory book pages, what Buddy learned); refuses to overwrite data unless --reset, which backs up first, then wipes; --no-paint skips the 2 paintings (about 2 cents)
    browser_checks/          Playwright scripts that check screens in a real browser (/webapp-testing)
  tests/
    conftest.py              temporary database + fake Meta client for every test
    test_safety.py           safety-net phrases (see docs/SAFETY.md)
    test_diary.py, test_meds.py, test_reminders.py, test_scam.py, test_tools.py
  test-output/               screenshots from browser checks. Git-ignored.
  models/                    Buddy's natural voice (kokoro-v1.0.onnx, voices-v1.0.bin). Git-ignored.
  data/
    grandma_buddy.db         created when the app runs. Git-ignored.
    memories/                the Memory book's paintings (<id>.webp). Git-ignored.
```

## Settings (.env)

| Setting | Default | What it is |
|---|---|---|
| `MODEL_API_KEY` | none (required) | Meta Model API key for the app |
| `CHAT_MODEL` | `muse-spark-1.3` | conversation and reasoning model (standard, never `-contributor`) |
| `TRANSCRIBE_MODEL` | `muse-voice-transcribe-1.0` | speech-to-text model |
| `IMAGE_MODEL` | `muse-image-1.0` | paints the Memory book pictures (standard mode; Meta lists no `-contributor` version) |
| `SAM_MODEL` | `sam-3.1` | finds her things in a photo (Find my things) |
| `LANGUAGE` | `English` | the app's language, sent to speech-to-text as `languageBias` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,::1` | the names this computer answers to. Any other host name gets 400 (so a website's name pointed at this computer can't get in), and an `/api` request sent by another website or another port gets 403 (`app/security.py`) |
| `DATABASE_PATH` | `data/grandma_buddy.db` | where the SQLite file lives. A relative path counts from the project folder, so the app and `scripts/seed_demo.py` always use the same file, whatever folder they're started from |

## Python packages (expected)

`fastapi`, `uvicorn[standard]`, `python-multipart` (file uploads), `openai` (chat, pointed at Meta), `requests` (speech-to-text upload), `python-dotenv`, `pytest`, `httpx` (needed by FastAPI's test client), `playwright` (browser checks only). They're installed into `.venv` in the project.

Buddy's natural voice adds `kokoro-onnx` 0.6.1 (MIT), `onnxruntime` (MIT), `numpy` (BSD), `phonemizer` and `espeakng-loader` (GPL-3.0; espeak-ng's pronunciation dictionary). `kokoro-onnx` is plain Python but not yet marked for Python 3.14, so it is installed with `--no-deps --ignore-requires-python` (see `requirements.txt`); everything it needs has Python 3.14 builds. The voice model itself (Kokoro-82M, Apache-2.0, by hexgrad, exported to ONNX by thewh1teagle) is downloaded by `scripts/get_voice.py`. Without them the app runs fine with the browser's voice.

## Data model (SQLite)

| Table | Columns |
|---|---|
| `profile` (one row) | id, name, preferred_name, language, family_name, family_email, family_phone, family2_name, family2_phone (an optional second family member), doctor_name, doctor_phone, voice_on, voice_rate, text_size, calm_mode (no movement), chime (tone when listening starts and stops), theme ('auto', 'light', or 'dark'), city (her town, for the weather and local news). Older databases get new columns on startup (`db.add_column`) |
| `briefings` | topic (weather, news, sports), city, text (after the checks), sources (site names, JSON), made_at. One per topic and town, kept 3 hours |
| `web_searches` | day, count: at most 30 web searches a day |
| `medications` | id, name, label_dose (exactly as on the label), times (JSON list like `["08:00","20:00"]`), notes, active, created_at |
| `med_events` | id, medication_id, due_at, status (`due`, `snoozed`, or `taken`: only her answers are stored; `upcoming` and `missed` follow from the clock), snooze_until, acted_at. One row per pill per time (`med_events_once` unique index) |
| `symptoms` (the diary) | id, created_at, description (her own words), body_area, pain_level (0 to 10, optional), since (her words, like "since Tuesday"), source (`check_in`, `diary`, `chat`, `safety_net`), conversation_id (the talk it came from; one entry per "Something hurts" talk) |
| `moods` | id, created_at, mood (`great`, `good`, `okay`, `low`, `very_low`), note, conversation_id (one mood per talk: saving again in the same talk replaces it) |
| `check_ins` | day (`YYYY-MM-DD`, one row per day), started_at, skipped (1 for "Not today"). The check-in is offered until today has a row; starting it after "Not today" turns the row into a start |
| `doctor_questions` | id, created_at, question, resolved (1 once asked), asked_at (when she marked it asked; Doctor notes shows it with a check for the days chosen) |
| `messages` | id, conversation_id, created_at, role, content |
| `scam_checks` | id, created_at, input_kind (`voice`, `text`, `photo`), excerpt, verdict, red_flags (JSON) |
| `safety_events` | id, created_at, kind (`emergency`, `poison_control`, `crisis`), matched (JSON), excerpt |
| `facts` | id, created_at, updated_at, kind (`person`, `pet`, `hobby`, `show`, `event`, `other`), fact (her life in plain words, up to 200 characters), follow_up (a question to ask later), follow_up_on (`YYYY-MM-DD`), asked_at, forgotten. The same fact again updates it; never health or feelings (`tools.private`) |
| `talk_summaries` | day (`YYYY-MM-DD`, one row per earlier day learned from), summary (one or two sentences, "" if a guard dropped it), made_at. The number of rows is how many days Buddy has learned from |
| `style_notes` | id, created_at, note ("Prefers short replies"), forgotten. Up to 8 at a time, replaced by each day's learning; forgotten ones are never learned again |
| `family_accounts` | id, created_at, name, email (unique), password_hash (scrypt), salt. Never the password |
| `family_sessions` | id, account_id, token_hash (the cookie's token is never stored, only its SHA-256), created_at, expires_at (30 days) |
| `family_invites` | code (six letters), created_at, expires_at (24 hours), used_at (one use) |
| `subscriptions` | id, account_id, plan (`family`), demo (1 in demo mode), checkout_session_id (unique: the same checkout twice records once), stripe_subscription_id, stripe_customer_id, current_period_end, cancel_at_period_end, created_at, updated_at. Never a card number |
| `memories` (the Memory book) | id, created_at, updated_at, conversation_id, her_words (her own words, joined), talk (JSON: what she and Buddy said), title, story (JSON list of paragraphs), scene (what the picture shows; also its alt text), picture (file name in `data/memories/`), status (`telling` for a page from her old photo still waiting for its story, `writing`, `painting`, `ready`, `no_picture`), photo (her own photo's file name, `photo-<id>…`), people (1 when SAM saw someone: then the photo is the picture, never painted), photo_scene (what Spark saw, checked). Saving again never paints twice: a memory talk makes one page, and in ordinary talk a new page needs a new memory (10 words or more) since the last one |

| `family_messages` | id, created_at, text, sender (`her`: her own words, after the safety net, once she tapped Send; `family`: a signed-in family member's words), sender_name (theirs), read_at (when she saw a family member's message on her Family screen; empty means new), voice (a voice message's recording, `voice-<id>.wav` in `data/voice-messages/`) |
| `postcards` | id, day (unique: one a day), created_at, updated_at, sentence (her line, word for word), scene, picture (`postcard-<id>.webp` in `data/memories/`), status (`painting`, `ready`, or `none` when nothing nice was found), said_until (her newest line when it was last tried: a later line means another try), shared_at (when she sent it to the family page; empty until then) |

## API routes

| Method and path | Sends | Returns |
|---|---|---|
| `GET /api/ping` | | `{"ok": true}` (server check) |
| `POST /api/transcribe` | WAV file | `{"transcript": "..."}` |
| `POST /api/chat` | `{"conversation_id", "text", "mode"}` where `mode` is `"chat"`, `"check_in"`, `"diary"`, or `"memory"` | `{"reply", "show", "actions", "diary_saved", "diary_done", "memory_saved", "memory_done"}` where `show` is `null`, `"emergency"`, `"poison_control"`, or `"crisis"`; `diary_saved` is true when a diary entry was saved this turn, and `diary_done` when a "Something hurts" talk is over; `memory_saved` is the id of a Memory book page saved this turn (then written and painted in the background), and `memory_done` when a memory talk is over |
| `GET /api/diary?days=7` | `days` from 1 to 90 (the Diary screen asks for 30) | diary entries, newest first |
| `GET/POST/PUT/DELETE /api/meds` | `{"name", "label_dose", "times": ["08:00", …]}` (1 to 6 times) | medication list; DELETE only hides it |
| `POST /api/meds/{id}/restore` | | brings a removed pill back (Undo) |
| `GET /api/reminders` | | `{"reminders", "due_title", "due_words", "has_pills", "after_poison_control", "poison_control_words"}`: today's reminders with their status, the card's words ("Rose, it's time for your evening Metformin.") and what Buddy reads aloud (those, then each label exactly), and whether a Poison Control screen came up today |
| `GET /api/reminders/demo` | | `{"title", "words", "reminders"}`: for the hidden `?demo=reminder`, her next pills (or the day's last ones) as if due now. Read only: nothing is saved. 404 with no pills |
| `POST /api/reminders/taken` and `/snooze` | `{"ids": [...]}` | the same as `GET /api/reminders`, updated |
| `POST /api/meds/read-label` (P2) | photo | suggested fields for a family member to confirm |
| `POST /api/scam-check` | `{"text", "kind"}` or `{"image": "data:image/jpeg;base64,…", "kind": "photo"}`; `kind` is `text` (pasted), `voice` (read out loud, written down by `/api/transcribe` first), or `photo` | scam result (below) |
| `GET /api/doctor-notes?days=7` | `days` is 7, 14, or 30 | doctor notes (below) |
| `GET /api/doctor-questions` | | `{"to_ask"}`: how many questions are still to ask, for Home's doctor-notes row |
| `POST /api/doctor-questions` | `{"question"}` | saved question |
| `POST /api/doctor-questions/{id}/asked` and `/reopen` | | she asked it (it stays on the page with a check for the days shown; never deleted), or Undo |
| `GET /api/family/summary?date=YYYY-MM-DD` | the day (today when left out; up to 30 days back) | `{"date", "subject", "text", "mailto", "to"}`: the update in plain words, and a `mailto:` link with it written (line breaks as `%0D%0A`) |
| `GET /api/memories` | | `{"pages": [{"id", "date", "title", "paragraphs", "scene", "status", "picture", "mailto"}]}`, newest first. `status` is `writing`, `painting`, `ready`, or `no_picture` (also when stuck over 15 minutes); `picture` is a URL once painted; `mailto` is "Send to {family}" with the story written in |
| `GET /api/memories/{id}/picture` | | the painting (WebP), only a file name saved by our own code; 404 before it is painted |
| `POST /api/memories` | `{"conversation_id", "mode"}` (`chat` or `memory`, the talk the button was shown in) | "Save it in my memory book": the page made from what was said in that talk (400 if she said nothing), written and painted in the background. Already saved: the same page, not painted again |
| `POST /api/memories/{id}/paint` | | "Paint it again", only for a page with `no_picture` (writes it first if it has no title) |
| `POST /api/memories/photo` | `{"image"}`: her old photo as a data URL | "Start from an old photo": SAM's person check and Spark's description, then a page waiting for her story (`status` `telling`). `{"id", "conversation_id", "opening"}`: the memory talk's id and Buddy's first words. 400 when it isn't a photo. The photo is kept in `data/memories/photo-<id>…` |
| `GET /api/memories/{id}/photo` | | her own photo for that page (only a file name saved by our own code); 404 when the page has none |
| `POST /api/find` | `{"thing", "image", "width", "height"}`: what she said or typed, and the photo as a data URL (JPEG, PNG, or WebP, at most about 6 MB; the page shrinks it to about 1600px JPEG) and its size | the safety net first: a safety-screen answer like `/api/chat`'s if her words need one (no AI). Else `{"found": true, "thing", "sentence", "box": {"x1", "y1", "x2", "y2"}, "width", "height"}` (the box in the photo's own pixels, x2 and y2 included) or `{"found": false, "thing", "sentence"}`. 400 when she named nothing or the photo isn't one; 503 with a kind sentence when SAM can't look. The photo is never saved |
| `POST /api/read` | `{"image"}`: a photo of a paper as a data URL (JPEG, PNG, or WebP, at most about 6 MB) | `{"kind", "title", "summary", "note", "facts": [{"label", "value"}], "words", "spoken", "scam"}`: `kind` is bill, letter, medical, pill_label, advertisement, form, other, or unreadable; `summary` is Spark's checked summary, `note` Buddy's fixed words instead (a health paper, a pill label, a photo it can't read); `words` the paper's words line by line (long numbers hidden; a likely scam's numbers and links taken out); `spoken` what Buddy says; `scam` `{"verdict": "likely_scam", "flags"}` or null. 400 when it isn't a photo; 503 with a kind sentence when Spark can't read it. Nothing is saved |
| `POST /api/check-words` | `{"text"}` | words she said outside a talk (the welcome's "Say it"): the safety net only, never the AI. `{"show": null}`, or the same safety-screen answer as `/api/chat` (saved the same way) |
| `POST /api/greeting` | `{"conversation_id"}` | `{"greeting"}`: at the start of a conversation (no talk in the last 2 hours), "Good afternoon, Rose!" plus a follow-up that's due (asked once) or a warm opener; plain words, no AI; saved in the conversation. Otherwise `""` |
| `GET /api/learned` | | `{"facts": [{"id", "kind", "fact", "follow_up"}], "notes": [{"id", "note"}], "days_learned"}` for Settings |
| `POST /api/learned/{facts or notes}/{id}/forget` and `/restore` | | "Forget this" and Undo |
| `WS /api/listen` | 16 kHz 16-bit mono sound, 80 ms at a time (binary) | `{"type": "ready"}` once Meta listens, then `hearing` (she started), `live` (`text`: her words so far), `turn` (`text`: her finished turn), or `unavailable` (tap to talk instead). Refused (1008) from another website, and (1013) while another is open |
| `GET /api/briefing/{topic}` | | `{"text", "sites"}`: today's weather (or news, sports) for her town, kept 3 hours. Empty (`"text": ""`) when there is nothing to show: no town yet, nothing found, or the search failed with nothing kept from today (normal for Home, so no error status). 404 only for an unknown topic |
| `GET /api/how` | | `{"models": [{"id", "name", "does"}], "features": [{"name", "what", "models": [ids], "here"}]}`: for Help, the Meta models from the settings and every feature with the models behind it (none: it runs on this computer) |
| `GET /about`, `/privacy`, `/terms`, `/family` | | the landing, Privacy, Terms, and the family page (plain files in `static/`, served like Home, always checked for a newer version) |
| `POST /api/family/invite` | | `{"code", "expires_at"}`: a six-letter invite code from her Settings, good for 24 hours, used once |
| `GET /api/family/accounts`, `DELETE /api/family/accounts/{id}` | | the family accounts for her Settings (`[{"id", "name", "email", "created_at"}]`); removing one ends its sessions |
| `POST /api/family/account` | `{"code", "name", "email", "password"}` | joins and signs in (the `buddy_family` cookie: HttpOnly, SameSite=Lax, 30 days). 400 names the entry to fix (`{"field", "message"}`); a wrong code too |
| `POST /api/family/sign-in`, `/sign-out`; `GET /api/family/me` | `{"email", "password"}` | `{"name", "email"}`; 401 when they don't match; 429 after five wrong tries in 15 minutes. `me` signed out: `{"signed_in": false, "demo", "demo_account"}` (whether "Try the demo as Maria" can be offered) |
| `GET /api/billing` | | the signed-in family member's plan: `{"mode": "test" or "demo", "plan": "free"}` or `{…, "plan": "family", "demo", "renews_on", "cancel_at_period_end", "ends_on"}` |
| `POST /api/billing/checkout` | | `{"url"}` of Stripe's test-mode Checkout page ($9 a month, subscription, this family member's id as the reference), or `{"demo": true}` with no key; 503 with a kind sentence when Stripe can't be reached |
| `POST /api/billing/demo`, `POST /api/billing/cancel` | | demo mode only: the plan with one tap (400 with a real key); cancel at the end of the period (Stripe is told in test mode) |
| `GET /billing/return?session_id=` | Stripe's redirect | asks Stripe about the session; records the plan only if it is test-mode, complete, paid, this family member's, a subscription, and $9; then 303 to `/family#billing` (or `#billing-problem`, nothing recorded; `/family` when not signed in) |
| `GET /api/data/export` | | one zip (`grandma-buddy-<date>.zip`): `grandma-buddy.db` (a whole copy), `memories/…` (paintings and her photos), `README.txt`. Never `.env`, never backups |
| `POST /api/data/delete` | `{"confirm": "DELETE"}` | everything gone, as on the first day (400 unless the word is exactly DELETE) |
| `POST /api/messages` | `{"text"}` (her message, up to 1000 characters) | the safety net first: a match answers with the safety screen (`{"show", "reply", "actions"}`) and nothing is sent; else `{"show": null, "message": {"id", "time", "text"}}`, kept for the family page. 400 when empty |
| `GET /api/messages` | | `{"messages": [{"id", "time", "text", "from": "her" or "family", "name", "unread"}], "unread", "latest_unread": {"name", "text"} or null}`: today's messages both ways plus any of the family's she hasn't seen from the last 7 days, oldest first; how many are new; the newest new one, for Home |
| `POST /api/messages/{id}/read` | | she has seen (and heard) a family member's message; 404 for any other id |
| `POST /api/family/reply` | `{"text"}` (up to 1000 characters) | a signed-in family member writes to her: `{"message": {…, "from": "family", "name", "unread": true, "voice": ""}}`; 401 without a session, 400 when empty |
| `POST /api/messages/voice` | multipart `text` and `audio` (a WAV, up to 5 MB) | her message with her own voice (the words she read over, the recording Say it kept): the safety net first, like `/api/messages`, and a match keeps nothing; else `{"show": null, "message": {…, "voice"}}` |
| `POST /api/family/voice` | multipart `audio` (a WAV, up to 5 MB) | a signed-in family member's voice message: kept as `voice-<id>.wav`, written down by Voice Transcribe (`text`, or "" when it can't), `{"message": {…, "voice": "/api/messages/<id>/voice"}}`; 400 when it isn't a WAV |
| `GET /api/messages/{id}/voice` | | that recording (`audio/wav`), only a file name saved by our own code; 404 otherwise |
| `GET /api/postcard/today` | | `{"postcard", "status", "why"}`: today's postcard (`{"id", "day", "date", "sentence", "scene", "status", "picture", "shared", "shared_time"}`), made now when there isn't one yet (so it can take a little while); or `null` with `status` `none` (nothing nice to paint yet), `failed` (painting didn't work: nothing kept, try again), or `painting` (another request is painting it), and `why` in her words |
| `POST /api/postcard/today/send` | | "Send postcard to Maria": the family page shows it from now on; 400 when today has no finished postcard |
| `GET /api/postcard/{id}/picture` | | the painting (WebP), only a file name saved by our own code |
| `GET /sw.js` | | the service worker, from the root so it may look after every page; always checked for a newer version |
| `GET /favicon.ico` | | the tab icon browsers ask for by name: Buddy's orb (an ICO holding the 192px PNG; every page also links it and the Apple icon) |
| `GET /api/demo` | | `{"demo": no Stripe key, "seeded": the demo week is loaded (her name is "Rose Demo")}` |
| `POST /api/demo/reset` | | demo mode only (404 otherwise): a backup, then Rose's week again ending today; `{"ok", "backup", "painting"}` (the Memory book pictures are painted in the background when an API key is set) |
| `POST /api/family/demo-sign-in` | | demo mode only, with the demo week loaded (404 otherwise): signs into the made-up family account, for a judge |
| `GET /api/family/dashboard?date=` | a day in the last 30 days (today by default) | her day as she shares it: `{"her_name", "day", "day_words", "shares": {mood, pills, diary, safety}, "mood", "pills": {"taken", "total", "not_taken"}, "diary", "safety" (kind and time as a fixed sentence, never her words), "memories", "talked", "alerts", "messages" (what she sent that day, `[{"time", "text"}]`), "postcard" (the one she sent that day, `{"sentence", "scene", "picture", "time"}`, else null)}`; a part she doesn't share is null. 401 without a session |
| `GET /api/voice` | | `{"available", "default", "voices": [{"id", "name"}]}`: is Buddy's natural voice set up on this computer, and which voices she can choose (Heart, Bella, Nicole, Emma (British), Michael) |
| `POST /api/speak` | `{"text", "voice", "speed"}` (a sentence, up to 600 characters; speed 0.6 to 1.4) | the words as a WAV (24 kHz mono). 503 when the natural voice isn't set up or fails: the page then uses the browser voice. The words are in the body, never the address, so they never show in the server log. The same words are made once (a cache of 64), and the model loads in the background when the app starts |
| `GET/PUT /api/profile` | profile fields | profile |
| `GET /api/check-in` | | `{"due", "done", "skipped", "mood"}`: whether today's check-in is still to do, done (she said how she feels after it started: Home shows a check), or skipped, and today's latest mood (`{"mood", "at"}` or `null`) |
| `POST /api/check-in/start` | `{"conversation_id"}` | `{"opening"}`: Buddy's fixed first question ("Good morning, Rose. How are you feeling today?"), also saved in that talk so the AI knows it was asked |
| `POST /api/check-in/skip` | | "Not today": not offered again until tomorrow |

## Main flows

**Talking (`/api/chat`)**

1. Save the message.
2. `safety.check(text)` runs the plain rules, first on this message (before the database), then on her last few messages together (up to 3 from the last 10 minutes, in any talk). In a "Something hurts" talk, or right after Buddy asked about pain, her words count as "it hurts" (`safety.as_hurting`). On an emergency, medication mix-up, or crisis match, save a safety event (and a diary entry for emergencies), and return `show` with the fixed message from `docs/SAFETY.md`. No AI call. With crisis words, her words are replaced in the saved conversation too.
3. Otherwise call Muse Spark with the companion prompt, the mode, today's context (pills due, recent mood, family and doctor names), the recent messages, and the tools. `reasoning_effort: "low"` for speed, with room for 3000 output tokens (hidden thinking counts too; at 1200 it sometimes ran out before writing anything). Run tool calls, up to 3 rounds; an empty reply is asked again the same way. Meta only supports `tool_choice: "auto"`, so when words are needed after 3 rounds, a short developer message asks for them. Return the reply.
4. After a crisis match, later AI turns get a note to stay gentle and keep encouraging real help.

**Symptom diary (`mode: "diary"`)**

1. The "Something hurts" button (on Today and on the Diary screen) starts a diary talk on Today. The page says and speaks the fixed opening "I'm sorry something hurts. Tell me what you're feeling." The talk gets its own conversation id (`<day>-diary-<time>`), so its entry holds exactly what she said in it.
2. Safety rules run first on every message, as above. In this talk her answers count as "it hurts", so "my chest" alone shows the emergency screen.
3. The companion asks up to 3 short follow-ups, one at a time (where, how bad from 0 to 10, since when), skipping any she already answered, then calls `log_symptom` once.
4. `log_symptom` saves all her messages in the talk, in her own words. The AI may fill in where, pain, and since, but each is kept only if she said those words (so "possible sprain" or a made-up pain number never reaches her diary). Saving again in the same talk updates the same entry.
5. The reply says "I've written that down for your doctor" with Call {doctor} and Call {family}; Python adds those buttons whenever an entry is saved, even if the AI forgot. It never comments on what the symptom means.
6. The server says when the talk is done (`diary_done`): once the entry is saved and Buddy's own words aren't asking anything more, or at her 4th answer, when Buddy is told "this is her last answer: save it now if something hurts". The page also ends it after a safety screen, when she leaves Today, or after 10 minutes without an answer.

**Buddy as a friend (memory and learning)**

1. Every reply's instructions (`prompts.companion_prompt`) add what Buddy knows, built by plain code (`companion.memory_for_prompt`):
   - her facts: at most 30; an event only until a week after it;
   - the last 5 days' summaries;
   - how she likes to talk (her style notes, once Buddy has learned from 2 days), or, before that in ordinary talk, a "getting to know her" note;
   - how Buddy's last reply began, so the next one starts differently.
2. Every AI reply is made spoken words only (`companion.spoken`: no markdown, bullets, or emoji), then checked by the advice guard as before.
3. After a chat, if there are earlier days (the last two weeks) not yet learned from, a background task (`companion.learn_from_past_days`) learns each one, oldest first, at most 5 at a time:
   - one structured Muse Spark call per day (low reasoning): a summary and her updated style notes;
   - it never sees the safety net's messages or words that were not kept;
   - plain code keeps a summary only if the guards are quiet, and a note only if it's short and not about health, feelings, or her mind;
   - it commits after each day and never holds the database while the AI thinks; one job at a time.
4. "Talk to Buddy" asks `/api/greeting` first. With a greeting, it's shown and read aloud, and listening starts when it has finished; otherwise listening starts at once.
5. `scripts/try_companion.py` runs 8 made-up conversations against the real AI (about 25 cents) to judge warmth, length, and the safety rules.

**Memory book (`mode: "memory"`, and `offer_memory_page` in ordinary talk)**

1. "Tell Buddy a memory" (on the Memory book screen) starts a memory talk, like "Something hurts": the fixed opening "I'd love to hear one of your memories. What would you like to tell me about?" and its own conversation id (`<day>-memory-<time>`). In ordinary talk, when she starts reminiscing, the AI calls `offer_memory_page`, which shows "Save it in my memory book", and asks whether she'd like it in her book.
2. Safety rules run first on every message, exactly as above.
3. The companion asks one or two gentle follow-ups, one at a time (when it was, who was there), then calls `save_memory`. At her 3rd answer Buddy is told to save now, and if it still didn't, Python saves it anyway, so her story is never lost. The talk is over (`memory_done`) once it is saved and Buddy isn't asking anything, or at her 3rd answer.
4. `save_memory` (or the button, `POST /api/memories`) only stores what was said: tools never use the internet. That is the talk's last half hour, or since its last page, and only after the safety net last answered in any talk, never words that were not kept (`db.memory_talk`). The tools only work in ordinary talk and memory talks, never in "Something hurts" or a check-in. A page is new only once: a memory talk makes one page, and in ordinary talk a short "Yes please, save it" after a page is the same page, while a new memory (10 words or more) is a new one. Only a new page is queued: after the reply is sent, a FastAPI background task (`memories.make_page`) writes and paints it, and does nothing for a page that is painted already. It commits before each AI call (reading her profile can start a write, so that is committed too), so the screen shows the title while the picture is painted and chat, pill reminders, and the Memory book never wait on the database (a test holds the lock check).
5. The Memory book screen asks again every 3 seconds while a page is writing or painting, shows a shimmer meanwhile, and fades the painting in.

**Pill reminders**

- The page asks `/api/reminders` every 30 seconds while open, and after each reply from Buddy.
- Each check creates today's missing `med_events` rows, only for times later today or in the last 2 hours (just after midnight, that includes last night's late pill), and never more rows in a day than the pill has times. So a pill added at noon gets no "missed" 8 AM reminder, and moving a time later can't remind her again for a dose she took. Rows are created for the whole rest of the day at once, so a reminder that comes due while the tablet sleeps can still end up missed.
- A reminder is due when its time has come (or its snooze ended) and it isn't taken. After 2 hours with no answer since it was last shown, it is `missed`. "I took it" still counts after that.
- The card says her name and the pill (`reminders.reminder_title`), repeats each label exactly as typed (`reminders.reminder_words`), is read aloud once per new set of due pills (never while she is talking, over a safety message, or over Buddy's own words; one that came before her first tap is read right after it), and stays until she answers.
- `?demo=reminder` in the address (screens.js `startDemoReminder`) shows `/api/reminders/demo` on the card 2 seconds after the first tap, for the demo video. Its answers thank her the same way but post nothing. Its words are made in the natural voice ahead of time (`warmVoice`), so they are heard the moment the card shows.
- The family update counts every reminder of the day, still to come included, so it says what the Pills screen's ring says (`family.pills_line`).
- Changing or removing a pill drops its waiting reminders; taken and missed ones stay as a record.

**Message Maria (`POST /api/messages`)**

1. On the Family screen (or Home's "Message Maria" chip) she says the message ("Say it", `static/sayit.js`: written down by Voice Transcribe, then `/api/check-words` runs the safety net before her words go into the box; the recording is kept on the page, `lastSaidWav`, so her voice can go with the words) or types it. Buddy reads it back (`speak`).
2. "Send to Maria" (`POST /api/messages`, or `POST /api/messages/voice` with the recording when she said it and didn't choose "Just the words"): `safety.check` runs on the words first. A match answers with the safety screen (recorded like any other input of her words, under the talk id `family-message`), and nothing is sent. Otherwise one `family_messages` row, at the app's clock, and `{"message": {id, time, text}}`; the box empties, "Sent today" shows it, and Buddy says "Sent."
3. In a talk, `offer_family_message` (or plain code, when she clearly asked and the AI forgot: `tools.message_she_asked_for`) shows "Send this to Maria" with her words in her order (`tools.her_own_words`); the button opens `#/family/message/<her words>`, which fills the box and leaves the address.
4. Maria's page reads `family_messages` for the day (`family.day_facts`, `messages`, both ways with `from` and `name`), and notifies on a new one of hers while it is open.
5. Maria writes back ("Write to Rose", `POST /api/family/reply`), or records a voice message (`static/recorder.js` on the family page makes the 16 kHz WAV, `POST /api/family/voice` keeps it in `data/voice-messages/` and asks Voice Transcribe for the words, with her name as a hint): her words as written (or heard), `sender` `family`, new until `read_at`. Rose's Family screen shows it marked New, reads it as "Maria wrote: …" (`speak`, never the AI), then posts `/api/messages/{id}/read`. Home's first row says "A message from Maria" while one waits (`GET /api/messages` `unread`, `latest_unread`), and `/api/greeting` adds "Maria sent you a message. It's on your Family screen." in fixed words.

**Today's postcard (`GET /api/postcard/today`)**

1. The Family screen asks on every open. A `ready` row answers at once; a fresh `painting` claim (under 15 minutes old) answers `painting` and the screen looks again in 5 seconds.
2. Otherwise her lines today in ordinary talk (`db.her_words_on`: never a check-in or a "Something hurts" talk), filtered by `postcards.about_health` (`POSTCARD_SKIP`, the safety net, the advice guard, the health patterns): none left means `none`, "Nothing nice to paint yet today". A `none` row is tried again only once she has said something new (`said_until`).
3. The day is claimed (`painting`, committed) before Meta is called; a second claim hits the UNIQUE day and answers `painting`. Muse Spark picks a line's number and a scene (`prompts.POSTCARD`); `checked_pick` checks both; Muse Image paints `memories.STYLE` + `STYLE_WORDS`; the file goes to `data/memories/postcard-<id>.<kind>`, and the row becomes `ready`. Any failure deletes the claim ("Try again").
4. "Send postcard to Maria" sets `shared_at`; only then `family.day_facts` includes it (`postcard`).

**The scam lookup (inside `POST /api/scam-check`)**

1. `scam.contacts` pulls the phone numbers and web addresses out of the pasted or spoken words (never a photo).
2. With any, and one of the day's 30 searches left (`briefing.take_search`, committed on the request thread), a worker thread runs `scam.searched` while Muse Spark reads the message: `meta_client.search` with no town, the number or address in the question, `prompts.SCAM_LOOKUP` as the instructions.
3. Plain code reads the first word of the answer (REPORTED, CLEAR, UNKNOWN): REPORTED makes the verdict `likely_scam` and puts a fixed red flag first; anything else gives the fixed "Nothing was found online…" line and never lowers the verdict. `named_sites` names the cited sites, never the looked-up address or a host carrying the number.
4. The verdict card shows the line on a tinted panel (its words left out of the warning-signs list) and reads it with the verdict.

**A pill from a bottle photo (`POST /api/meds/label`)**

1. In Set up pills, "Take a photo of the bottle": the page shrinks the photo and posts it. `labels.read_label` asks Muse Spark for `{readable, name, label}` (`prompts.PILL_LABEL`) and trims both to the form's limits; unreadable or empty is a 400 with kind words, Meta down a 503.
2. The words only fill the Name and Label boxes; a "I checked this against the bottle" box appears under each, and Save waits until both are ticked (the cursor goes to the first unticked one). The times are typed. Saving is the usual `POST /api/meds`; nothing is stored by the reading, and the photo is never saved.

## AI design

**Companion prompt (outline, lives in `app/prompts.py`)**: you are a warm, patient companion for {preferred_name}, an older adult who lives alone. Short sentences. One question at a time. Simple words. You never give medical, mental-health, or food advice: no opinions on how serious anything is, no causes, no treatments, no medicines, no diets. When asked for advice, say kindly that you can't give medical advice, and offer to call her doctor or family or to add the question to her doctor notes. You're a friend, not a therapist. Encourage real-world connection with {family_name} and friends. You are an AI helper, and you say so if asked.

**Companion tools (`app/tools.py`)**

| Tool | Parameters | What it does |
|---|---|---|
| `log_mood` | mood, note | saves to `moods` |
| `log_symptom` | description, body_area, pain_level, since | saves a diary entry to `symptoms` |
| `get_pills_due` | none | today's reminders: name, time, and status. Never the label, so the AI can't repeat or change a dose |
| `mark_pill_taken` | medication_name | marks pills taken with `reminders.pick_taken`: at most one reminder per pill; due ones first, else one within the hour; a missed one only when she names it |
| `add_doctor_question` | question | saves to `doctor_questions` |
| `show_call_buttons` | who (`doctor`, `family`, or both) | tells the screen to show big call buttons |
| `suggest_calling_family` | none | tells the screen to show a big "Call {family_name}" button |
| `remember_fact` | kind, fact, follow_up, follow_up_on | remembers something lasting about her life in `facts`. Plain code refuses an unknown kind, long text, a date that isn't today to 60 days ahead, and anything about health, hard feelings, or her mind, or that the safety net or advice guard reacts to |
| `offer_memory_page` | none | tells the screen to show "Save it in my memory book" |
| `save_memory` | none | saves what was said in the talk for a Memory book page (her own words; Buddy's questions too, for context) and shows "Open my memory book". The page is written and painted afterward. Saving again is the same page. Ordinary talk and memory talks only |
| `open_screen` | screen (`today`, `diary`, `pills`, `notes`, `family`, `scam`, `memories`) | tells the screen to show "Open …" |
| `look_up_today` | topic (weather, news, or sports only) | looks it up with Meta's web search near her town (`briefing.look_up`): the checked words for the AI to say, and "From the web: …" under its reply |
| `find_my_things` | thing | when she can't find something: tells the screen to show "Find my glasses", which opens Find my things with the thing filled in. Plain code makes the thing a short noun phrase first |

**Structured outputs (`meta_client.structured()`)**

`response_format` with a strict `json_schema`; the answer is parsed, asked for once more if it isn't valid JSON, and every field is checked in Python. A photo is sent as an `image_url` part with a base64 data URL (the page shrinks it to about 1600px JPEG first).

Scam check (`app/scam.py`). The AI fills in only:

```json
{"verdict": "likely_scam | suspicious | looks_safe", "red_flags": ["plain words"], "explanation": "2 or 3 short sentences"}
```

The route returns `{"verdict", "title", "red_flags", "explanation", "what_to_do", "if_you_paid", "actions", "lookup"}`:
- The plain red-flag rules set a floor: the verdict is the stronger of the rules', the AI's, and the web's. If the rules or the web found more, or the AI's words slip into advice, its explanation is replaced with fixed words.
- `lookup`: while the AI reads the words, a thread asks Meta's web search (`meta_client.search` with no town, `prompts.SCAM_LOOKUP`) whether the phone numbers and web addresses plain code found in the message (`scam.contacts`: at most 2 each, never a bare code or an email's domain) are reported as scams. Plain code reads only the first word of the answer: REPORTED makes the verdict `likely_scam` and puts a fixed red flag first ("The phone number in it has been reported as a scam online."); CLEAR or UNKNOWN gives `{"reported": false, "words": "Nothing was found online about the website in it. That doesn't make it safe.", "sites"}` and never lowers the verdict. `sites` are the cited pages' site names. `null` when there was nothing to look up, for a photo, when today's 30 searches are used up (`briefing.take_search`, shared with the briefing), or when the search failed or didn't really search.
- `what_to_do` and `if_you_paid` are fixed lines from `docs/SAFETY.md` section 8, never AI text.
- Links and phone numbers are taken out of the AI's words.
- If the AI is down, the rules answer alone ("I'm not sure about this one…" when nothing matched).
- Each check saves a `scam_checks` row: a 120-character excerpt with long numbers hidden, or "(photo)".

Doctor notes (`app/notes.py`). Every fact comes from the logs with plain code; the AI fills in only a grouping:

```json
{"topics": [{"label": "Left knee", "entry_ids": [3, 7]}]}
```

The grouping is used only if:
- every id is a real entry;
- each entry appears exactly once;
- every label is 1 to 3 words she said herself (a plural or singular counts).

Otherwise, or when the AI is down, entries are grouped by where she said it hurts. The route returns:

```json
{
  "period": "October 22 to 28", "her_name": "Rose", "doctor_name": "Dr. Lee", "made_on": "Wednesday, October 28",
  "topics": [{"label": "Left knee", "entries": [{"date": "Thu, Oct 22", "time": "9:20 AM", "words": "...", "quoted": true, "where": "left knee", "pain": 4, "since": "", "note": ""}]}],
  "pills": [{"name": "...", "label": "exactly as typed", "taken": 6, "total": 7, "missed": ["Tue, Oct 27, 8:00 AM"]}],
  "moods": [{"day": "Thu, Oct 22", "mood": "Good"}],
  "questions": [{"id": 1, "question": "..."}]
}
```

Memory book page (`app/memories.py`). The AI writes, in her voice, only:

```json
{"title": "Summers at the lake", "paragraphs": ["2 or 3 short paragraphs"], "scene": "one moment to paint, no names or faces"}
```

The page is kept only if:
- it has a title, 2 or 3 paragraphs, and a scene, all short;
- the advice guard (`guard.check_reply`) finds nothing in it;
- every name (a capitalized word that doesn't start a sentence) and every number in the title and paragraphs came up in the talk (`memories.invented`). A plural or a possessive counts.

Otherwise it is written once more with a note saying what to fix (like "These were not in what she said: Paris"). If that fails too, or the AI is down, the page is her own words under the title "A memory".

**Painting (`meta_client.paint()`, Muse Image)**

`POST /v1/images/generations` through the `openai` package's `images.generate` (Meta's endpoint follows the OpenAI Images format): `model` (`muse-image-1.0`), `prompt`, `n: 1`, `size: "1536x1024"`, and `extra_body: {"tool_enablement": {...all false}}`. That last part turns off Muse Image's own web and image search, so her story stays in the request and it never matches a real person's likeness. The answer is base64 (WebP by default). Our code saves it only if its first bytes are a real WebP, PNG, or JPEG. The prompt is always the fixed `memories.STYLE` (a soft watercolor storybook in Buddy's colors, no text, people only as small figures from behind or far away) followed by the writer's scene. That's what makes every page in the book look like the same book. It costs $0.01 per picture, so each page is painted once; "Paint it again" only appears when painting failed. Waits and retries on 429 and 503; a 180-second timeout.

**Finding her things (`meta_client.segment()`, SAM 3.1)**

`POST /v1/responses` through the `openai` package's `responses.create`: `model` (`sam-3.1`); `input` is one user message with an `input_text` part (one short noun phrase, like "glasses") and an `input_image` part (the data URL); `metadata: {"include_confidence": "true", "mask_encoding": "one_bit"}` (Meta's settings are strings); and `store: false`, so Meta doesn't keep her photo (big inline photos can also fail with HTTP 413 when stored). The answer (`output_text`) is one line, empty when nothing matched:

```
<0f>0<|box;x1=100;y1=200;x2=199;y2=259;w=1000;h=800;c=0.91|><|mask;x=0;y=0;data=60,100,!…|>,3<|box;…|><|mask;…|>
```

Each match is an id, a box, and a mask. `x1,y1` is the top-left corner and `x2,y2` the bottom-right (both included), in the photo's own pixels; `w,h` is the photo's size; `c` is how sure SAM is (0 to 1). `finder.parse_matches` reads the boxes and skips anything it can't read; `finder.best_match` keeps the surest, if `c` is at least 0.5. The mask (the exact outline) uses an encoding Meta doesn't document (only its own client library decodes it, with no published license), so the page draws a soft halo around the box instead. Costs $0.0025 per photo. Waits and retries on 429, like chat. A few things are asked of SAM by the name it knows (`finder.SAM_WORDS`): "pill bottle" found nothing in the real check, "medicine bottle" found it; Buddy still says "pill bottle" to her.

Then Muse Spark (`structured()`, reasoning "low") gets the photo, the thing, and where the box is as parts of the photo ("from 10% to 20% across…"), and writes `{"sentence"}` with the `FIND` prompt: one short sentence, where it is next to what, never reading labels, never about medicines, health, or food, never describing people. The sentence is used only if it's 30 words or fewer and the advice guard finds nothing; otherwise, or when Spark is down, plain code says where in the photo it is ("Your keys are near the bottom left of your photo.").

Message Maria and the postcard (`app/routes/messages.py`, `app/postcards.py`). A message is never AI: her words, the safety net, a row for the family page. The companion's `offer_family_message` tool only shows a button, with the AI's message if every meaningful word of it is one she said in her last three messages, else her whole last message (`tools.her_own_words`). The postcard: plain code gathers her lines that day (3 words or more, up to 200 characters, the newest 30) and drops every line about health, pain, medicines, or hard feelings, or that the safety net or the advice guard would react to; Muse Spark gets the rest numbered (`prompts.POSTCARD`, structured output `{"number", "scene"}`, low reasoning); plain code checks the number is real, the line once more, and the scene (no name or number, `memories.invented`; no health word; no advice); Muse Image paints `memories.STYLE` plus `postcards.STYLE_WORDS` and the scene. One painting a day: the day's row is claimed (`painting`) before Meta is called and the database is committed, so a second request meanwhile sees `painting` and the screen looks again in 5 seconds; a failure deletes the row (try again); "nothing nice" keeps a `none` row with `said_until`, so the picker runs again only once she has said something new. The family sees the postcard only once `shared_at` is set.

## Errors and offline behavior

- Every screen shows a friendly message, never raw errors: "I didn't catch that. Tap the button and try again."
- If Meta's API is slow or down, the app says so kindly, and the safety net and pill reminders still work.
- Timeouts: 60 seconds for chat and for speech-to-text. On HTTP 429, wait and retry with backoff, up to 3 times.

## Privacy and security

- Health data stays in the SQLite file on this computer. `data/` is git-ignored.
- All app calls use standard models, so Meta does not train on Grandma's conversations.
- The server only listens on this computer (`127.0.0.1`, Uvicorn's default). There is no login, so don't put it on the internet without adding protection, and only with demo data.
