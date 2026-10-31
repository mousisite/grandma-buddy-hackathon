# app/her_data.py
# "Her data" in Settings, for a family member (docs/SPEC.md feature 21):
# - Export everything: one zip with a whole copy of the database (SQLite's
#   own backup, so it is complete even while the app runs), her memory book
#   pictures and photos, and a README. Never .env, never backups.
# - Delete everything: every table emptied (the tables stay, so the app
#   keeps working, as on the first day), ids starting from 1 again, the file
#   shrunk (VACUUM), her pictures and photos gone, old backups gone, and the
#   voice's remembered sentences forgotten. It can't be undone: the screen
#   asks for the word DELETE first.

import io
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from app import db, memories, voice
from app.config import get_settings

README = """Grandma Buddy: everything the app wrote down, exported on {date}.

grandma-buddy.db   The database: her profile, diary, pills and reminders,
                   check-ins and moods, doctor questions, memory book pages,
                   what Buddy learned, safety screens (kind and time), the
                   family accounts (password hashes only, never passwords).
                   It is a SQLite file: any SQLite viewer opens it, and the
                   app can use it again as data/grandma_buddy.db.
memories/          The memory book's paintings and her own photos.

Nothing here was ever sent anywhere but Meta's standard models, to be
answered. This export never includes the app's .env file (the API key).
"""


def export_zip() -> bytes:
    """Everything, as one zip file's bytes."""
    source = sqlite3.connect(get_settings().database_path)
    copy = sqlite3.connect(":memory:")
    try:
        source.backup(copy)
        database = copy.serialize()
    finally:
        copy.close()
        source.close()
    packed_file = io.BytesIO()
    with zipfile.ZipFile(packed_file, "w", zipfile.ZIP_DEFLATED) as packed:
        packed.writestr("grandma-buddy.db", database)
        pictures = memories.pictures_dir()
        if pictures.is_dir():
            for path in sorted(pictures.iterdir()):
                if path.is_file():
                    packed.write(path, f"memories/{path.name}")
        packed.writestr("README.txt", README.format(date=f"{datetime.now():%B} {datetime.now().day}, {datetime.now().year}"))
    return packed_file.getvalue()


def delete_everything() -> None:
    """Buddy as on the first day. The caller has checked the word DELETE."""
    connection = db.get_connection()
    try:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )]
        for table in tables:  # names from the database itself, never from a request
            connection.execute(f"DELETE FROM {table}")
        connection.execute("DELETE FROM sqlite_sequence")
        connection.commit()
        connection.execute("VACUUM")  # the space back, and nothing left in the file
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    shutil.rmtree(memories.pictures_dir(), ignore_errors=True)
    for backup in Path(get_settings().database_path).parent.glob("backup-*.db"):
        backup.unlink(missing_ok=True)
    voice.speech.cache_clear()  # sentences made in her name, kept in memory
