# A public demo of Grandma Buddy

For judges who want a live link. The app runs as a **public demo** (`PUBLIC_DEMO=1`): Rose's made-up week, put back every night, each visitor gets a share of Buddy's thinking, the day has a cap so the Meta key's credits can't be drained, no one can sign up or wipe anything, and the key lives only as a secret on the host. Nothing real is ever in it.

## Which host

**Render** (render.com) is the simplest for this app: one web service built from the `Dockerfile` in this repository, HTTPS included (the microphone needs it), WebSockets allowed (hands-free talking needs them), secrets kept out of the code, and deploys straight from GitHub.

| | What you get | Cost |
| --- | --- | --- |
| Render **Pro** (recommended for judging) | always on, 2 CPU, 4 GB: room for Buddy's natural voice (the Kokoro model) | $85 a month, billed by the hour (about $2.80 a day), cancel any time |
| Render **Starter** ($7) or **Free** ($0) | always on (Free sleeps after 15 minutes and takes a minute to wake), 512 MB: too small for the voice model, so Buddy speaks with the browser's voice there | $7 a month, or $0 |

Fly.io and Railway work too (the same `Dockerfile`), but need a command-line tool or a card up front. With the natural voice loaded Buddy uses about 700 MB of memory (550 MB is the model) and one or two CPUs while it speaks; without the voice, about 150 MB.

## Before you start (5 minutes)

1. Push the repository to GitHub (it must be public for the hackathon anyway).
2. Have your Meta Model API key ready to paste. Never put it in the code or in `render.yaml`: it goes into Render's secret store in step 6 below.

## Click by click (Render, about 10 minutes)

1. Go to https://render.com and sign up with your GitHub account (free). Allow Render to see the `grandma-buddy-hackathon` repository when it asks.
2. In the Render dashboard, click **New +** (top right), then **Blueprint**.
3. Pick the repository. Render finds `render.yaml` and shows one service, **grandma-buddy**. Click **Apply**.
4. Render asks for the values marked as secrets: paste your key into **MODEL_API_KEY**. Click **Apply** again. The first build takes about 4 to 6 minutes (the packages, then the 354 MB voice model, downloaded once and kept in the image).
5. When the service shows **Live**, click its name. Its address is at the top, like `https://grandma-buddy-ab12.onrender.com`. Copy it.
6. Open the service's **Environment** tab. Set **ALLOWED_HOSTS** to that address without `https://` (for example `grandma-buddy-ab12.onrender.com`). The app only answers to its own address (`app/security.py`), so until this matches, every page says "Grandma Buddy only answers on this computer." Click **Save, rebuild, and deploy**.
7. Open the address in Chrome or Edge. Home shows "Good morning, Rose" and the made-up week. Allow the microphone when asked and tap **Talk to Buddy**.
8. Open `/family` on that address and tap **Try the demo as Maria**.
9. Optional: to stop paying, open the service's **Settings** and click **Delete Web Service**, or switch its plan to Free.

The plan is set in `render.yaml` (`plan: pro`, 2 CPU and 4 GB). It was chosen by measuring the voice: the model takes about 550 MB, and on one thread a short sentence takes 1.4 seconds and a long one 3.5, so Standard (1 CPU) would leave her waiting; on two threads it is half that. If sentences still come too slowly on the live site, switch to `pro plus` (4 CPU) and set VOICE_THREADS to 4. On Starter or Free the model can't load (the app notices and leaves it off), and Buddy speaks with the browser's voice.

## What the public demo does differently

All of it is in `app/public_demo.py` and switched on only by `PUBLIC_DEMO=1`:

