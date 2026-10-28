# scripts/seed_demo.py
# Fills the database with MADE-UP demo data for showing the app:
# "Rose", her daughter "Maria", and "Dr. Lee". None of it is real.
#
# Run it by hand:  .venv\Scripts\python scripts\seed_demo.py
# It writes to the database set in .env (DATABASE_PATH), so it is meant for
# a demo computer, not for a real grandma's data. It grows as features are
# added (pills, diary, moods...).

import sys
from pathlib import Path

# Let this script import app/ no matter where it is run from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402

DEMO_PROFILE = {
    "name": "Rose Demo",
    "preferred_name": "Rose",
    "family_name": "Maria",
    "family_phone": "555-0100",          # 555-01xx numbers are reserved for fiction
    "family_email": "maria@example.com",  # example.com never delivers real mail
    "doctor_name": "Dr. Lee",
    "doctor_phone": "555-0199",
}


def main() -> int:
    db.init_db()
    connection = db.get_connection()
    try:
        db.get_profile(connection)
        for field, value in DEMO_PROFILE.items():
            connection.execute(f"UPDATE profile SET {field} = ? WHERE id = 1", (value,))
        connection.commit()
    finally:
        connection.close()
    print("Demo profile saved: Rose, her daughter Maria (555-0100), and Dr. Lee (555-0199). All made up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
