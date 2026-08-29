"""Orchestrator — multi-role conversation loop.

Parses the room config, plans the speaker queue, calls Claude per role, and
yields SSE events so the frontend can stream each role's reply in turn.
"""
from __future__ import annotations

import json
import os
from collections.abc import Generator
from typing import Any

import re

import anthropic

from ..config import get_default_api_key
from .mentions import parse_mentions, strip_mention_prefix
from .room import Message, Role, RoomConfig

_MAX_TURNS = 20
_TOKEN_BUDGET = 190_000  # tokens reserved for history (200K ctx – ~10K overhead)

# A character is "CJK" if it falls in any of the common Han/Hangul/Kana ranges.
# Such characters typically tokenize to ~1-2 tokens each, whereas Latin text
# averages ~4 chars/token. Treating CJK like ASCII (len // 3 or len // 4)
# badly underestimates token counts, which risks overflowing the context window
# in long Chinese conversations.
_CJK_PATTERN = re.compile(
    "["
    "\U00004e00-\U00009fff"   # CJK Unified Ideographs
    "\U00003400-\U00004dbf"   # CJK Extension A
    "\U00003000-\U000030ff"   # Hiragana, Katakana, CJK symbols
    "\U0000ac00-\U0000d7af"   # Hangul Syllables
    "\U0000ff00-\U0000ffef"   # Fullwidth forms
    "]"
)


def _speaker_name(role_name: str) -> str:
    """Normalize a role name to a safe prefix string."""
    return role_name.strip()


def _estimate_tokens(text: str) -> int:
    """Estimate tokens counting CJK at ~1.5 tokens/char, ASCII at ~0.25 tokens/char."""
    cjk = len(_CJK_PATTERN.findall(text))
    ascii_ = len(text) - cjk
    return cjk * 2 + ascii_ // 4


def _format_history(
    history: list[Message],
    system: str,
) -> list[dict[str, Any]]:
    """Convert our internal Message list into Anthropic-API messages.

    Each entry is wrapped with a `name: ` prefix inside the content so the
    model can tell who said what.  The system prompt is passed separately.

    Messages with empty content are dropped up front - trimming must not be
    the only thing standing between them and the API (issue #17).

    Oldest messages are dropped to stay within the token budget, but the
    opening user prompt is preserved whenever the budget allows it - losing
    the opening question derails the whole conversation.  Whatever survives
    is normalized to the API's message rules: the first message must be a
    user turn, and consecutive same-role messages are merged into one (the
    API rejects both an assistant-first sequence and non-alternating roles).
    """
    api_messages: list[dict[str, Any]] = []
    for msg in history:
        if not msg.content:
            continue
        prefix = _speaker_name(msg.name)
        text = f"{prefix}: {msg.content}"
        api_messages.append({"role": msg.role, "content": text})

    return _trim_history(api_messages, system)


def _trim_history(
    api_messages: list[dict[str, Any]],
    system: str,
) -> list[dict[str, Any]]:
    """Trim messages to the token budget and normalize for the API."""
    # The API rejects a leading assistant turn, so strip any up front -
    # imported histories can start with assistant messages (issue #17). This
    # runs before the budget math so doomed messages don't eat into the room
    # available for real content.
    while api_messages and api_messages[0]["role"] != "user":
        api_messages.pop(0)
    if not api_messages:
        return []

    # Account for the system prompt too; it shares the same context window.
    total = _estimate_tokens(system)
    for msg in api_messages:
        total += _estimate_tokens(msg["content"])

    # Trim from the oldest messages, preserving the opening user prompt
    # (index 0) whenever the budget allows it - losing the opening question
    # derails the whole conversation. If even the anchor alone exceeds the
    # budget, nothing usable remains.
    drop_from = 1
    while total > _TOKEN_BUDGET and drop_from < len(api_messages):
        total -= _estimate_tokens(api_messages[drop_from]["content"])
        drop_from += 1
    if total > _TOKEN_BUDGET:
        return []
    trimmed = api_messages[:1] + api_messages[drop_from:]

    # Merge consecutive same-role messages into one.  Consecutive assistants
    # are the normal multi-role round shape and consecutive users appear when
    # trimming splits a round; the API rejects both, so join their content -
    # each line keeps its "name: " prefix, so speakers stay distinguishable.
    merged: list[dict[str, Any]] = []
    for msg in trimmed:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] += "\n\n" + msg["content"]
        else:
            merged.append(dict(msg))
    return merged


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

    client = anthropic.Anthropic(api_key=key)

    # The frontend already pushed the user message into `history` before
    # POSTing, so don't append it again here — that would double the user
    # turn and skew every subsequent speaker's context.
    queue: list[Role] = _plan_speakers(room)
    queued_names: set[str] = {r.name for r in queue}
    turns = 0
    errors: list[str] = []

    while queue and turns < _MAX_TURNS:
        role = queue.pop(0)
        queued_names.discard(role.name)
        turns += 1

        try:
            yield from _stream_role(role, room, history, client)
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
            # Don't re-queue the role that just spoke, and don't queue a role
            # already pending — multiple @mentions of the same target before
            # it speaks would otherwise waste redundant calls.
            for m in mentioned:
                if m.name == role.name:
                    continue
                if m.name in queued_names:
                    continue
                queue.append(m)
                queued_names.add(m.name)

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
    client: anthropic.Anthropic,
) -> Generator[tuple[str, Any], None, None]:
    """Stream one role's full turn (Claude call → SSE events)."""
    system = _build_system_prompt(room, role)
    messages = _format_history(history, system)

    yield ("role_start", {"role": role.name})

    max_tokens = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4096"))

    full_text = ""
    stream_error: str | None = None
    try:
        with client.messages.stream(
            model=role.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_text += text
                yield ("text", {"role": role.name, "delta": text})
    except anthropic.APIError:
        # Defer to orchestrate()'s outer handler for Anthropic-origin errors
        # (auth, rate limit, etc.) — those have dedicated messages there.
        raise
    except Exception as e:
        # Catch non-Anthropic exceptions (network drops, timeouts, JSON
        # decode errors) so the entire orchestrate generator doesn't die —
        # other roles can still speak after this one fails.
        stream_error = str(e)
    finally:
        if stream_error:
            yield ("error", {"message": f"{role.name}: 流式响应异常 — {stream_error}"})
        else:
            # Strip only this role's own name echo; a leading mention of
            # another role stays so the chaining loop below can see it.
            cleaned = strip_mention_prefix(full_text, room.roles, speaker=role.name)
            if cleaned:
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
        "以下历史中每条消息以「发言者名: 内容」的形式呈现，请据此辨认谁在说话。",
        "回复时不要带「你的名字: 」前缀，系统会自动补上。",
        "若想 @ 其他角色，请使用 @角色名 形式触发其发言。",
    ]
    return "\n".join(parts)
