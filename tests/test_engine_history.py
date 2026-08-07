"""Tests for _format_history — the messages we send to the Anthropic API.

Covers issues #12 and #17: trimming must never produce a sequence the API
rejects (assistant-first, or consecutive same-role messages), and the
opening user prompt must survive trimming whenever the budget allows.
"""
import random

import pytest

from app.orchestrator import engine
from app.orchestrator.room import Message


def M(role, name, content):
    return Message(role=role, name=name, content=content)


def assert_api_valid(messages, opening_kept=None):
    """Assert a message list satisfies the Anthropic API's message rules."""
    for msg in messages:
        assert msg["content"], "empty message content would be rejected"
    if not messages:
        return
    assert messages[0]["role"] == "user", "first message must be a user turn"
    for prev, cur in zip(messages, messages[1:]):
        assert prev["role"] != cur["role"], "roles must strictly alternate"
    if opening_kept is not None:
        assert messages[0]["content"] == f"用户: {opening_kept}"


def test_simple_alternating_history_passes_through():
    history = [M("user", "用户", "hello"), M("assistant", "研究员", "hi")]
    out = engine._format_history(history, "")
    assert_api_valid(out)
    assert out == [
        {"role": "user", "content": "用户: hello"},
        {"role": "assistant", "content": "研究员: hi"},
    ]


def test_leading_assistant_messages_are_dropped():
    # Imported histories may start with assistant turns (issue #17).
    history = [
        M("assistant", "研究员", "monologue"),
        M("user", "用户", "hello"),
        M("assistant", "代码手", "hi"),
    ]
    out = engine._format_history(history, "")
    assert_api_valid(out)
    assert out[0] == {"role": "user", "content": "用户: hello"}


def test_all_assistant_history_yields_empty():
    history = [M("assistant", "研究员", "a"), M("assistant", "代码手", "b")]
    assert engine._format_history(history, "") == []


def test_empty_history_yields_empty():
    assert engine._format_history([], "") == []


def test_empty_content_messages_are_dropped():
    # An empty leading user message (issue #17's edge case) must not skew
    # the budget math or reach the API.
    history = [
        M("user", "用户", ""),
        M("assistant", "研究员", "a"),
        M("user", "用户", "real question"),
        M("assistant", "代码手", "b"),
    ]
    out = engine._format_history(history, "")
    assert_api_valid(out)
    assert out[0] == {"role": "user", "content": "用户: real question"}


def test_multi_role_round_keeps_all_speakers():
    # Several assistants per user turn is the normal multi-role shape — they
    # get merged into one assistant turn but every speaker stays visible.
    history = [
        M("user", "用户", "q"),
        M("assistant", "研究员", "r1"),
        M("assistant", "代码手", "r2"),
        M("assistant", "创意家", "r3"),
    ]
    out = engine._format_history(history, "")
    assert_api_valid(out)
    assert len(out) == 2
    assert "研究员: r1" in out[1]["content"]
    assert "代码手: r2" in out[1]["content"]
    assert "创意家: r3" in out[1]["content"]


def test_over_budget_trim_keeps_opening_user_and_alternates(monkeypatch):
    # Issue #12's repro: 3 assistant roles per round, trimmed mid-round.
    monkeypatch.setattr(engine, "_TOKEN_BUDGET", 100)
    history = []
    for turn in range(2):
        history.append(M("user", "用户", f"q{turn}" + "x" * 100))
        for role in ("研究员", "代码手", "创意家"):
            history.append(M("assistant", role, f"a{turn}" + "x" * 100))
    out = engine._format_history(history, "system prompt")
    assert_api_valid(out, opening_kept="q0" + "x" * 100)


def test_over_budget_trim_never_breaks_alternation_stress(monkeypatch):
    # Random user/assistant sequences at a range of budgets must always come
    # out API-valid.
    rng = random.Random(42)
    for budget in (0, 50, 200, 10_000):
        monkeypatch.setattr(engine, "_TOKEN_BUDGET", budget)
        for _ in range(50):
            history = [
                M(rng.choice(["user", "assistant"]), f"角色{i}", "w" * rng.randint(1, 80))
                for i in range(rng.randint(0, 20))
            ]
            assert_api_valid(engine._format_history(history, "sys" * 5))


def test_opening_message_alone_over_budget_yields_empty(monkeypatch):
    # Nothing fits — returning the giant opening message alone would still
    # overflow, so prefer an honest empty result over a request the API
    # rejects on context size.
    monkeypatch.setattr(engine, "_TOKEN_BUDGET", 10)
    history = [M("user", "用户", "x" * 400), M("assistant", "研究员", "y" * 400)]
    assert engine._format_history(history, "") == []


def test_system_prompt_counts_against_budget(monkeypatch):
    # A big system prompt leaves less room for history (issue #12's token
    # budget includes the system prompt). With no system prompt both messages
    # fit; a large one forces the assistant reply to be dropped.
    monkeypatch.setattr(engine, "_TOKEN_BUDGET", 250)
    history = [
        M("user", "用户", "q" + "x" * 100),
        M("assistant", "研究员", "a" + "x" * 100),
    ]
    small_system = engine._format_history(history, "")
    big_system = engine._format_history(history, "s" * 800)
    assert len(small_system) == 2
    assert_api_valid(big_system)
    assert len(big_system) == 1  # only the opening user prompt survives
