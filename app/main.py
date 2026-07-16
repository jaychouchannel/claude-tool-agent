"""FastAPI entry point — multi-role Claude chatroom."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .chatroom import router as chatroom_router

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Claude 多角色聊天室")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chatroom_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve static files
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))
