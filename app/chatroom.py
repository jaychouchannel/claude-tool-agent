"""POST /api/chatroom/send — SSE-streaming multi-role conversation."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .config import get_default_api_key, get_default_model
from .orchestrator.engine import orchestrate
from .orchestrator.room import Message, Role, RoomConfig

router = APIRouter()


def _serialize(event_name: str, payload: Any) -> str:
    """Translate one (event_name, payload) tuple into SSE wire format."""
    if event_name == "done":
        return "event: done\ndata: null\n\n"
    if event_name == "error":
        return f"event: error\ndata: {json.dumps({'message': payload['message']})}\n\n"
    if event_name == "role_start":
        return f"event: role_start\ndata: {json.dumps({'role': payload['role']})}\n\n"
    if event_name == "role_end":
        return f"event: role_end\ndata: {json.dumps({'role': payload['role']})}\n\n"
    if event_name == "text":
        return f"event: text\ndata: {json.dumps({'role': payload['role'], 'delta': payload['delta']})}\n\n"
    return ""


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
    """Accept { message, room, history?, api_key? } and return an SSE stream."""
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
    api_key = body.get("api_key") or get_default_api_key()

    def event_stream():
        for event_name, payload in orchestrate(room=room, history=history, user_msg=user_msg, api_key=api_key):
            yield _serialize(event_name, payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
