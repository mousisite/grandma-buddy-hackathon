# Grandma Buddy: architecture

## The big picture

```
 Grandma's browser (Chrome or Edge)                Our backend (Python, FastAPI)            Meta Model API
 ----------------------------------                -----------------------------            --------------
 Tap to talk -> recorder.js makes a WAV  --POST-->  /api/transcribe  ---------------------->  Muse Voice Transcribe
 Big text + speechSynthesis reads aloud  <--JSON--  /api/chat
                                                      1. safety.py checks for warning signs
                                                         (plain rules, no AI, works offline)
                                                      2. companion prompt + tools  -------->  Muse Spark 1.3
                                                      3. tools read/write SQLite             (function calling,
                                                                                              structured outputs,
 Pill banner (checks every 30 seconds)   <--JSON--  /api/reminders/due                        image input)
 Diary, pills, scam, notes, family       <--JSON--  feature routes
                                                    SQLite file: data/grandma_buddy.db
```

Key ideas:

- The browser never talks to Meta directly. The API key stays on the backend.
- The safety net is plain Python that runs before any AI. Emergencies are caught even if the AI or the internet is down, and its messages are fixed text, never AI-generated.
- One AI "companion" handles conversation and uses tools to do things: write a diary entry, mark a pill taken, add a doctor question, show a call button. That is what makes it an agent, not just a chatbot.
- The AI never gives medical advice (`docs/SAFETY.md`). It records, reminds, and connects her to people.
- Reports (scam verdict, doctor notes) use structured outputs (JSON schemas), so the screen can show clean cards instead of walls of text.

## Folder map

The plan and agent setup come first. All app code (`app/`, `static/`, `scripts/`, `tests/`) is written during the hackathon.

```
grandma-buddy-hackathon/
  AGENTS.md                  instructions the coding agent reads every session
  README.md                  project description for GitHub and judges (finish on Day 9)
  LICENSE                    MIT license (the repo must be public and open source)
  THIRD_PARTY_NOTICES.md     credits for the helper skills from other projects
  .env                       YOU copy it in. Holds the API key. Never shared.
  .env.example               shows which settings go in .env
  .gitignore                 keeps .env, .venv, the database, and recordings off GitHub
  requirements.txt           Python packages
  docs/                      SPEC, ARCHITECTURE, SAFETY, DESIGN, PLAN
  .agents/skills/            project skills for Muse Code
  app/
    __init__.py
    main.py                  creates the FastAPI app, serves static/, includes the routes
    config.py                reads settings from .env (only place that does)
    db.py                    SQLite connection, creates tables, small query helpers
    meta_client.py           ALL calls to Meta: chat(), chat_json(), transcribe()
    safety.py                emergency, crisis, and medication mix-up rules with fixed messages
    prompts.py               system prompts for companion, diary, scam, notes, family
    schemas.py               JSON schemas for structured outputs
    tools.py                 companion tool definitions and what each one does
    routes/
      companion.py           /api/chat, /api/transcribe
      diary.py               /api/diary
      meds.py                /api/meds, /api/reminders
      scam.py                /api/scam-check
      notes.py               /api/doctor-notes, /api/doctor-questions
      family.py              /api/family/summary
      profile.py             /api/profile
  static/
    index.html               one page with sections: home, talk, diary, pills, scam, notes, family, settings
    styles.css               senior-friendly styles (see docs/DESIGN.md)
    app.js                   navigation, API calls, reminder checks every 30 seconds
    recorder.js              microphone -> 16 kHz mono 16-bit WAV
    speech.js                read-aloud wrapper around speechSynthesis (speed, voice, replay)
  scripts/
    check_meta.py            one tiny real call to confirm the API key and billing work
    seed_demo.py             fills the database with made-up demo data ("Rose", 7 days)
    browser_checks/          Playwright scripts that check screens in a real browser (/webapp-testing)
  tests/
    conftest.py              temporary database + fake Meta client for every test
    test_safety.py           safety-net phrases (see docs/SAFETY.md)
    test_diary.py, test_meds.py, test_scam.py, test_tools.py
  test-output/               screenshots from browser checks. Git-ignored.
  data/
    grandma_buddy.db         created when the app runs. Git-ignored.
```

## Settings (.env)

| Setting | Default | What it is |
|---|---|---|
| `MODEL_API_KEY` | none (required) | Meta Model API key for the app |
| `CHAT_MODEL` | `muse-spark-1.3` | conversation and reasoning model (standard, never `-contributor`) |
| `TRANSCRIBE_MODEL` | `muse-voice-transcribe-1.0` | speech-to-text model |
| `LANGUAGE` | `English` | the app's language, sent to speech-to-text as `languageBias` |
| `DATABASE_PATH` | `data/grandma_buddy.db` | where the SQLite file lives |

## Python packages (expected)

