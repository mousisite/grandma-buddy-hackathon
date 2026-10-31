# scripts/check_stripe.py
# Hand-run, real check of the Family plan's checkout with Stripe, in TEST
# MODE only (app/billing.py). It opens one Checkout session for a made-up
# family member and prints its address. Nothing is charged, ever: the key
# must be a test key, and Stripe's test page takes only test cards (like
# 4242 4242 4242 4242, any future date, any three digits).
#
# Then it asks Stripe about that session, the way /billing/return does, and
# prints what our checks say (not paid yet, until you pay on that page).
#   .venv\Scripts\python scripts\check_stripe.py
#   .venv\Scripts\python scripts\check_stripe.py cs_test_…   (check a session you paid)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import billing  # noqa: E402

MARIA = {"id": 0, "email": "maria@example.com"}  # made up; nothing is saved


def main(args: list[str]) -> int:
    if billing.mode() != "test":
        print("No Stripe test key is set (STRIPE_SECRET_KEY in .env), so the app is in demo mode: nothing to check.")
        return 0
    if args:
        session = billing.stripe("GET", f"/v1/checkout/sessions/{args[0]}", {"expand[]": "subscription"})
    else:
        print("Opening one test-mode Checkout session with Stripe…")
        opened = billing.checkout(MARIA, "http://localhost:8000")
        print(f"Stripe's page (test mode, nothing is charged): {opened['url']}")
        session_id = opened["url"].rsplit("/", 1)[-1].split("#")[0]
        session = billing.stripe("GET", f"/v1/checkout/sessions/{session_id}", {"expand[]": "subscription"})
    print(f"Session {session.get('id')}: livemode={session.get('livemode')}, status={session.get('status')}, "
          f"payment_status={session.get('payment_status')}, amount_total={session.get('amount_total')} {session.get('currency')}, "
          f"mode={session.get('mode')}")
    checked = billing.checked_session(session, MARIA["id"])
    print("Our checks: " + ("it checks out, the plan would be recorded." if checked
                            else "not recorded (not paid yet, or not this family member's: as it should be)."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
