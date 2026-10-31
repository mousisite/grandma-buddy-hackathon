# Tests for the Family plan's checkout and billing (docs/SPEC.md feature
# 19): Stripe's hosted Checkout in TEST MODE only, so the app never sees a
# card number; without a key, a "Demo mode, no real charge" flow with no
# card fields. Stripe is always FAKE here (app/billing.py's stripe() is
# replaced), and a live key is refused before the app even starts.
# Nothing Buddy does for her is ever behind the plan.

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import accounts, billing, db, reminders
from app.config import get_settings
from app.main import app

NOW = datetime(2026, 10, 31, 10, 0)
MARIA = {"name": "Maria", "email": "maria@example.com", "password": "rose-garden-2026"}
PERIOD_END = int((NOW + timedelta(days=30)).timestamp())


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(reminders, "current_time", lambda: NOW)
    accounts.forget_tries()
    return NOW


@pytest.fixture
def maria(clock, safe_test_setup):
    """A signed-in family member (the client keeps her cookie)."""
    client = TestClient(app)
    code = client.post("/api/family/invite").json()["code"]
    assert client.post("/api/family/account", json={"code": code, **MARIA}).status_code == 200
    return client


@pytest.fixture
def test_key(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_madeup")


def fake_stripe(monkeypatch, answers: dict, calls: list | None = None):
    """Stripe's answers by (method, path); every call is written down."""
    calls = calls if calls is not None else []

    def fake(method, path, data=None, idempotency_key=None):
        calls.append({"method": method, "path": path, "data": data or {}, "idempotency_key": idempotency_key})
        answer = answers.get((method, path))
        if isinstance(answer, Exception):
            raise answer
        assert answer is not None, f"no fake answer for {method} {path}"
        return answer

    monkeypatch.setattr(billing, "stripe", fake)
    return calls


def paid_session(account_id: int = 1, **changes) -> dict:
    """A finished test-mode Checkout session, as Stripe returns it."""
    session = {
        "id": "cs_test_a1b2c3", "object": "checkout.session", "livemode": False, "mode": "subscription",
        "status": "complete", "payment_status": "paid", "amount_total": 900, "currency": "usd",
        "client_reference_id": str(account_id), "customer": "cus_test_1",
        "subscription": {"id": "sub_test_1", "status": "active", "current_period_end": PERIOD_END,
                         "cancel_at_period_end": False},
    }
    session.update(changes)
    return session


# ---------- The keys ----------

def test_a_live_key_is_refused_before_the_app_starts(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_never")
    with pytest.raises(ValueError, match="test mode"):
        get_settings()


def test_without_a_key_the_app_is_in_demo_mode(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert get_settings().stripe_secret_key == "" and billing.mode() == "demo"


# ---------- Only the family ----------

def test_billing_needs_a_signed_in_family_member(clock):
    client = TestClient(app)
    assert client.get("/api/billing").status_code == 401
    assert client.post("/api/billing/checkout").status_code == 401
    assert client.post("/api/billing/demo").status_code == 401
    assert client.post("/api/billing/cancel").status_code == 401


# ---------- Demo mode: no key, no card fields, no charge ----------

def test_demo_mode_says_so_and_starts_the_plan_without_a_card(maria, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert maria.get("/api/billing").json() == {"mode": "demo", "plan": "free", "price": "$9 a month"}
    # Checkout in demo mode: nothing to redirect to, the page shows the demo flow.
    assert maria.post("/api/billing/checkout").json() == {"demo": True}
    started = maria.post("/api/billing/demo").json()
    assert started["plan"] == "family" and started["demo"] is True
    assert started["renews_on"] == "November 30" and started["cancel_at_period_end"] is False
    assert maria.get("/api/billing").json()["plan"] == "family"


def test_demo_mode_is_refused_when_a_real_test_key_is_set(maria, test_key):
    assert maria.post("/api/billing/demo").status_code == 400


def test_cancelling_keeps_the_plan_until_the_period_ends(maria, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    maria.post("/api/billing/demo")
    ended = maria.post("/api/billing/cancel").json()
    assert ended["plan"] == "family" and ended["cancel_at_period_end"] is True and ended["ends_on"] == "November 30"


# ---------- Test mode: Stripe's hosted Checkout ----------

def test_checkout_opens_a_test_mode_subscription_for_nine_dollars(maria, test_key, monkeypatch):
    calls = fake_stripe(monkeypatch, {("POST", "/v1/checkout/sessions"): {
        "id": "cs_test_a1b2c3", "url": "https://checkout.stripe.com/c/pay/cs_test_a1b2c3"}})
    answer = maria.post("/api/billing/checkout").json()
    assert answer == {"url": "https://checkout.stripe.com/c/pay/cs_test_a1b2c3"}
    sent = calls[0]
    assert sent["idempotency_key"], "a retry never makes two sessions"
    data = sent["data"]
    assert data["mode"] == "subscription"
    assert data["line_items[0][price_data][unit_amount]"] == 900
    assert data["line_items[0][price_data][currency]"] == "usd"
    assert data["line_items[0][price_data][recurring][interval]"] == "month"
    assert data["line_items[0][quantity]"] == 1
    assert data["client_reference_id"] == "1" and data["customer_email"] == "maria@example.com"
    assert data["success_url"].endswith("/billing/return?session_id={CHECKOUT_SESSION_ID}")
    assert data["cancel_url"].endswith("/family#billing")
    # Our app never sends or sees a card number: Stripe's own page takes it.
    assert not any("card" in key for key in data)


def test_coming_back_from_checkout_records_the_paid_plan(maria, test_key, monkeypatch):
    fake_stripe(monkeypatch, {("GET", "/v1/checkout/sessions/cs_test_a1b2c3"): paid_session()})
    back = maria.get("/billing/return?session_id=cs_test_a1b2c3", follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"] == "/family#billing"
    plan = maria.get("/api/billing").json()
    assert plan == {"mode": "test", "plan": "family", "price": "$9 a month", "demo": False,
                    "renews_on": "November 30", "cancel_at_period_end": False, "ends_on": ""}


def test_coming_back_twice_records_the_plan_once(maria, test_key, monkeypatch, safe_test_setup):
    fake_stripe(monkeypatch, {("GET", "/v1/checkout/sessions/cs_test_a1b2c3"): paid_session()})
    maria.get("/billing/return?session_id=cs_test_a1b2c3", follow_redirects=False)
    maria.get("/billing/return?session_id=cs_test_a1b2c3", follow_redirects=False)
    connection = db.get_connection(safe_test_setup)
    assert connection.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 1
    connection.close()


@pytest.mark.parametrize("session_id, session", [
    ("cs_live_x", paid_session(id="cs_live_x")),                     # never a live session
    ("cs_test_a1b2c3", paid_session(livemode=True)),                  # never live mode
    ("cs_test_a1b2c3", paid_session(status="open")),                  # not finished
    ("cs_test_a1b2c3", paid_session(payment_status="unpaid")),        # not paid
    ("cs_test_a1b2c3", paid_session(account_id=2)),                   # someone else's checkout
    ("cs_test_a1b2c3", paid_session(amount_total=100)),               # not the Family plan's price
    ("cs_test_a1b2c3", paid_session(mode="payment")),                 # not a subscription
])
def test_a_checkout_that_doesnt_check_out_records_nothing(maria, test_key, monkeypatch, session_id, session):
    fake_stripe(monkeypatch, {("GET", f"/v1/checkout/sessions/{session_id}"): session})
    back = maria.get(f"/billing/return?session_id={session_id}", follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"] == "/family#billing-problem"
    assert maria.get("/api/billing").json()["plan"] == "free"


def test_coming_back_signed_out_asks_to_sign_in_first(clock, test_key, monkeypatch):
    fake_stripe(monkeypatch, {})
    back = TestClient(app).get("/billing/return?session_id=cs_test_a1b2c3", follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"] == "/family"


def test_cancelling_in_test_mode_tells_stripe(maria, test_key, monkeypatch):
    calls = fake_stripe(monkeypatch, {
        ("GET", "/v1/checkout/sessions/cs_test_a1b2c3"): paid_session(),
        ("POST", "/v1/subscriptions/sub_test_1"): {"id": "sub_test_1", "cancel_at_period_end": True,
                                                   "current_period_end": PERIOD_END},
    })
    maria.get("/billing/return?session_id=cs_test_a1b2c3", follow_redirects=False)
    ended = maria.post("/api/billing/cancel").json()
    assert ended["cancel_at_period_end"] is True and ended["ends_on"] == "November 30"
    assert calls[-1] == {"method": "POST", "path": "/v1/subscriptions/sub_test_1",
                         "data": {"cancel_at_period_end": "true"}, "idempotency_key": None}


def test_when_stripe_is_down_she_hears_a_kind_word(maria, test_key, monkeypatch):
    fake_stripe(monkeypatch, {("POST", "/v1/checkout/sessions"): billing.StripeError("HTTP 500")})
    refused = maria.post("/api/billing/checkout")
    assert refused.status_code == 503
    assert refused.json()["detail"] == "I couldn’t open the payment page just now. Please try again in a moment."


def test_nothing_buddy_does_for_her_checks_the_plan():
    # The safety net, reminders, talking, and every screen of hers never ask
    # about billing: no file of hers imports it.
    import pathlib
    for path in pathlib.Path("app").glob("*.py"):
        if path.name not in ("billing.py", "main.py"):
            assert "billing" not in path.read_text(encoding="utf-8"), path
    for path in pathlib.Path("app/routes").glob("*.py"):
        if path.name != "billing.py":
            assert "billing" not in path.read_text(encoding="utf-8"), path
