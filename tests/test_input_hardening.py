"""Tests for input hardening: history role validation, ANTHROPIC_MAX_TOKENS
parsing, and the conservative token estimate used for trimming."""
import pytest

from app.chatroom import _parse_history
from app.orchestrator import engine
from app.orchestrator.room import Message


def test_parse_history_drops_non_api_roles():
    # "system"/"tool" roles are rejected by the Anthropic API and would 400
    # every later call mid-conversation; they must not be forwarded.
    out = _parse_history({"history": [
        {"role": "user", "name": "u", "content": "hi"},
        {"role": "system", "name": "x", "content": "inject"},
        {"role": "tool", "name": "t", "content": "data"},
        {"role": "assistant", "name": "a", "content": "hello"},
    ]})
    assert [(m.role, m.content) for m in out] == [("user", "hi"), ("assistant", "hello")]


def test_parse_history_defaults_missing_role_to_user():
    out = _parse_history({"history": [{"name": "u", "content": "hi"}]})
    assert out[0].role == "user"


def test_max_tokens_env_falls_back_on_bad_value(monkeypatch):
    monkeypatch.setattr(engine.os, "environ", {})
    assert engine._max_tokens() == 4096

    monkeypatch.setattr(engine.os, "environ", {"ANTHROPIC_MAX_TOKENS": "8192"})
    assert engine._max_tokens() == 8192

    monkeypatch.setattr(engine.os, "environ", {"ANTHROPIC_MAX_TOKENS": "abc"})
    assert engine._max_tokens() == 4096

    monkeypatch.setattr(engine.os, "environ", {"ANTHROPIC_MAX_TOKENS": "-5"})
    assert engine._max_tokens() == 1


def test_estimate_tokens_is_conservative_for_non_ascii():
    # Emoji are ~1-2 tokens each; counting them like ASCII (//4) badly
    # underestimates emoji-rich conversations.
    assert engine._estimate_tokens("🎉" * 100) >= 200
    assert engine._estimate_tokens("你好世界") == 8
    assert engine._estimate_tokens("abcd") == 1
    assert engine._estimate_tokens("") == 0


def test_estimate_tokens_matches_previous_cjk_behavior():
    # Pure-CJK text keeps its previous ~2 tokens/char estimate.
    text = "汉字测试" * 10
    assert engine._estimate_tokens(text) == len(text) * 2
