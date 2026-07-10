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

try:
    from .langchain_agent import chat as langchain_chat
except ImportError:
    langchain_chat = None

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


def _serialize_event(event_name: str, payload: Any) -> str:
    """Translate one (event_name, payload) tuple from the agent generator into SSE wire format."""
    if event_name == "done":
        return "event: done\ndata: null\n\n"
    if event_name == "error":
        data = json.dumps({"message": payload})
        return f"event: error\ndata: {data}\n\n"
    if event_name == "text":
        data = json.dumps({"text": payload})
        return f"event: text\ndata: {data}\n\n"
    if event_name == "tool_use":
        data = json.dumps({
            "id": payload["id"],
            "name": payload["name"],
            "input": payload["input"],
        })
        return f"event: tool_use\ndata: {data}\n\n"
    if event_name == "tool_result":
        data = json.dumps({
            "id": payload["id"],
            "name": payload["name"],
            "output": payload["output"],
        })
        return f"event: tool_result\ndata: {data}\n\n"
    return ""


def _build_messages(body: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Shared request parsing for both chat endpoints. Returns (messages, error)."""
    user_msg = body.get("message", "").strip()
    if not user_msg:
        return [], "message is empty"

    history: list[dict[str, Any]] = body.get("history") or []
    messages: list[dict[str, Any]] = []
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_msg})
    return messages, None


def _resolve_api_key(body: dict[str, Any]) -> tuple[str | None, str | None]:
    """Returns (api_key, error_message). Error_message is None when key is available."""
    api_key = body.get("api_key") or get_default_api_key()
    if not api_key:
        return None, (
            "No API key provided. "
            "Set ANTHROPIC_API_KEY in your environment or "
            "click the gear icon and paste your key."
        )
    return api_key, None


@app.post("/api/chat")
async def chat_stream(request: Request):
    """Accept { message, api_key?, history? } and return an SSE stream (native agent)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    messages, msg_err = _build_messages(body)
    if msg_err:
        return JSONResponse({"error": msg_err}, status_code=400)

    api_key, key_err = _resolve_api_key(body)
    if key_err:
        return JSONResponse({"error": key_err}, status_code=401)

    def event_stream():
        for event_name, payload in chat(api_key=api_key, messages=messages):
            yield _serialize_event(event_name, payload)

    return _sse_response(event_stream)


@app.post("/api/chat/langchain")
async def chat_stream_langchain(request: Request):
    """Same contract as /api/chat but backed by the LangChain + langchain-anthropic agent."""
    if langchain_chat is None:
        return JSONResponse(
            {
                "error": (
                    "LangChain dependencies are not installed. "
                    "Run `pip install langchain langchain-anthropic`."
                )
            },
            status_code=503,
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    messages, msg_err = _build_messages(body)
    if msg_err:
        return JSONResponse({"error": msg_err}, status_code=400)

    api_key, key_err = _resolve_api_key(body)
    if key_err:
        return JSONResponse({"error": key_err}, status_code=401)

    def event_stream():
        for event_name, payload in langchain_chat(api_key=api_key, messages=messages):
            yield _serialize_event(event_name, payload)

    return _sse_response(event_stream)


def _sse_response(event_stream):
    return StreamingResponse(
        event_stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
