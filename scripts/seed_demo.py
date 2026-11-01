# scripts/seed_demo.py
# A made-up week for "Rose", for the demo video: every screen filled in.
# The week itself lives in app/demo.py (so Settings can reset it with one
# tap in demo mode); this is the command-line way to add it.
#
# Run it by hand:
#   .venv\Scripts\python scripts\seed_demo.py
# It refuses if the app already has pills or diary entries, so nothing is
# ever overwritten by accident. To start over with the demo week:
#   .venv\Scripts\python scripts\seed_demo.py --reset
# --reset first saves a copy of the database (data\backup-<date>-<time>.db),
# then wipes it, the Memory book pictures, and the voice messages, then adds
# the demo week, ending today.
# The 3 Memory book pictures cost about 3 cents; --no-paint skips them.

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, demo, memories  # noqa: E402
from app.config import get_settings  # noqa: E402

# Kept here by name for scripts and checks that import them from this file.
FAMILY_ACCOUNT, MESSAGES, TODAY_TALK, POSTCARDS, PHOTO_PAGE = (
    demo.FAMILY_ACCOUNT, demo.MESSAGES, demo.TODAY_TALK, demo.POSTCARDS, demo.PHOTO_PAGE)
at, seed, has_data, back_up_and_wipe = demo.at, demo.seed, demo.has_data, demo.back_up_and_wipe


def main(args: list[str]) -> int:
    path = get_settings().database_path
    db.init_db(path)
    connection = db.get_connection(path)
    try:
        if demo.has_data(connection) and "--reset" not in args:
            print("The app already has pills or diary entries, so nothing was changed.")
            print("To start over with the demo week (a backup is saved first), run:")
            print("  .venv\\Scripts\\python scripts\\seed_demo.py --reset")
            return 1
    finally:
        connection.close()
    if "--reset" in args:
        print(f"Saved a copy of the old data in {demo.back_up_and_wipe(path)}")
    connection = db.get_connection(path)
    try:
        pages = demo.seed(connection, datetime.now())
        connection.commit()
    finally:
        connection.close()
    print("Added a made-up week for Rose, ending today: 2 pills (this morning's taken), 5 check-ins, a knee that comes")
    print("and goes, 2 questions for Dr. Lee, 1 checked scam text, 3 Memory book pages (one from an old photo), what")
    print("Buddy has learned about her, 4 messages with Maria (one of hers still new), yesterday's postcard (sent),")
    print("today's postcard (ready to send), and this morning's talk about her tulips.")
    print(f"Family page: open /family and sign in as {demo.FAMILY_ACCOUNT['email']} with the password "
          f"{demo.FAMILY_ACCOUNT['password']} (Rose shares her diary in the demo), or tap \"Try the demo as Maria\".")
    if "--no-paint" in args or not get_settings().model_api_key:
        print("The Memory book pages have no pictures yet: open a page and tap \"Paint it again\".")
    else:
        print("Painting the 3 Memory book pictures with Muse Image (about 3 cents)…")
        for page in pages:
            connection = db.get_connection(path)
            memories.paint_again(connection, page)
            connection.commit()
            connection.close()
            memories.make_page(page)
        print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
