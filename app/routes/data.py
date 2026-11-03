# app/routes/data.py
# "Her data" (Settings, for a family member; app/her_data.py):
# - GET  /api/data/export   one zip: the database, her pictures, a README
# - POST /api/data/delete   {"confirm": "DELETE"}: everything gone, as on the first day
# Like every /api route, refused from any other website (app/main.py).

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app import demo, her_data

router = APIRouter()


@router.get("/api/data/export")
def export_everything():
    name = f"grandma-buddy-{datetime.now():%Y-%m-%d}.zip"
    return Response(her_data.export_zip(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


class DeleteRequest(BaseModel):
    confirm: str = ""


@router.post("/api/data/delete")
def delete_everything(request: DeleteRequest):
    """Only with the word DELETE, typed exactly."""
    if request.confirm != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to delete everything.")
    her_data.delete_everything()
    demo.remember_choice("F")  # start.bat won't bring Rose back
    return {"ok": True}
