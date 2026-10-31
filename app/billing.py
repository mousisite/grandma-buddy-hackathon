# app/billing.py
# The Family plan ($9 a month) for a signed-in family member, through
# Stripe's hosted Checkout, in TEST MODE only (docs/SAFETY.md section 9b):
# - Our app never sees a card number. It opens a Checkout session and sends
#   the family member to Stripe's own page; Stripe sends them back to
#   /billing/return, and we ask Stripe (never the address bar) whether the
#   session is finished, paid, theirs, and the right price before recording
#   the plan. The same session twice records it once.
# - A key that isn't a test key refuses to start (app/config.py). With no
#   key at all the app is in demo mode: "Demo mode, no real charge", a plan
#   started with one tap, and no card fields anywhere.
# - Nothing Buddy does for her is ever behind the plan (tests/test_billing.py
#   checks that no file of hers even mentions this one).
# Every call to Stripe lives in stripe(), which tests replace.

import re
import secrets
from datetime import datetime, timedelta

import requests

from app import reminders
from app.config import get_settings

STRIPE_URL = "https://api.stripe.com"
TIMEOUT_SECONDS = 30
PRICE_CENTS = 900
PRICE_WORDS = "$9 a month"
PLAN_NAME = "Grandma Buddy Family plan"
DEMO_DAYS = 30
SESSION_ID = re.compile(r"^cs_test_[A-Za-z0-9]+$")


class StripeError(Exception):
    """Stripe answered with a problem (never its words: the screen shows a kind message)."""


def mode() -> str:
    """ "test" with a test key in .env, else "demo" (no charge, no card fields)."""
    return "test" if get_settings().stripe_secret_key else "demo"


def stripe(method: str, path: str, data: dict | None = None, idempotency_key: str | None = None) -> dict:
    """One call to Stripe's API, form-encoded as Stripe wants. Tests replace
    this function, so they can never reach Stripe."""
    headers = {"Authorization": f"Bearer {get_settings().stripe_secret_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        response = requests.request(
            method, STRIPE_URL + path, headers=headers, timeout=TIMEOUT_SECONDS,
            params=data if method == "GET" else None, data=data if method != "GET" else None,
        )
    except requests.RequestException as problem:
        raise StripeError(type(problem).__name__)
    if response.status_code >= 400:
        raise StripeError(f"HTTP {response.status_code}")  # never the body
    return response.json()


def day_words(when: datetime) -> str:
    """ "November 30" """
    return f"{when:%B} {when.day}"


# ---------- The plan's checkout ----------

def checkout(account: dict, origin: str) -> dict:
    """Where to send a family member to pay: {"url"} to Stripe's page, or
    {"demo": True} in demo mode (the page shows the demo flow instead)."""
    if mode() == "demo":
        return {"demo": True}
    data = {
        "mode": "subscription",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": PRICE_CENTS,
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][product_data][name]": PLAN_NAME,
        "line_items[0][quantity]": 1,
        "client_reference_id": str(account["id"]),
        "customer_email": account["email"],
        "success_url": f"{origin}/billing/return?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{origin}/family#billing",
    }
    # Two taps in the same minute reuse the same session instead of making two.
    minute = int(reminders.current_time().timestamp()) // 60
    session = stripe("POST", "/v1/checkout/sessions", data, idempotency_key=f"buddy-checkout-{account['id']}-{minute}")
    url = session.get("url")
    if not url or not SESSION_ID.match(str(session.get("id", ""))):
        raise StripeError("no test-mode checkout page came back")
    return {"url": url}


def checked_session(session: dict, account_id: int) -> dict | None:
    """The subscription from a finished test-mode Checkout that is this
    family member's, paid, and the Family plan's price. Else None."""
    subscription = session.get("subscription")
    fine = (
        SESSION_ID.match(str(session.get("id", "")))
        and session.get("livemode") is False
        and session.get("mode") == "subscription"
        and session.get("status") == "complete"
        and session.get("payment_status") == "paid"
        and session.get("amount_total") == PRICE_CENTS
        and session.get("currency") == "usd"
        and session.get("client_reference_id") == str(account_id)
        and isinstance(subscription, dict)
        and str(subscription.get("id", "")).startswith("sub_")
    )
    return subscription if fine else None


