from __future__ import annotations

from app.orchestrator.mentions import parse_mentions
from app.orchestrator.room import Role


def role(name: str) -> Role:
    return Role(name=name, system_prompt="", model="x")


PRESET = [role(n) for n in ["研究员", "代码手", "创意家", "评论家", "编剧", "历史学家"]]


def test_cjk_text_glued_to_mention_is_matched():
    # @研究员你好 used to miss because 你 is a \w character in Unicode mode.
    assert parse_mentions("@研究员你好", PRESET) == [PRESET[0]]


def test_full_width_punctuation_boundary_still_matches():
    assert parse_mentions("@研究员，你好", PRESET) == [PRESET[0]]


def test_mention_at_end_of_string():
    assert parse_mentions("@历史学家", PRESET) == [PRESET[5]]


def test_no_match_inside_ascii_word():
    roles = [role("bot")]
    assert parse_mentions("@botman hello", roles) == []
    assert parse_mentions("email bot@example.com", roles) == []


def test_longer_name_wins_over_prefix():
    roles = [role("翻译"), role("翻译社")]
    assert parse_mentions("@翻译社帮忙", roles) == [roles[1]]


def test_dedup_and_multiple_mentions():
    result = parse_mentions("@研究员 @代码手 @研究员", PRESET)
    assert result == [PRESET[0], PRESET[1]]


def test_mentions_follow_text_order():
    roles = [role("甲"), role("乙")]
    assert parse_mentions("@乙 你好 @甲", roles) == [roles[1], roles[0]]


def test_no_roles():
    assert parse_mentions("@研究员", []) == []
