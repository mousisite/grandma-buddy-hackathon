# app/accounts.py
# Family accounts, for the family page (/family): the people who help her
# can sign in and see her day as she shares it (docs/SAFETY.md section 9a).
#
# - A family member joins with an invite code from Rose's Settings: six
#   letters, good for 24 hours, used once.
# - A password is never kept. Only a hash made with scrypt and a random
#   salt is stored, and a sign-in is checked in constant time. A missing
#   email takes as long to refuse as a wrong password.
# - A signed-in session is a random token in a cookie the page's scripts
#   can't read (HttpOnly); only the token's hash is kept here. It lasts 30
#   days, or until Sign out, or until the account is removed.
# - Five wrong passwords in 15 minutes lock that email for 15 minutes.
# The clock is reminders.current_time(), so tests can set it.

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from app import reminders

INVITE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I or O, which look like 1 and 0 when read aloud
INVITE_LENGTH = 6
INVITE_HOURS = 24
SESSION_DAYS = 30
SHORTEST_PASSWORD = 8
MAX_TRIES = 5
LOCK_MINUTES = 15
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Wrong passwords by email, kept in memory: the app is one process, and a
# restart forgives them.
_wrong_tries: dict[str, list[datetime]] = {}


class Problem(ValueError):
    """An entry needs another look: which one, and what to do."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class Locked(Exception):
    """Too many wrong passwords for this email: wait 15 minutes."""


def stamp(when: datetime) -> str:
    return when.isoformat(timespec="seconds")


def hash_password(password: str, salt: bytes) -> bytes:
    """scrypt: slow on purpose (about 50 ms), so guessing is slow too."""
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------- Invites (from Rose's Settings) ----------

def new_invite(connection) -> dict:
    now = reminders.current_time()
    code = "".join(secrets.choice(INVITE_LETTERS) for _ in range(INVITE_LENGTH))
    expires = now + timedelta(hours=INVITE_HOURS)
    connection.execute(
        "INSERT INTO family_invites (code, created_at, expires_at) VALUES (?, ?, ?)", (code, stamp(now), stamp(expires))
    )
    return {"code": code, "expires_at": stamp(expires)}


def use_invite(connection, code: str) -> bool:
    """Spend the code if it is real, unused, and not expired."""
    now = stamp(reminders.current_time())
    changed = connection.execute(
        "UPDATE family_invites SET used_at = ? WHERE code = ? AND used_at = '' AND expires_at > ?",
        (now, str(code or "").strip().upper(), now),
    ).rowcount
    return changed == 1


# ---------- Accounts ----------

def checked_entries(name, email, password) -> tuple[str, str]:
    """The name and email as kept, or a Problem naming the entry to fix."""
    name = " ".join(str(name or "").split())[:80]
    email = str(email or "").strip().lower()[:120]
    if not name:
        raise Problem("name", "Please type your name.")
    if not EMAIL.match(email):
        raise Problem("email", "Please check the email address. It looks like name@example.com.")
    if len(str(password or "")) < SHORTEST_PASSWORD:
        raise Problem("password", f"Please choose a password of at least {SHORTEST_PASSWORD} letters or numbers.")
    return name, email


def create_account(connection, name, email, password) -> dict:
    name, email = checked_entries(name, email, password)
    if connection.execute("SELECT 1 FROM family_accounts WHERE email = ?", (email,)).fetchone():
        raise Problem("email", "That email already has an account. Sign in instead.")
    salt = secrets.token_bytes(16)
    cursor = connection.execute(
        "INSERT INTO family_accounts (created_at, name, email, password_hash, salt) VALUES (?, ?, ?, ?, ?)",
        (stamp(reminders.current_time()), name, email, hash_password(str(password), salt), salt),
    )
    return {"id": cursor.lastrowid, "name": name, "email": email}


def accounts(connection) -> list[dict]:
    """Every family account, for Rose's Settings (no hashes, ever)."""
    return [dict(row) for row in connection.execute(
        "SELECT id, name, email, created_at FROM family_accounts ORDER BY id"
    )]


def remove_account(connection, account_id: int) -> bool:
    """Remove an account and end its sessions (from Rose's Settings)."""
    connection.execute("DELETE FROM family_sessions WHERE account_id = ?", (account_id,))
    return connection.execute("DELETE FROM family_accounts WHERE id = ?", (account_id,)).rowcount == 1


# ---------- Signing in ----------

def forget_tries() -> None:
    _wrong_tries.clear()


def locked(email: str, now: datetime) -> bool:
    recent = [tried for tried in _wrong_tries.get(email, []) if now - tried < timedelta(minutes=LOCK_MINUTES)]
    _wrong_tries[email] = recent
    return len(recent) >= MAX_TRIES


def sign_in(connection, email, password) -> dict | None:
    """The account when the email and password match, else None. Raises
    Locked after five wrong tries in 15 minutes."""
    email = str(email or "").strip().lower()
    now = reminders.current_time()
    if locked(email, now):
        raise Locked()
    row = connection.execute(
        "SELECT id, name, email, password_hash, salt FROM family_accounts WHERE email = ?", (email,)
    ).fetchone()
    # The slow hash runs either way, so a missing email takes as long as a wrong password.
    salt = row["salt"] if row else b"no such account"
    given = hash_password(str(password or ""), salt)
    if row is not None and hmac.compare_digest(given, row["password_hash"]):
        _wrong_tries.pop(email, None)
        return {"id": row["id"], "name": row["name"], "email": row["email"]}
    _wrong_tries.setdefault(email, []).append(now)
    return None


# ---------- Sessions ----------

def open_session(connection, account_id: int) -> str:
    """A new session's token (the cookie's value): only its hash is kept."""
    token = secrets.token_urlsafe(32)
    now = reminders.current_time()
    connection.execute(
        "INSERT INTO family_sessions (account_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (account_id, hash_token(token), stamp(now), stamp(now + timedelta(days=SESSION_DAYS))),
    )
    return token


def signed_in(connection, token: str | None) -> dict | None:
    """The account behind a cookie's token, while its session lasts."""
    if not token:
        return None
    row = connection.execute(
        "SELECT a.id, a.name, a.email FROM family_sessions s JOIN family_accounts a ON a.id = s.account_id "
        "WHERE s.token_hash = ? AND s.expires_at > ?",
        (hash_token(token), stamp(reminders.current_time())),
    ).fetchone()
    return dict(row) if row else None


def close_session(connection, token: str | None) -> None:
    if token:
        connection.execute("DELETE FROM family_sessions WHERE token_hash = ?", (hash_token(token),))
