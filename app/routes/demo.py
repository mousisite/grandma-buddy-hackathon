# app/routes/demo.py
# The demo week, in demo mode only (no Stripe key, app/demo.py):
# - GET  /api/demo        {"demo": in demo mode?, "seeded": is the demo week loaded?}
# - POST /api/demo/reset  start the demo week over (a backup first), ending today;
#                         the Memory book pictures are painted in the background
#                         when an API key is set (about 3 cents)
# - POST /api/demo/fresh  "Start fresh for a real person": a backup, an empty
#                         Buddy, the welcome flow next, and the demo week never
#                         loaded by itself again (refused on a public demo)
# Outside demo mode all three answer 404: a real family's data is never one
# tap from being wiped.

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app import db, demo, memories, public_demo
from app.config import get_settings

router = APIRouter()


def only_in_demo_mode() -> None:
    if not demo.demo_mode():
        raise HTTPException(status_code=404, detail="Not in demo mode.")


@router.get("/api/demo")
def demo_state():
    connection = db.get_connection()
    try:
        seeded = db.get_profile(connection)["name"] == demo.DEMO_NAME
    finally:
        connection.close()
    return {"demo": demo.demo_mode(), "seeded": seeded, "public": public_demo.on()}


def paint_pages(pages: list[int]) -> None:
    """The demo week's Memory book pictures, one after another."""
    for page in pages:
        connection = db.get_connection()
        try:
            memories.paint_again(connection, page)
            connection.commit()
        finally:
            connection.close()
        memories.make_page(page)


@router.post("/api/demo/reset")
def reset_demo(background: BackgroundTasks):
    """ "Reset the demo week" in Settings, Her data."""
    only_in_demo_mode()
    made = demo.reset()
    painting = bool(get_settings().model_api_key)
    if painting:
        background.add_task(paint_pages, made["pages"])
    return {"ok": True, "backup": made["backup"], "painting": painting}


@router.post("/api/demo/fresh")
def start_fresh():
    """ "Start fresh for a real person" in Settings, Her data."""
    only_in_demo_mode()
    return {"ok": True, **demo.start_fresh()}
