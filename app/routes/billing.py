# app/routes/billing.py
# The Family plan on the family page (app/billing.py), for a signed-in
# family member only:
# - GET  /api/billing            the plan: free, or Family and when it renews
# - POST /api/billing/checkout   {"url"} to Stripe's test-mode page, or {"demo": true}
# - POST /api/billing/demo       demo mode only: the plan with one tap, no charge
# - POST /api/billing/cancel     cancel at the end of the period
# - GET  /billing/return         back from Stripe's page: checked, recorded, home
# Nothing of hers is behind the plan; these routes are the family's only.

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import billing, db
from app.routes.family_accounts import COOKIE, signed_in_account
from app import accounts

router = APIRouter()

COULDNT_OPEN = "I couldn’t open the payment page just now. Please try again in a moment."
COULDNT_CANCEL = "I couldn’t cancel it just now. Please try again in a moment."


def origin(request: Request) -> str:
    """Where Stripe sends her back: this app's own address."""
    return f"{request.url.scheme}://{request.headers.get('host', 'localhost:8000')}"


@router.get("/api/billing")
def plan(request: Request):
    connection = db.get_connection()
    try:
        account = signed_in_account(request, connection)
        return billing.status(connection, account["id"])
    finally:
        connection.close()


@router.post("/api/billing/checkout")
def checkout(request: Request):
    connection = db.get_connection()
    try:
        account = signed_in_account(request, connection)
    finally:
        connection.close()
    try:
        return billing.checkout(account, origin(request))
    except billing.StripeError as problem:
        print(f"Checkout couldn't open: {problem}")  # the kind of trouble, never a key or a card
        raise HTTPException(status_code=503, detail=COULDNT_OPEN)


@router.post("/api/billing/demo")
def start_demo(request: Request):
    """Demo mode only: no key, no charge, no card fields."""
    if billing.mode() != "demo":
        raise HTTPException(status_code=400, detail="Payments run through Stripe here. Tap Start the Family plan instead.")
    connection = db.get_connection()
    try:
        account = signed_in_account(request, connection)
        answer = billing.start_demo(connection, account["id"])
        connection.commit()
        return answer
    finally:
        connection.close()


@router.post("/api/billing/cancel")
def cancel(request: Request):
    connection = db.get_connection()
    try:
        account = signed_in_account(request, connection)
        try:
            answer = billing.cancel(connection, account["id"])
        except ValueError:
            raise HTTPException(status_code=400, detail="There is no Family plan to cancel.")
        except billing.StripeError as problem:
            print(f"Cancelling couldn't reach Stripe: {problem}")
            raise HTTPException(status_code=503, detail=COULDNT_CANCEL)
        connection.commit()
        return answer
    finally:
        connection.close()


@router.get("/billing/return")
def back_from_checkout(request: Request, session_id: str = ""):
    """Stripe sends her here after paying. The session is checked with
    Stripe before anything is recorded; then back to the family page."""
    connection = db.get_connection()
    try:
        account = accounts.signed_in(connection, request.cookies.get(COOKIE))
        if account is None:
            return RedirectResponse("/family", status_code=303)  # sign in first
        try:
            recorded = billing.record_return(connection, account["id"], session_id)
        except billing.StripeError as problem:
            print(f"Checking the checkout with Stripe failed: {problem}")
            recorded = False
        if recorded:
            connection.commit()
    finally:
        connection.close()
    return RedirectResponse("/family#billing" if recorded else "/family#billing-problem", status_code=303)
