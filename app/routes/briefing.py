# app/routes/briefing.py
# GET /api/briefing/weather (or news, sports): what's happening today in her
# town, looked up on the web (app/briefing.py), for the weather row on Home.
# When there is nothing to show (no town yet, nothing found, or the search
# failed with nothing kept from today), the answer is empty: that is normal
# for Home, not an error (a browser would log every 404 or 503 as one).

from fastapi import APIRouter, HTTPException

from app import briefing, db, meta_client

router = APIRouter()

NOTHING = {"text": "", "sites": []}


@router.get("/api/briefing/{topic}")
def todays(topic: str):
    if topic not in briefing.QUESTIONS:
        raise HTTPException(status_code=404, detail="There is nothing like that to look up.")
    connection = db.get_connection()
    try:
        found = briefing.look_up(connection, topic, db.get_profile(connection)["city"])
    except meta_client.MetaError as problem:
        print(f"Looking up today's {topic} failed: {problem}")
        found = None
    finally:
        connection.close()
    return found or NOTHING
