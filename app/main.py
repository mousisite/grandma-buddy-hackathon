# app/main.py
# Starts the Grandma Buddy web server.
#
# Run it with: .venv\Scripts\python -m uvicorn app.main:app --reload
# Then open http://localhost:8000 in Chrome or Edge.

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db, security
from app.config import get_settings
from app import voice
from app.routes import briefing, checkin, companion, diary, family, find, how, learned, listen, meds, memories, notes, profile, read, scam
from app.routes import voice as voice_routes

# The folder with index.html, styles.css, and app.js.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts: make sure the database exists.
    db.init_db(get_settings().database_path)
    # Buddy's natural voice loads in the background (about 3 seconds), so
    # the app opens at once and her first reply never waits for it.
    if voice.available():
        threading.Thread(target=voice.warm_up, daemon=True).start()
    yield
    # Nothing to clean up when the server stops.


app = FastAPI(title="Grandma Buddy", lifespan=lifespan)

# Talking: /api/transcribe and /api/chat (safety net first).
app.include_router(companion.router)
# Her profile: names, phone numbers, voice settings.
app.include_router(profile.router)
# Questions for her doctor.
app.include_router(notes.router)
# Her symptom diary.
app.include_router(diary.router)
# Her pills and pill reminders.
app.include_router(meds.router)
# The daily check-in: once a day, Buddy asks how she is.
app.include_router(checkin.router)
# Check a message: is it a scam?
app.include_router(scam.router)
# The family update: one day in plain words, sent from her own email app.
app.include_router(family.router)
# The Memory book: her stories, written in her words, each with a painting.
app.include_router(memories.router)
# Find my things: SAM 3.1 finds her glasses in a photo, Spark says where.
app.include_router(find.router)
# Buddy's natural voice (Kokoro, on this computer).
app.include_router(voice_routes.router)
# What Buddy has learned about her (Settings): see it, forget it, undo.
app.include_router(learned.router)
# Help: how Buddy works (each feature and its Meta model).
app.include_router(how.router)
# Today's weather, a local story, or sports, from the web (Meta's web search).
app.include_router(briefing.router)
# Hands-free talking: her microphone, live, to Meta's realtime speech-to-text.
app.include_router(listen.router)
# Read it to me: a photo of a letter or bill, in plain words.
app.include_router(read.router)


@app.middleware("http")
async def only_buddys_own_page(request, call_next):
    """Refuse a request for another host name (400), and an /api request
    that another website sent (403): app/security.py says why."""
    host = request.headers.get("host", "")
    if not security.allowed_host(host, get_settings().allowed_hosts):
        return JSONResponse({"detail": "Grandma Buddy only answers on this computer."}, status_code=400)
    if request.url.path.startswith("/api/") and not security.from_buddys_page(
        request.headers, f"{request.url.scheme}://{host}"
    ):
        return JSONResponse({"detail": "Only Grandma Buddy's own page can do that."}, status_code=403)
    return await call_next(request)


# The pages for the family member who sets Buddy up (docs/SPEC.md feature
# 17): the landing, Privacy, and Terms. Plain files, served like Home.
PAGES = {"/about": "about.html", "/privacy": "privacy.html", "/terms": "terms.html"}


@app.middleware("http")
async def always_check_for_updates(request, call_next):
    """The pages and their files are always checked for a newer version
    ("no-cache"), so a browser never keeps running an old copy after the app
    changes. Unchanged files just get a quick "not modified" answer."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path in PAGES or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/ping")
def ping():
    """Server check. Answers {"ok": true} so we know the app is running."""
    return {"ok": True}


@app.get("/")
def home():
    """The home screen."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/about")
def about():
    """The landing page: what Buddy is, for the family member who sets it up."""
    return FileResponse(STATIC_DIR / PAGES["/about"])


@app.get("/privacy")
def privacy():
    """Where her data lives and what Meta gets, in plain words."""
    return FileResponse(STATIC_DIR / PAGES["/privacy"])


@app.get("/terms")
def terms():
    """What Buddy is and isn't, in plain words."""
    return FileResponse(STATIC_DIR / PAGES["/terms"])


# Serves styles.css, app.js, and later recorder.js and speech.js.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
