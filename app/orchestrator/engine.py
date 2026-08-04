"""Orchestrator — multi-role conversation loop.

Parses the room config, plans the speaker queue, calls Claude per role, and
yields SSE events so the frontend can stream each role's reply in turn.

Roles in the same round run in parallel via a thread pool so a slow role
(e.g. a long Opus thought) doesn't block the rest of the group from
streaming — other roles keep producing deltas while one stalls. Each worker
threads events onto a shared queue; the main generator drains the queue in
arrival order and yields outward. @mention chains still work: when a round
finishes, parsed mentions are merged into the next round's speaker set.
"""
from __future__ import annotations

import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, Future
from queue import Empty, Queue
from threading import Event
from typing import Any

import re

import anthropic

from ..config import get_default_api_key
from .mentions import parse_mentions, strip_mention_prefix
from .room import Message, Role, RoomConfig

_MAX_TURNS = 20
_TOKEN_BUDGET = 190_000  # tokens reserved for history (200K ctx – ~10K overhead)
_ROUND_WORKERS = 8  # cap parallel in-flight Claude calls per round

# Sentinel pushed by each worker when its role finishes — lets the main
# generator know how many workers are still draining events.
_DONE_SENTINEL = ("__done__", None)

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

    Oldest messages are dropped to stay within the token budget, but the
    very first user message is always preserved — losing the opening
    question derails the whole conversation.  After trimming, the result is
    forced to start with a user turn and to alternate strictly user/assistant
    — Anthropic's API rejects consecutive same-role messages.
    """
    api_messages: list[dict[str, Any]] = []
    for msg in history:
        prefix = _speaker_name(msg.name)
        text = f"{prefix}: {msg.content}"
        api_messages.append({"role": msg.role, "content": text})

    # Account for the system prompt too; it shares the same context window.
    total = _estimate_tokens(system)
    for msg in api_messages:
        total += _estimate_tokens(msg["content"])
    # Always keep the first message (the opening user prompt) — drop from
    # index 1 onward when we need to trim.
    drop_from = 1
    while drop_from < len(api_messages) and total > _TOKEN_BUDGET:
        total -= _estimate_tokens(api_messages[drop_from]["content"])
        drop_from += 1
    trimmed = (api_messages[:1] + api_messages[drop_from:]) if api_messages else []

    # Force the first message to be user — Anthropic's API rejects a leading
    # assistant turn.  Trimming can drop enough leading user messages that an
    # assistant message ends up first.
    while trimmed and trimmed[0]["role"] != "user":
        trimmed.pop(0)
    # Collapse consecutive user messages into one (should be rare, but the API
    # rejects them).  Multiple consecutive assistant messages are the normal
    # multi-role pattern — keep them intact.
    alternated: list[dict[str, Any]] = []
    for msg in trimmed:
        if alternated and alternated[-1]["role"] == "user" and msg["role"] == "user":
            alternated[-1] = msg
        else:
            alternated.append(msg)
    return alternated


def orchestrate(
    room: RoomConfig,
    history: list[Message],
    user_msg: str,
    api_key: str | None = None,
    client: anthropic.Anthropic | None = None,
    stop_event: Event | None = None,
) -> Generator[tuple[str, Any], None, None]:
    """Run one user message through the multi-role room and yield SSE events.

    Yielded tuples are (event_name, payload). ``client`` may be reused across
    requests (connection pooling — see chatroom.py for the shared instance);
    ``stop_event``, when set, aborts in-flight Claude calls promptly (used on
    client disconnect).
    """
    key = api_key or get_default_api_key()
    if not key:
        yield ("error", {"message": "No API key configured. Set ANTHROPIC_API_KEY or pass one in the request."})
        yield ("done", None)
        return

    if client is None:
        client = anthropic.Anthropic(
            api_key=key,
            timeout=float(os.environ.get("ANTHROPIC_TIMEOUT", "120")),
        )
    if stop_event is None:
        stop_event = Event()

    queued: list[Role] = _plan_speakers(room)
    spoke: set[str] = {r.name for r in queued}
    turns = 0
    errors: list[str] = []

    try:
        while queued and turns < _MAX_TURNS and not stop_event.is_set():
            round_roles = queued
            queued = []
            turns += len(round_roles)

            evq: Queue[tuple[str, Any]] = Queue()
            with ThreadPoolExecutor(max_workers=min(len(round_roles), _ROUND_WORKERS)) as pool:
                futures: dict[Future[list[Role]], str] = {
                    pool.submit(_run_role, role, room, history, client, evq, stop_event): role.name
                    for role in round_roles
                }
                # Drain shared event queue until every worker has pushed its
                # done-sentinel. FIFO ordering guarantees a worker's text
                # events are consumed before its sentinel. A bounded get()
                # also yields periodic heartbeat frames during slow starts so
                # the async SSE wrapper can observe client disconnects.
                remaining = len(round_roles)
                while remaining > 0:
                    if stop_event.is_set():
                        break
                    try:
                        event, payload = evq.get(timeout=2.0)
                    except Empty:
                        yield ("ping", None)
                        continue
                    if event == "__done__":
                        remaining -= 1
                        continue
                    yield (event, payload)

                # Workers may still be finishing even when stop fired — wait
                # for them so we can collect mentions (and surface errors).
                for fut in futures:
                    try:
                        mentioned = fut.result()
                    except anthropic.AuthenticationError as e:
                        msg = f"{futures[fut]}: API key is invalid — {e}"
                        errors.append(msg)
                        yield ("error", {"message": msg})
                        continue
                    except anthropic.APIError as e:
                        msg = f"{futures[fut]}: Claude API returned an error — {e}"
                        errors.append(msg)
                        # Don't surface raw API errors in SSE to avoid leaking internals
                        yield ("error", {"message": f"{futures[fut]}: 模型调用失败，已跳过"})
                        continue
                    except Exception as e:
                        # Worker-level fallback (network, timeout, JSON decode).
                        msg = f"{futures[fut]}: 流式响应异常 — {e}"
                        errors.append(msg)
                        yield ("error", {"message": msg})
                        continue
                    for m in mentioned:
                        if m.name in spoke:
                            continue
                        queued.append(m)
                        spoke.add(m.name)

            if stop_event.is_set():
                break
    except Exception as e:
        # Top-level safety net (issue #22): a surprise error in _plan_speakers,
        # parse_mentions, system prompt construction, or the queue machinery
        # must still terminate the SSE stream cleanly so the frontend doesn't
        # hang waiting for more frames.
        yield ("error", {"message": f"orchestrate failed: {e}"})

    if errors:
        yield ("error", {"message": f"{len(errors)} 个角色发言失败，已跳过"})

    yield ("done", None)


def _plan_speakers(room: RoomConfig) -> list[Role]:
    """Determine which roles speak for this turn.

    V1: all roles in registration order.  Future versions may parse
    ``group_rules`` to reorder or filter.
    """
    return list(room.roles)


def _run_role(
    role: Role,
    room: RoomConfig,
    history: list[Message],
    client: anthropic.Anthropic,
    evq: Queue[tuple[str, Any]],
    stop_event: Event,
) -> list[Role]:
    """Run one role's full Claude turn, pushing SSE events onto ``evq``.

    Returns the list of roles this reply @mentioned (used to seed the next
    round). Catches per-role exceptions and emits an error event instead of
    propagating — the orchestrate generator translates them into per-role
    SSE errors and the rest of the round continues.
    """
    try:
        system = _build_system_prompt(room, role)
        messages = _format_history(history, system)
        evq.put(("role_start", {"role": role.name}))

        max_tokens = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4096"))
        full_text = ""
        stream_ctx = None
        try:
            stream_ctx = client.messages.stream(
                model=role.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            with stream_ctx as stream:
                for text in stream.text_stream:
                    if stop_event.is_set():
                        # Drops the upstream stream promptly so we stop
                        # consuming billed tokens nobody will read.
                        break
                    full_text += text
                    evq.put(("text", {"role": role.name, "delta": text}))
        except anthropic.APIError:
            # Auth / rate limit / 5xx — let orchestrate distinguish via
            # the future's exception. Re-raise so the typed handler there
            # picks it up.
            raise
        except Exception as e:
            # Network drops, timeouts, decode errors — surface as a
            # per-role SSE error so the rest of the round keeps going.
            evq.put(("error", {"message": f"{role.name}: 流式响应异常 — {e}"}))
        finally:
            if stream_ctx is not None:
                try:
                    stream_ctx.close()
                except Exception:
                    pass

        cleaned = strip_mention_prefix(full_text, room.roles)
        if cleaned:
            history.append(Message(role="assistant", name=role.name, content=cleaned))

        evq.put(("role_end", {"role": role.name}))

        # Parse mentions from this reply only if it actually completed; an
        # aborted/errored reply shouldn't queue more speakers.
        if cleaned and not stop_event.is_set():
            return parse_mentions(cleaned, room.roles)
        return []
    finally:
        evq.put(_DONE_SENTINEL)


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