def record_return(connection, account_id: int, session_id: str) -> bool:
    """Back from Checkout: ask Stripe about the session and record the plan.
    True when it checked out; False when it didn't (nothing is recorded)."""
    if not SESSION_ID.match(session_id or "") or len(session_id) > 200:
        return False
    session = stripe("GET", f"/v1/checkout/sessions/{session_id}", {"expand[]": "subscription"})
    subscription = checked_session(session, account_id)
    if subscription is None:
        return False
    save_plan(connection, account_id, demo=False, checkout_session_id=session_id,
              stripe_subscription_id=subscription["id"], stripe_customer_id=str(session.get("customer") or ""),
              period_end=datetime.fromtimestamp(int(subscription["current_period_end"])),
              cancel_at_period_end=bool(subscription.get("cancel_at_period_end")))
    return True


def start_demo(connection, account_id: int) -> dict:
    """Demo mode: the Family plan with one tap, no charge, for 30 days."""
    if mode() != "demo":
        raise ValueError("not in demo mode")
    now = reminders.current_time()
    save_plan(connection, account_id, demo=True, checkout_session_id=f"demo-{account_id}-{secrets.token_hex(6)}",
              stripe_subscription_id="", stripe_customer_id="", period_end=now + timedelta(days=DEMO_DAYS),
              cancel_at_period_end=False)
    return status(connection, account_id)


# ---------- Keeping the plan ----------

def save_plan(connection, account_id: int, demo: bool, checkout_session_id: str, stripe_subscription_id: str,
              stripe_customer_id: str, period_end: datetime, cancel_at_period_end: bool) -> None:
    """One plan per account: a new checkout replaces the old row; the same
    checkout again changes nothing (checkout_session_id is unique)."""
    now = reminders.current_time().isoformat(timespec="seconds")
    already = connection.execute("SELECT 1 FROM subscriptions WHERE checkout_session_id = ?", (checkout_session_id,)).fetchone()
    if already:
        return
    connection.execute("DELETE FROM subscriptions WHERE account_id = ?", (account_id,))
    connection.execute(
        "INSERT INTO subscriptions (account_id, plan, demo, checkout_session_id, stripe_subscription_id, "
        "stripe_customer_id, current_period_end, cancel_at_period_end, created_at, updated_at) "
        "VALUES (?, 'family', ?, ?, ?, ?, ?, ?, ?, ?)",
        (account_id, int(demo), checkout_session_id, stripe_subscription_id, stripe_customer_id,
         period_end.isoformat(timespec="seconds"), int(cancel_at_period_end), now, now),
    )


def current(connection, account_id: int):
    return connection.execute(
        "SELECT * FROM subscriptions WHERE account_id = ? ORDER BY id DESC LIMIT 1", (account_id,)
    ).fetchone()


def status(connection, account_id: int) -> dict:
    """The plan for the family page: free, or the Family plan and when it
    renews (or ends, once cancelled)."""
    answer = {"mode": mode(), "plan": "free", "price": PRICE_WORDS}
    row = current(connection, account_id)
    if row is None or row["plan"] != "family":
        return answer
    end = datetime.fromisoformat(row["current_period_end"])
    cancelled = bool(row["cancel_at_period_end"])
    answer.update({
        "plan": "family",
        "demo": bool(row["demo"]),
        "renews_on": "" if cancelled else day_words(end),
        "cancel_at_period_end": cancelled,
        "ends_on": day_words(end) if cancelled else "",
    })
    return answer


def cancel(connection, account_id: int) -> dict:
    """Cancel at the end of the period: the plan stays until then. In test
    mode Stripe is told; a demo plan is just marked."""
    row = current(connection, account_id)
    if row is None or row["plan"] != "family":
        raise ValueError("no Family plan to cancel")
    period_end = row["current_period_end"]
    if not row["demo"]:
        answer = stripe("POST", f"/v1/subscriptions/{row['stripe_subscription_id']}", {"cancel_at_period_end": "true"})
        if answer.get("current_period_end"):
            period_end = datetime.fromtimestamp(int(answer["current_period_end"])).isoformat(timespec="seconds")
    connection.execute(
        "UPDATE subscriptions SET cancel_at_period_end = 1, current_period_end = ?, updated_at = ? WHERE id = ?",
        (period_end, reminders.current_time().isoformat(timespec="seconds"), row["id"]),
    )
    return status(connection, account_id)
