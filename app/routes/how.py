# app/routes/how.py
# Help: GET /api/how lists every feature and the Meta model behind it
# (app/how.py), for the "How Buddy works" part of the Help screen.

from fastapi import APIRouter

from app import how
from app.config import get_settings

router = APIRouter()


@router.get("/api/how")
def how_buddy_works():
    return how.how(get_settings())
