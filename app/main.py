# app/main.py
# Starts the Grandma Buddy web server.
#
# Run it with: .venv\Scripts\python -m uvicorn app.main:app --reload
# Then open http://localhost:8000 in Chrome or Edge.

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.config import get_settings
from app.routes import companion, diary, notes, profile

# The folder with index.html, styles.css, and app.js.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts: make sure the database exists.
    db.init_db(get_settings().database_path)
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


@app.get("/api/ping")
def ping():
    """Server check. Answers {"ok": true} so we know the app is running."""
    return {"ok": True}


@app.get("/")
def home():
    """The home screen."""
    return FileResponse(STATIC_DIR / "index.html")


# Serves styles.css, app.js, and later recorder.js and speech.js.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
