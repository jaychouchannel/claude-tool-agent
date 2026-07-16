"""Orchestrator — multi-role conversation loop.

Parses the room config, plans the speaker queue, calls Claude per role, and
yields SSE events so the frontend can stream each role's reply in turn.
"""
from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import anthropic

from ..config import get_default_api_key
from .mentions import parse_mentions, strip_mention_prefix
from .room import Message, Role, RoomConfig

_MAX_TURNS = 20


def _speaker_name(role_name: str) -> str:
    """Normalize a role name to a safe prefix string."""
    return role_name.strip()


def _format_history(
    history: list[Message],
    system: str,
) -> list[dict[str, Any]]:
    """Convert our internal Message list into Anthropic-API messages.

    Each entry is wrapped with a `[name]: ` prefix inside the content so the
    model can tell who said what.  The system prompt is passed separately.
    """
    api_messages: list[dict[str, Any]] = []
    for msg in history:
        prefix = _speaker_name(msg.name)
        text = f"{prefix}: {msg.content}"
        api_messages.append({"role": msg.role, "content": text})
    return api_messages


def orchestrate(
    room: RoomConfig,
    history: list[Message],
    user_msg: str,
    api_key: str | None = None,
) -> Generator[tuple[str, Any], None, None]:
    """Run one user message through the multi-role room and yield SSE events.

    Yielded tuples are (event_name, payload) — see the SSE protocol below.
    """
    key = api_key or get_default_api_key()
    if not key:
        yield ("error", {"message": "No API key configured. Set ANTHROPIC_API_KEY or pass one in the request."})
        yield ("done", None)
        return

    history.append(Message(role="user", name="用户", content=user_msg))

    queue: list[Role] = _plan_speakers(room)
    turns = 0
    errors: list[str] = []

    while queue and turns < _MAX_TURNS:
        role = queue.pop(0)
        turns += 1

        try:
            yield from _stream_role(role, room, history, key)
        except anthropic.AuthenticationError as e:
            msg = f"{role.name}: API key is invalid — {e}"
            errors.append(msg)
            yield ("error", {"message": msg})
            continue
        except anthropic.APIError as e:
            msg = f"{role.name}: Claude API returned an error — {e}"
            # Don't surface raw API errors in SSE to avoid leaking internals
            errors.append(msg)
            yield ("error", {"message": f"{role.name}: 模型调用失败，已跳过"})
            continue

        # After the role has spoken, check if it @mentioned anyone
        if history:
            last = history[-1]
            mentioned = parse_mentions(last.content, room.roles)
            # Don't re-queue the role that just spoke
            for m in mentioned:
                if m.name != role.name:
                    queue.append(m)

    if errors:
        yield ("error", {"message": f"{len(errors)} 个角色发言失败，已跳过"})

    yield ("done", None)


def _plan_speakers(room: RoomConfig) -> list[Role]:
    """Determine which roles speak for this turn.

    V1: all roles in registration order.  Future versions may parse
    ``group_rules`` to reorder or filter.
    """
    return list(room.roles)


def _stream_role(
    role: Role,
    room: RoomConfig,
    history: list[Message],
    api_key: str,
) -> Generator[tuple[str, Any], None, None]:
    """Stream one role's full turn (Claude call → SSE events)."""
    system = _build_system_prompt(room, role)
    messages = _format_history(history, system)

    yield ("role_start", {"role": role.name})

    client = anthropic.Anthropic(api_key=api_key)
    full_text = ""
    with client.messages.stream(
        model=role.model,
        max_tokens=2048,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            full_text += text
            yield ("text", {"role": role.name, "delta": text})

    # Strip leading @mention the model may have prefixed
    cleaned = strip_mention_prefix(full_text, room.roles)

    history.append(Message(role="assistant", name=role.name, content=cleaned))

    yield ("role_end", {"role": role.name})


def _build_system_prompt(room: RoomConfig, role: Role) -> str:
    """Build the system prompt combining group rules + role personality."""
    parts = [
        "# 群公告（所有角色共同遵循）",
        room.group_rules or "（无特殊规则）",
        "",
        "# 你的发言设定",
        role.system_prompt,
        "",
        "# 当前对话历史中的发言者",
        "以下历史中每条消息带 [发言者名] 前缀，请辨认谁在说话。",
        "回复时不要带 [你的名字] 前缀，系统会自动加上。",
        "若想 @ 其他角色，请使用 @角色名 形式触发其发言。",
    ]
    return "\n".join(parts)