`fastapi`, `uvicorn[standard]`, `python-multipart` (file uploads), `openai` (chat, pointed at Meta), `requests` (speech-to-text upload), `python-dotenv`, `pytest`, `httpx` (needed by FastAPI's test client), `playwright` (browser checks only). They're installed into `.venv` in the project.

## Data model (SQLite)

| Table | Columns |
|---|---|
| `profile` (one row) | id, name, preferred_name, language, family_name, family_email, family_phone, doctor_name, doctor_phone, voice_on, voice_rate, text_size |
| `medications` | id, name, label_dose (exactly as on the label), times (JSON list like `["08:00","20:00"]`), notes, active, created_at |
| `med_events` | id, medication_id, due_at, status (`due`, `snoozed`, `taken`, `missed`), snooze_until, acted_at |
| `symptoms` (the diary) | id, created_at, description (her own words), body_area, pain_level (0 to 10, optional), since (her words, like "since Tuesday"), source (`check_in`, `diary`, `chat`, `safety_net`) |
| `moods` | id, created_at, mood (`great`, `good`, `okay`, `low`, `very_low`), note |
| `doctor_questions` | id, created_at, question, resolved |
| `messages` | id, conversation_id, created_at, role, content |
| `scam_checks` | id, created_at, input_kind (`voice`, `text`, `photo`), excerpt, verdict, red_flags (JSON) |
| `safety_events` | id, created_at, kind (`emergency`, `poison_control`, `crisis`), matched (JSON), excerpt |

## API routes

| Method and path | Sends | Returns |
|---|---|---|
| `GET /api/ping` | | `{"ok": true}` (server check) |
| `POST /api/transcribe` | WAV file | `{"transcript": "..."}` |
| `POST /api/chat` | `{"conversation_id", "text", "mode"}` where `mode` is `"chat"`, `"check_in"`, or `"diary"` | `{"reply", "show", "actions"}` where `show` is `null`, `"emergency"`, `"poison_control"`, `"crisis"`, `"call_buttons"`, or `"call_family"` |
| `GET /api/diary?days=7` | | diary entries, newest first |
| `GET/POST/PUT/DELETE /api/meds` | medication fields | medication list |
| `GET /api/reminders/due` | | reminders due right now |
| `POST /api/reminders/{id}/taken` and `/snooze` | | updated reminder |
| `POST /api/meds/read-label` (P2) | photo | suggested fields for a family member to confirm |
| `POST /api/scam-check` | `{"text"}` or a photo | scam result (below) |
| `POST /api/doctor-notes` | `{"days": 7}` | doctor notes (below) |
| `POST /api/doctor-questions` | `{"question"}` | saved question |
| `GET /api/family/summary?date=YYYY-MM-DD` | | `{"text", "mailto"}` |
| `GET/PUT /api/profile` | profile fields | profile |

## Main flows

**Talking (`/api/chat`)**

1. Save the message.
2. `safety.check(text)` runs the plain rules. On an emergency, medication mix-up, or crisis match, save a safety event (and a diary entry for emergencies), and return `show` with the fixed message from `docs/SAFETY.md`. No AI call.
3. Otherwise call Muse Spark with the companion prompt, the mode, today's context (pills due, recent mood, family and doctor names), the recent messages, and the tools. `reasoning_effort: "low"` for speed. Run tool calls, up to 3 rounds. Return the reply.
4. After a crisis match, later AI turns get a note to stay gentle and keep encouraging real help.

**Symptom diary (`mode: "diary"`)**

1. The "Something hurts" button opens the talk screen in diary mode, and the companion asks "Tell me what you're feeling."
2. Safety rules run first on every message, as above.
3. The companion asks up to 3 short follow-ups, one at a time (where, how bad from 0 to 10, since when), then calls `log_symptom` with her own words.
4. It confirms the entry and calls `show_call_buttons`, offering to tell family or call the doctor. It never comments on what the symptom means.

**Pill reminders**

- The page asks `/api/reminders/due` every 30 seconds while open.
- On the first check each day, the backend creates that day's `med_events`.
- A reminder is due when its time has come (or its snooze ended) and it isn't taken. After 2 hours with no answer it becomes `missed`.

## AI design

**Companion prompt (outline, lives in `app/prompts.py`)**: you are a warm, patient companion for {preferred_name}, an older adult who lives alone. Short sentences. One question at a time. Simple words. You never give medical, mental-health, or food advice: no opinions on how serious anything is, no causes, no treatments, no medicines, no diets. When asked for advice, say kindly that you can't give medical advice, and offer to call her doctor or family or to add the question to her doctor notes. You're a friend, not a therapist. Encourage real-world connection with {family_name} and friends. You are an AI helper, and you say so if asked.

**Companion tools (`app/tools.py`)**

| Tool | Parameters | What it does |
|---|---|---|
| `log_mood` | mood, note | saves to `moods` |
| `log_symptom` | description, body_area, pain_level, since | saves a diary entry to `symptoms` |
| `get_pills_due` | none | lists today's reminders and their status |
| `mark_pill_taken` | medication_name | marks today's matching due reminder as taken |
| `add_doctor_question` | question | saves to `doctor_questions` |
| `show_call_buttons` | who (`doctor`, `family`, or both) | tells the screen to show big call buttons |
| `suggest_calling_family` | none | tells the screen to show a big "Call {family_name}" button |

**Structured outputs (`app/schemas.py`)**

Scam result:

```json
{
  "verdict": "likely_scam | suspicious | looks_safe",
  "red_flags": ["plain-word reasons"],
  "what_to_do": ["clear steps"],
  "explanation": "2 or 3 short sentences"
}
```

Doctor notes (only facts from the logs, no interpretation):

```json
{
  "period": "Oct 27 to Nov 2",
  "symptom_log": [{"date": "...", "her_words": "...", "body_area": "...", "pain_level": 6, "since": "..."}],
  "medications": [{"name": "...", "taken": 12, "missed": 2}],
  "mood_by_day": [{"date": "...", "mood": "okay"}],
  "questions_to_ask": ["..."]
}
```

## Errors and offline behavior

- Every screen shows a friendly message, never raw errors: "I didn't catch that. Tap the button and try again."
- If Meta's API is slow or down, the app says so kindly, and the safety net and pill reminders still work.
- Timeouts: 60 seconds for chat and for speech-to-text. On HTTP 429, wait and retry with backoff, up to 3 times.

## Privacy and security

- Health data stays in the SQLite file on this computer. `data/` is git-ignored.
- All app calls use standard models, so Meta does not train on Grandma's conversations.
- The server only listens on this computer (`127.0.0.1`, Uvicorn's default). There is no login, so don't put it on the internet without adding protection, and only with demo data.
