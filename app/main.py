"""FastAPI app — serves the UI and the /api/chat SSE endpoint."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from .agent import chat
from .config import get_default_api_key

app = FastAPI(title="Claude Tool-Use Agent Demo")

# Serve /static/* if the directory exists (e.g. for extra assets)
_static = Path(__file__).resolve().parent.parent / "static"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")

_INDEX_HTML = (_static / "index.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def index():
    return _INDEX_HTML


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat_stream(request: Request):
    """Accept { message, api_key?, history? } and return an SSE stream."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    user_msg = body.get("message", "").strip()
    if not user_msg:
        return JSONResponse({"error": "message is empty"}, status_code=400)

    # Resolve API key: request body → env
    api_key = body.get("api_key") or get_default_api_key()
    if not api_key:
        return JSONResponse(
            {
                "error": (
                    "No API key provided. "
                    "Set ANTHROPIC_API_KEY in your environment or "
                    "click the gear icon and paste your key."
                )
            },
            status_code=401,
        )

    # Build message list from client history
    history: list[dict[str, Any]] = body.get("history") or []
    messages: list[dict[str, Any]] = []
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_msg})

    def event_stream():
        for event_name, payload in chat(api_key=api_key, messages=messages):
            if event_name == "done":
                yield f"event: done\ndata: null\n\n"
            elif event_name == "error":
                data = json.dumps({"message": payload})
                yield f"event: error\ndata: {data}\n\n"
            elif event_name == "text":
                data = json.dumps({"text": payload})
                yield f"event: text\ndata: {data}\n\n"
            elif event_name == "tool_use":
                data = json.dumps(
                    {
                        "id": payload["id"],
                        "name": payload["name"],
                        "input": payload["input"],
                    }
                )
                yield f"event: tool_use\ndata: {data}\n\n"
            elif event_name == "tool_result":
                data = json.dumps(
                    {
                        "id": payload["id"],
                        "name": payload["name"],
                        "output": payload["output"],
                    }
                )
                yield f"event: tool_result\ndata: {data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
