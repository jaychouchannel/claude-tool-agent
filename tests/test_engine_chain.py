from __future__ import annotations

import anthropic

from app.orchestrator.engine import orchestrate
from app.orchestrator.mentions import strip_mention_prefix
from app.orchestrator.room import Message, Role, RoomConfig


def _roles() -> list[Role]:
    return [
        Role(name="研究员", system_prompt="研究员设定", model="fake"),
        Role(name="代码手", system_prompt="代码手设定", model="fake"),
    ]


def test_strip_strips_only_speaker_echo():
    roles = _roles()
    # 回复开头 @ 别人：必须原样保留，这是链式发言的触发信号
    assert strip_mention_prefix("@研究员，你怎么看？", roles, speaker="代码手") == "@研究员，你怎么看？"
    # 自己的自报前缀：剥掉，连同紧邻标点
    assert strip_mention_prefix("@代码手：我的思路如下", roles, speaker="代码手") == "我的思路如下"
    # 兼容：不传 speaker 时保持旧行为
    assert strip_mention_prefix("@代码手：hi", roles) == "hi"


def test_reply_opening_with_mention_chains(monkeypatch):
    """回复第一句就 @ 下一位发言者时，链式排队不能断。"""

    class _FakeStream:
        def __init__(self, text):
            self.text = text

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def text_stream(self):
            yield self.text

    script = {
        "研究员": ["收到。", "补充：数据侧风险可控。"],
        "代码手": ["@研究员，请补充你的看法。"],
    }

    class _FakeMessages:
        def stream(self, model=None, max_tokens=None, system=None, messages=None):
            key = "研究员" if "研究员设定" in (system or "") else "代码手"
            return _FakeStream(script[key].pop(0))

    class _FakeClient:
        def __init__(self, **kwargs):
            self.messages = _FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)

    room = RoomConfig(room_id="t", roles=_roles(), group_rules="")
    history = [Message(role="user", name="用户", content="讨论一下")]
    events = list(orchestrate(room=room, history=history, user_msg="讨论一下", api_key="k"))

    # 代码手开口 @ 了研究员，研究员必须在说完一轮后被重新排队
    speakers = [p["role"] for e, p in events if e == "role_start"]
    assert speakers == ["研究员", "代码手", "研究员"]

    # 代码手回复开头的 @研究员 原样进入历史，没有被截出孤立标点
    b_msg = [m for m in history if m.name == "代码手"][0]
    assert b_msg.content == "@研究员，请补充你的看法。"
