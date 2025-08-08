from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os

router = APIRouter()

static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

router.mount("/static", StaticFiles(directory=static_dir), name="static")

@router.get("/")
async def index():
    index_file = os.path.join(static_dir, "index.html")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())