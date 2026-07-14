"""Alternative agent implementation built on LangChain + langchain-anthropic.

Mirrors `app/agent.py`'s SSE event contract (`text`, `tool_use`, `tool_result`, `error`, `done`)
so the same frontend can drive either endpoint.

Why a second implementation? The native `agent.py` is a tight, hand-rolled loop that shows
the bare Anthropic tool-use API. This module is the same idea expressed with LangChain's
`create_react_agent` + `ChatAnthropic` — useful for comparing the two idioms.
"""
from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from .config import MAX_ITERATIONS, get_model
from .tools import REGISTRY, get_tool_specs

# LangChain imports are local so the native endpoint keeps zero LangChain deps.
# Anything goes wrong here → the `/api/chat/langchain` route surfaces that cleanly,
# while `/api/chat` stays untouched.
try:
    from langchain_anthropic import ChatAnthropic
    from langgraph.prebuilt import create_react_agent
    from langchain_core.tools import StructuredTool
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    from pydantic import BaseModel, ValidationError
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "LangChain dependencies are not installed. "
        "Run `pip install langchain langchain-anthropic langgraph` to enable /api/chat/langchain."
    ) from e


SYSTEM_PROMPT = (
    "You are a helpful AI assistant with access to tools. "
    "Always use tools when they can help answer the user's question. "
    "After using a tool, summarise the results for the user in a concise, helpful way."
)


def _spec_to_pydantic(spec: dict[str, Any]) -> type[BaseModel]:
    """Convert an Anthropic-style tool input_schema into a Pydantic model.

    LangChain's `StructuredTool` expects a Pydantic class; Anthropic's tool spec
    uses raw JSON-schema dicts. We translate field-by-field for the simple shapes
    this project's tools actually use (string / integer / boolean / number).

    Pydantic v2 requires real type annotations on the class namespace — building
    fields as `(type, default)` tuples via `type(...)` doesn't work. We build a
    proper `__annotations__` mapping and use `Field(...)` for required fields.
    """
    from pydantic import Field

    props = spec.get("input_schema", {}).get("properties", {})
    required = set(spec.get("input_schema", {}).get("required", []))

    annotations: dict[str, type] = {}
    namespace: dict[str, Any] = {"__annotations__": annotations}
    for name, schema in props.items():
        json_type = schema.get("type", "string")
        if json_type == "integer":
            py_type: type = int
        elif json_type == "number":
            py_type = float
        elif json_type == "boolean":
            py_type = bool
        else:
            py_type = str

        description = schema.get("description", "")
        annotations[name] = py_type
        if name in required:
            namespace[name] = Field(..., description=description)
        else:
            default = schema.get("default")
            namespace[name] = Field(default, description=description)

    return type(f"{spec['name']}_Args", (BaseModel,), namespace)


def _build_tools() -> list[StructuredTool]:
    """Wrap each native tool as a LangChain StructuredTool bound to its TOOL_SPEC."""
    tools: list[StructuredTool] = []
    for spec in get_tool_specs():
        name = spec["name"]
        fn = REGISTRY[name]
        args_model = _spec_to_pydantic(spec)

        def _runner(_name: str = name, _fn=fn, **kwargs: Any) -> str:
            return _fn(**kwargs)

        tools.append(
            StructuredTool.from_function(
                _runner,
                name=name,
                description=spec.get("description", ""),
                args_schema=args_model,
            )
        )
    return tools


def _strip_pydantic_v2_validation_error(err: ValidationError) -> str:
    """Compact a pydantic v2 ValidationError into a one-line message for SSE."""
    try:
        first = err.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        return f"{loc}: {first.get('msg', 'invalid')}"
    except Exception:
        return str(err)


def chat(
    api_key: str,
    messages: list[dict[str, Any]],
) -> Generator[tuple[str, Any], None, None]:
    """LangChain version of the agent loop. Same SSE contract as `app/agent.py:chat`."""
    model = ChatAnthropic(
        model=get_model(),
        api_key=api_key,
        max_tokens=4096,
        timeout=60,
        stop=None,
    )
    tools = _build_tools()

    try:
        agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)
    except Exception as e:
        yield ("error", f"Failed to build LangChain agent: {e}")
        yield ("done", None)
        return

    # Translate our {role, content} history into LangChain's message types.
    # The ReAct agent graph takes its prior turns as the `messages` state key.
    lc_messages: list[Any] = []
    for turn in messages:
        role = turn.get("role")
        content = turn.get("content", "")
        if isinstance(content, list):
            # Anthropic-style content blocks (text / tool_use / tool_result).
            # The native endpoint stores raw blocks sometimes; collapse to text
            # since the LangChain ReAct graph doesn't replay tool history here.
            content = json.dumps(content, default=str)
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))

    try:
        result = agent.invoke(
            {"messages": lc_messages},
            config={"recursion_limit": MAX_ITERATIONS * 4},
        )
    except Exception as e:
        yield ("error", f"LangChain agent error: {e}")
        yield ("done", None)
        return

    # `create_react_agent` returns state with a `messages` list mixing
    # AIMessage (text + tool_calls), ToolMessage (tool outputs), and a final
    # AIMessage with the assistant's summary. Walk that list in order and emit
    # tool_use / tool_result events as the UI expects, then the trailing text.
    final_text = ""
    for msg in result.get("messages", []):
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            for call in tool_calls:
                yield ("tool_use", {
                    "id": call.get("id", "") if isinstance(call, dict) else getattr(call, "id", ""),
                    "name": call.get("name", "") if isinstance(call, dict) else getattr(call, "name", ""),
                    "input": call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {}),
                })
        # ToolMessage carries the tool's output.
        if getattr(msg, "type", None) == "tool" or "ToolMessage" in type(msg).__name__:
            yield ("tool_result", {
                "id": getattr(msg, "tool_call_id", ""),
                "name": getattr(msg, "name", "") or getattr(msg, "tool_name", ""),
                "output": str(getattr(msg, "content", "")),
            })
        # Trailing AIMessage text becomes the SSE `text` event.
        if isinstance(msg, AIMessage) and not tool_calls:
            content_str = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, default=str)
            if content_str:
                final_text = content_str

    if final_text:
        yield ("text", final_text)

    yield ("done", None)