- **The week comes back every night.** When the database is empty (the first start, and after every deploy, since the host's disk is wiped then), the made-up week is loaded with its pictures (`scripts/demo_pictures/`, painted by Muse Image for this project, so nothing is painted on the host). From `DEMO_RESET_HOUR` (9:00 UTC, 1:00 AM Pacific) it is put back once a day, so a judge's test talks don't pile up.
- **A share of Buddy's thinking.** Each visitor (by the address Render reports) gets `AI_CALLS_PER_VISITOR_HOUR` (40) calls to Meta an hour, and the day has `AI_CALLS_PER_DAY` (600) for everyone. Past a share, Buddy says kind words ("You've used this demo's share of Buddy's thinking for now…") and the rest of the app keeps working. **The safety net never counts and is never stopped**: it needs no AI. Pill reminders, the diary, the pills, the Memory book's pages, the weather (Open-Meteo), and the family page all work without any Meta call.
- **A share of Buddy's voice.** Making speech is this host's CPU, not a Meta call, so it has its own share: each visitor gets `VOICE_SENTENCES_PER_VISITOR_HOUR` (300) sentences in the natural voice an hour; past it the browser's voice speaks for them, with kind words in the answer. The safety screens' words and Buddy's fixed lines are made ahead at start and are never capped.
- **No real people.** Invite codes and sign-ups are off (the made-up family account, "Try the demo as Maria", is the only one). Export and Delete everything are off. Stripe stays in demo mode (no key).
- **The key is a host secret.** It is read from the environment like at home (`app/config.py`), never logged, never sent to the browser.

## If something is off

- "Grandma Buddy only answers on this computer." on every page: `ALLOWED_HOSTS` doesn't match the service's address (step 6).
- Buddy can't hear anything: the address must be `https://` (Render's always is), and the browser must allow the microphone.
- A judge says Buddy "is resting": a share is used up. Raise `AI_CALLS_PER_VISITOR_HOUR` in the Environment tab (and deploy), or wait an hour.
- To start the week over right now: Settings, Her data, **Reset the demo week** (it is there in a public demo too). "Start fresh for a real person" is refused on a public demo: the week stays.

## Buddy's voice on the host

- **Baked into the image.** The `Dockerfile` installs `kokoro-onnx` and runs `scripts/get_voice.py` at build time, so the voice files are in the image and survive the host wiping its disk on every deploy. `espeak-ng` is installed from apt as well (kokoro-onnx also brings its own copy).
- **Loads in the background.** After each deploy the model loads (about 2 seconds) and the three safety screens' words are made ahead (about 10 seconds); then Buddy is ready, and its other fixed lines (the trouble and no-advice lines, the bridge lines) keep being made in the background, giving way to any real request. `/api/ping` answers at once, so the health check never fails; `/api/voice` says `loading` until the safety lines are made, and the page speaks with the browser's voice meanwhile, then looks again every 5 seconds (for two minutes) and switches to Heart.
- **Fast first words.** The first sentence of every reply is made the moment the reply exists, before the page asks (`voice.say_ahead`); every sentence made is kept; the same sentence asked twice at once is made once. Buddy is told to open every reply with a short sentence (under ten words), and the page waits up to 3 seconds for it; past that, the whole reply is said with the browser's voice, so she is never left waiting, and Buddy never switches voices in the middle of a reply.
- **Threads.** `VOICE_THREADS` is 2 in `render.yaml` (the Pro plan's 2 CPUs); at home it is 0 (every core).
- **One process, one instance.** Measured on the live site (Nov 3): the same sentence asked six times took 1625, 138, 142, 190, 1370, and 140 ms, so requests were being shared between two server processes, each with its own cache (Render recommends two web processes on a 2-CPU plan and uvicorn starts that many when `WEB_CONCURRENCY` is set). The `Dockerfile` now runs exactly one worker (`--workers 1`, `WEB_CONCURRENCY=1`) and `render.yaml` sets `numInstances: 1`; keep the service's Scaling at 1 instance. `/api/voice` returns a `process` marker that must be the same on every request.
- **Check after a deploy.** Settings shows Heart, Bella, Nicole, Emma, and Michael under "Buddy's natural voices" with Heart chosen; "Try it" plays; Talk to Buddy answers in Heart about a second after the words appear. In Render's **Metrics** tab, memory should sit near 700 MB and CPU should spike while Buddy speaks. If first sentences often fall back to the browser's voice, the host is too slow: `pro plus` and `VOICE_THREADS=4`. Measured on Pro (Nov 3): a repeated sentence 120 to 140 ms, the emergency lines about 110 ms, a fresh 7-word sentence about 1.5 to 2.2 s, and a real reply's first sentence through the page's path 0.9 to 1.25 s after the words appear, with Heart on every reply.
