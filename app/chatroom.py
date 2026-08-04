"""POST /api/chatroom/send — SSE-streaming multi-role conversation."""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import anthropic
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .config import get_default_api_key, get_default_model
from .orchestrator.engine import orchestrate
from .orchestrator.room import Message, Role, RoomConfig

router = APIRouter()

# One Anthropic client per API key, shared across requests — the underlying
# httpx connection pool is kept warm (`connection: keep-alive`) so concurrent
# sends don't each tear down and reopen a fresh TCP socket. A different key
# (per-request override) gets its own client so connection reuse never leaks
# credentials across keys.
_shared_client: anthropic.Anthropic | None = None
_shared_client_key: str | None = None


def _client_for(api_key: str | None) -> anthropic.Anthropic:
    global _shared_client, _shared_client_key
    key = api_key or get_default_api_key() or ""
    if _shared_client is None or _shared_client_key != key:
        _shared_client = anthropic.Anthropic(api_key=key, timeout=30.0)
        _shared_client_key = key
    return _shared_client


def _serialize(event_name: str, payload: Any) -> str:
    """Translate one (event_name, payload) tuple into SSE wire format."""
    if event_name == "done":
        # json.dumps(None) yields the JSON literal "null", consistent with
        # every other event. Rendering raw "null" was fragile — proxies/CDNs
        # that chunk mid-frame could reconstruct a corrupted data line.
        return f"event: done\ndata: {json.dumps(None)}\n\n"
    if event_name == "error":
        return f"event: error\ndata: {json.dumps({'message': payload['message']})}\n\n"
    if event_name == "role_start":
        return f"event: role_start\ndata: {json.dumps({'role': payload['role']})}\n\n"
    if event_name == "role_end":
        return f"event: role_end\ndata: {json.dumps({'role': payload['role']})}\n\n"
    if event_name == "text":
        return f"event: text\ndata: {json.dumps({'role': payload['role'], 'delta': payload['delta']})}\n\n"
    if event_name == "ping":
        # SSE comment frame — ignored by all clients and proxies.
        # Used as a heartbeat so the async wrapper can detect client
        # disconnects during slow first-token waits. Trailing blank line
        # terminates the frame so the frontend splitter sees it complete.
        return ":\n\n"


def _parse_room(body: dict[str, Any]) -> RoomConfig | str:
    """Extract RoomConfig from request body; return error string on failure."""
    raw = body.get("room")
    if not raw:
        return "room config is required"
    try:
        default_model = get_default_model()
        roles = [
            Role(name=r["name"], system_prompt=r["system_prompt"], model=r.get("model", default_model))
            for r in raw.get("roles", [])
        ]
        if not roles:
            return "at least one role is required"
        # Combine announcement (group notice) and free-form group rules into the
        # single system-prompt field used downstream. Either may be absent.
        announcement = (raw.get("announcement") or "").strip()
        group_rules = (raw.get("group_rules") or "").strip()
        combined: str
        if announcement and group_rules:
            combined = f"【群公告】\n{announcement}\n\n【补充规则】\n{group_rules}"
        elif announcement:
            combined = f"【群公告】\n{announcement}"
        else:
            combined = group_rules
        return RoomConfig(
            room_id=raw.get("room_id", "default"),
            roles=roles,
            group_rules=combined,
        )
    except (KeyError, TypeError) as e:
        return f"invalid room config: {e}"


def _parse_history(body: dict[str, Any]) -> list[Message]:
    raw = body.get("history") or []
    messages: list[Message] = []
    for h in raw:
        messages.append(Message(role=h.get("role", "user"), name=h.get("name", "用户"), content=h.get("content", "")))
    return messages


@router.post("/api/chatroom/send")
async def chatroom_send(request: Request):
    """Accept { message, room, history?, api_key? } and return an SSE stream.

    API key resolution order: Authorization: Bearer <key> header → body.api_key
    → ANTHROPIC_API_KEY env var.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    user_msg = body.get("message", "").strip()
    if not user_msg:
        return JSONResponse({"error": "message is empty"}, status_code=400)

    room = _parse_room(body)
    if isinstance(room, str):
        return JSONResponse({"error": room}, status_code=400)

    history = _parse_history(body)
    api_key = _extract_api_key(request, body)

    async def event_stream():
        # Run the (blocking, sync) orchestrate generator on a worker thread so
        # its long evq.get() waits don't stall the event loop; bridge events
        # back via an asyncio.Queue. Disconnect is observed on the loop and
        # signals orchestrate's stop_event (issue #23).
        loop = asyncio.get_running_loop()
        aq: asyncio.Queue = asyncio.Queue()
        stop_event = threading.Event()

        def produce():
            try:
                for event_name, payload in orchestrate(
                    room=room,
                    history=history,
                    user_msg=user_msg,
                    api_key=api_key,
                    client=_client_for(api_key),
                    stop_event=stop_event,
                ):
                    loop.call_soon_threadsafe(aq.put_nowait, (event_name, payload))
            except Exception as e:
                loop.call_soon_threadsafe(aq.put_nowait, ("error", {"message": f"orchestrate crashed: {e}"}))
            finally:
                loop.call_soon_threadsafe(aq.put_nowait, ("__done__", None))

        thread = threading.Thread(target=produce, daemon=True)
        thread.start()

        try:
            while True:
                event_name, payload = await aq.get()
                if event_name == "__done__":
                    break
                if await request.is_disconnected():
                    stop_event.set()
                    yield _serialize(event_name, payload)
                    break
                yield _serialize(event_name, payload)
        finally:
            stop_event.set()
            # Don't block shutdown on a wedged upstream call — leave the
            # producer thread to wind down on its own.

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _extract_api_key(request: Request, body: dict[str, Any]) -> str | None:
    """Prefer Authorization: Bearer <key>; fall back to body.api_key for backward compat."""
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    return body.get("api_key") or get_default_api_key()
