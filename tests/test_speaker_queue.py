"""Regression tests for the orchestrate() speaker queue.

These pin down the stale-history mention bug: when a turn produces no
appended reply (stream failure or an empty / mention-only response),
orchestrate() must not re-parse history[-1] for @mentions — doing so
re-queues roles that already spoke and ping-pongs until _MAX_TURNS,
burning API calls on duplicate turns.
"""
from app.orchestrator import engine
from app.orchestrator.room import Message, Role, RoomConfig


class _FakeStream:
    def __init__(self, chunks=(), error=None):
        self._chunks = chunks
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        if self._error is not None:
            raise self._error
        return iter(self._chunks)


def _fake_anthropic(script):
    """Build a fake ``anthropic.Anthropic`` whose streams follow ``script``.

    ``script`` is a list of zero-arg callables returning _FakeStream; the
    last entry repeats once exhausted. Returns (class, calls_list).
    """
    calls = []

    class _Messages:
        def stream(self, **kwargs):
            idx = min(len(calls), len(script) - 1)
            calls.append(idx)
            return script[idx]()

    class _Client:
        def __init__(self, api_key=None):
            self.messages = _Messages()

    return _Client, calls


def _room(*names):
    return RoomConfig(
        room_id="r",
        roles=[Role(name=n, system_prompt="s", model="m") for n in names],
        group_rules="",
    )


def _run(monkeypatch, client_cls, history):
    monkeypatch.setattr(engine.anthropic, "Anthropic", client_cls)
    events = list(engine.orchestrate(room=_room("研究员", "代码手", "创意家"), history=history, user_msg="x", api_key="k"))
    return events


def test_empty_replies_do_not_ping_pong_until_max_turns(monkeypatch):
    # Every role answers empty -> nothing is appended. The old code kept
    # re-parsing the mention-bearing USER message, re-queueing spoken roles
    # and looping until _MAX_TURNS (20 API calls for 2 roles).
    client_cls, calls = _fake_anthropic([lambda: _FakeStream(chunks=[""])])
    history = [Message(role="user", name="用户", content="@研究员 @代码手 打个招呼")]

    room = _room("研究员", "代码手")
    monkeypatch.setattr(engine.anthropic, "Anthropic", client_cls)
    list(engine.orchestrate(room=room, history=history, user_msg="x", api_key="k"))

    assert len(calls) == 2, f"expected 2 speaker turns, got {len(calls)}"


def test_trailing_stream_failures_do_not_requeue_spoken_roles(monkeypatch):
    # First speaker succeeds and mentions the other two; both then fail with
    # a network error. The old code re-parsed the first reply after EACH
    # failure, resurrecting already-failed / spoken roles up to _MAX_TURNS.
    script = [
        lambda: _FakeStream(chunks=["请 @代码手 和 @创意家 发言"]),
        lambda: _FakeStream(error=ConnectionError("boom")),
        lambda: _FakeStream(error=ConnectionError("boom")),
    ]
    client_cls, calls = _fake_anthropic(script)
    history = [Message(role="user", name="用户", content="@代码手 @创意家 聊聊")]

    _run(monkeypatch, client_cls, history)

    assert len(calls) == 3, f"expected 3 speaker attempts, got {len(calls)}"


def test_successful_mention_still_queues_pending_role(monkeypatch):
    # Guard the intended behavior: a fresh reply that @mentions someone who
    # has not spoken yet must still queue them.
    script = [
        lambda: _FakeStream(chunks=["请 @创意家 接棒"]),
        lambda: _FakeStream(chunks=["收到"]),
    ]
    client_cls, calls = _fake_anthropic(script)
    history = [Message(role="user", name="用户", content="聊聊")]

    starts = [
        payload["role"]
        for name, payload in _run(monkeypatch, client_cls, history)
        if name == "role_start"
    ]

    assert len(calls) == 3
    assert starts == ["研究员", "代码手", "创意家"]
