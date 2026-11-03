# A public demo of Grandma Buddy

For judges who want a live link. The app runs as a **public demo** (`PUBLIC_DEMO=1`): Rose's made-up week, put back every night, each visitor gets a share of Buddy's thinking, the day has a cap so the Meta key's credits can't be drained, no one can sign up or wipe anything, and the key lives only as a secret on the host. Nothing real is ever in it.

## Which host

**Render** (render.com) is the simplest for this app: one web service built from the `Dockerfile` in this repository, HTTPS included (the microphone needs it), WebSockets allowed (hands-free talking needs them), secrets kept out of the code, and deploys straight from GitHub.

| | What you get | Cost |
| --- | --- | --- |
| Render **Starter** (recommended for judging) | always on, 512 MB | $7 a month, cancel any time (Render bills by the hour: about $0.25 a day) |
| Render **Free** | the same, but it sleeps after 15 minutes without visitors and takes about a minute to wake up | $0 |

Fly.io and Railway work too (the same `Dockerfile`), but need a command-line tool or a card up front. Buddy here uses about 150 MB of memory (the natural voice isn't installed on the host; the browser's own voice speaks, Edge's sound the warmest), so the smallest plan is enough. Meta's calls are the only other cost: a judge's three-minute demo is about 15 calls, a cent or two; the daily cap of 600 calls keeps the worst day under about $3.

## Before you start (5 minutes)

1. Push the repository to GitHub (it must be public for the hackathon anyway).
2. Have your Meta Model API key ready to paste. Never put it in the code or in `render.yaml`: it goes into Render's secret store in step 6 below.

## Click by click (Render, about 10 minutes)

1. Go to https://render.com and sign up with your GitHub account (free). Allow Render to see the `grandma-buddy-hackathon` repository when it asks.
2. In the Render dashboard, click **New +** (top right), then **Blueprint**.
3. Pick the repository. Render finds `render.yaml` and shows one service, **grandma-buddy**. Click **Apply**.
4. Render asks for the values marked as secrets: paste your key into **MODEL_API_KEY**. Click **Apply** again. The first build takes 3 to 5 minutes (it installs the packages into a small Linux image).
5. When the service shows **Live**, click its name. Its address is at the top, like `https://grandma-buddy-ab12.onrender.com`. Copy it.
6. Open the service's **Environment** tab. Set **ALLOWED_HOSTS** to that address without `https://` (for example `grandma-buddy-ab12.onrender.com`). The app only answers to its own address (`app/security.py`), so until this matches, every page says "Grandma Buddy only answers on this computer." Click **Save, rebuild, and deploy**.
7. Open the address in Chrome or Edge. Home shows "Good morning, Rose" and the made-up week. Allow the microphone when asked and tap **Talk to Buddy**.
8. Open `/family` on that address and tap **Try the demo as Maria**.
9. Optional: to stop paying, open the service's **Settings** and click **Delete Web Service**, or switch its plan to Free.

The plan is set in `render.yaml` (`plan: starter`). Change it to `free` before step 3 if you'd rather not pay; then tell judges the first visit may take a minute to wake up.

## What the public demo does differently

All of it is in `app/public_demo.py` and switched on only by `PUBLIC_DEMO=1`:

- **The week comes back every night.** When the database is empty (the first start, and after every deploy, since the host's disk is wiped then), the made-up week is loaded with its pictures (`scripts/demo_pictures/`, painted by Muse Image for this project, so nothing is painted on the host). From `DEMO_RESET_HOUR` (9:00 UTC, 1:00 AM Pacific) it is put back once a day, so a judge's test talks don't pile up.
- **A share of Buddy's thinking.** Each visitor (by the address Render reports) gets `AI_CALLS_PER_VISITOR_HOUR` (40) calls to Meta an hour, and the day has `AI_CALLS_PER_DAY` (600) for everyone. Past a share, Buddy says kind words ("You've used this demo's share of Buddy's thinking for now…") and the rest of the app keeps working. **The safety net never counts and is never stopped**: it needs no AI. Pill reminders, the diary, the pills, the Memory book's pages, the weather (Open-Meteo), and the family page all work without any Meta call.
- **No real people.** Invite codes and sign-ups are off (the made-up family account, "Try the demo as Maria", is the only one). Export and Delete everything are off. Stripe stays in demo mode (no key).
- **The key is a host secret.** It is read from the environment like at home (`app/config.py`), never logged, never sent to the browser.

## If something is off

- "Grandma Buddy only answers on this computer." on every page: `ALLOWED_HOSTS` doesn't match the service's address (step 6).
- Buddy can't hear anything: the address must be `https://` (Render's always is), and the browser must allow the microphone.
- A judge says Buddy "is resting": a share is used up. Raise `AI_CALLS_PER_VISITOR_HOUR` in the Environment tab (and deploy), or wait an hour.
- To start the week over right now: Settings, Her data, **Reset the demo week** (it is there in a public demo too). "Start fresh for a real person" is refused on a public demo: the week stays.
