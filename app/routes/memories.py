# app/routes/memories.py
# The Memory book (docs/SPEC.md feature 10).
# - GET  /api/memories               every page, newest first
# - GET  /api/memories/{id}/picture  a page's painting (from data/memories/)
# - POST /api/memories               "Save it in my memory book": her memory from a talk
# - POST /api/memories/{id}/paint    "Paint it again", when painting didn't work
# Writing and painting happen in the background (app/memories.py), so these
# answer at once and the screen shows a shimmer until the page is ready.

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import db, memories, tools

router = APIRouter()


class SaveRequest(BaseModel):
    conversation_id: str
    mode: str = "chat"  # the talk the button was shown in: "chat" or "memory"


@router.get("/api/memories")
def memory_book():
    connection = db.get_connection()
    try:
        return {"pages": memories.pages(connection)}
    finally:
        connection.close()


@router.get("/api/memories/{memory_id}/picture")
def picture(memory_id: int):
    connection = db.get_connection()
    try:
        row = connection.execute("SELECT picture FROM memories WHERE id = ?", (memory_id,)).fetchone()
    finally:
        connection.close()
    # Only a file name we saved ourselves, never a path from the request.
    path = memories.picture_path(row["picture"]) if row else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="No picture yet.")
    return FileResponse(path, media_type=memories.MEDIA_TYPES[path.suffix[1:]])


@router.post("/api/memories")
def save(request: SaveRequest, background: BackgroundTasks):
    """The "Save it in my memory book" button under Buddy's words."""
    if len(request.conversation_id) > 80 or request.mode not in tools.MEMORY_MODES:
        raise HTTPException(status_code=400, detail="Please try again.")
    connection = db.get_connection()
    try:
        memory_id, new = tools.save_memory(connection, request.conversation_id, request.mode)
        if memory_id is None:
            raise HTTPException(status_code=400, detail="Tell Buddy your memory first, then tap Save.")
        connection.commit()
        if new:  # saved already: the same page, never a second painting
            background.add_task(memories.make_page, memory_id)
        return memories.page(connection, memory_id)
    finally:
        connection.close()


@router.post("/api/memories/{memory_id}/paint")
def paint_again(memory_id: int, background: BackgroundTasks):
    """ "Paint it again": only for a page whose painting didn't work."""
    connection = db.get_connection()
    try:
        page = memories.page(connection, memory_id)
        if page is None:
            raise HTTPException(status_code=404, detail="I couldn’t find that page.")
        if page["status"] == "no_picture":
            memories.paint_again(connection, memory_id)
            connection.commit()
            background.add_task(memories.make_page, memory_id)
        return memories.page(connection, memory_id)
    finally:
        connection.close()
