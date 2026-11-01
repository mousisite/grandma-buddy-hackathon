# app/routes/family_accounts.py
# The family page (/family, static/family.html) and its accounts
# (app/accounts.py). Two sides:
# - Rose's Settings (her own page): make an invite code, see the family
#   accounts, remove one.
# - The family member: join with the code, sign in and out, and see her
#   day as she shares it (app/family.py day_facts).
# Every request here is refused from another website by app/main.py's
# checks, so the session cookie can't be used behind her family's back.

from datetime import date as calendar_date, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import accounts, db, demo, family, reminders

router = APIRouter()

COOKIE = "buddy_family"
DAYS_BACK = 30  # the family page shows the last 30 days
BAD_CODE = {"field": "code", "message": "That code didn’t work. Ask for a new one in Buddy’s Settings."}


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    """The session, in a cookie only the server can read (HttpOnly), sent
    only with the page's own requests (SameSite), and only over HTTPS when
    the page came that way."""
    response.set_cookie(COOKIE, token, max_age=accounts.SESSION_DAYS * 24 * 3600, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https", path="/")


def refuse(problem: accounts.Problem):
    raise HTTPException(status_code=400, detail={"field": problem.field, "message": problem.message})


# ---------- Rose's Settings ----------

@router.post("/api/family/invite")
def invite():
    """A new six-letter code, good for 24 hours, used once."""
    connection = db.get_connection()
    try:
        code = accounts.new_invite(connection)
        connection.commit()
        return code
    finally:
        connection.close()


@router.get("/api/family/accounts")
def family_accounts():
    connection = db.get_connection()
    try:
        return accounts.accounts(connection)
    finally:
        connection.close()


@router.delete("/api/family/accounts/{account_id}")
def remove_family_account(account_id: int):
    """Remove an account: its sessions end at once."""
    connection = db.get_connection()
    try:
        if not accounts.remove_account(connection, account_id):
            raise HTTPException(status_code=404, detail="That account isn’t there anymore.")
        connection.commit()
        return {"ok": True}
    finally:
        connection.close()


# ---------- The family member ----------

class JoinRequest(BaseModel):
    code: str = ""
    name: str = ""
    email: str = ""
    password: str = ""


@router.post("/api/family/account")
def join(body: JoinRequest, request: Request, response: Response):
    """Join with an invite code; signed in at once."""
    connection = db.get_connection()
    try:
        if not accounts.use_invite(connection, body.code):
            raise HTTPException(status_code=400, detail=BAD_CODE)
        try:
            account = accounts.create_account(connection, body.name, body.email, body.password)
        except accounts.Problem as problem:
            connection.rollback()  # the code is not spent on a refused entry
            refuse(problem)
        token = accounts.open_session(connection, account["id"])
        connection.commit()
    finally:
        connection.close()
    set_session_cookie(response, request, token)
    return {"name": account["name"], "email": account["email"]}


class SignInRequest(BaseModel):
    email: str = ""
    password: str = ""


@router.post("/api/family/sign-in")
def sign_in(body: SignInRequest, request: Request, response: Response):
    connection = db.get_connection()
    try:
        try:
            account = accounts.sign_in(connection, body.email, body.password)
        except accounts.Locked:
            raise HTTPException(status_code=429, detail="Too many tries. Please wait 15 minutes, then try again.")
        if account is None:
            raise HTTPException(status_code=401, detail="That email and password don’t match.")
        token = accounts.open_session(connection, account["id"])
        connection.commit()
    finally:
        connection.close()
    set_session_cookie(response, request, token)
    return {"name": account["name"], "email": account["email"]}


@router.post("/api/family/sign-out")
def sign_out(request: Request, response: Response):
    connection = db.get_connection()
    try:
        accounts.close_session(connection, request.cookies.get(COOKIE))
        connection.commit()
    finally:
        connection.close()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


def signed_in_account(request: Request, connection) -> dict:
    account = accounts.signed_in(connection, request.cookies.get(COOKIE))
    if account is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return account


def demo_account(connection):
    """The made-up family account the demo week adds (app/demo.py), or None."""
    return connection.execute("SELECT id, name, email FROM family_accounts WHERE email = ?",
                              (demo.FAMILY_ACCOUNT["email"],)).fetchone()


@router.get("/api/family/me")
def me(request: Request):
    """ "Am I signed in?": a plain answer either way (not a 401, which the
    browser would log as an error on every visit). Signed out, it also says
    whether a judge can try the page as Maria (demo mode, the demo week loaded)."""
    connection = db.get_connection()
    try:
        account = accounts.signed_in(connection, request.cookies.get(COOKIE))
        if account is None:
            return {"signed_in": False, "demo": demo.demo_mode(), "demo_account": demo_account(connection) is not None}
    finally:
        connection.close()
    return {"signed_in": True, "name": account["name"], "email": account["email"]}


@router.post("/api/family/demo-sign-in")
def demo_sign_in(request: Request, response: Response):
    """ "Try the demo as Maria": signs into the demo week's made-up family
    account, in demo mode only (no Stripe key), so a judge can see the
    family page and the no-card plan. 404 otherwise, or without the demo week."""
    if not demo.demo_mode():
        raise HTTPException(status_code=404, detail="Not in demo mode.")
    connection = db.get_connection()
    try:
        account = demo_account(connection)
        if account is None:
            raise HTTPException(status_code=404, detail="The demo week isn’t loaded. Run scripts/seed_demo.py first.")
        token = accounts.open_session(connection, account["id"])
        connection.commit()
    finally:
        connection.close()
    set_session_cookie(response, request, token)
    return {"name": account["name"], "email": account["email"]}


@router.get("/api/family/dashboard")
def dashboard(request: Request, date: str = ""):
    """Her day as she shares it: today, or a day in the last 30 days."""
    today = reminders.current_time().date()
    try:
        day = calendar_date.fromisoformat(date) if date else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Please choose a day in the last 30 days.")
    if not today - timedelta(days=DAYS_BACK) <= day <= today:
        raise HTTPException(status_code=400, detail="Please choose a day in the last 30 days.")
    connection = db.get_connection()
    try:
        signed_in_account(request, connection)
        facts = family.day_facts(connection, day, db.get_profile(connection))
        connection.commit()  # today's reminder rows, if any were made
        return facts
    finally:
        connection.close()
