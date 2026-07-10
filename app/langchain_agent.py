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
    from langchain.agents import create_react_agent, AgentExecutor
    from langchain_core.tools import StructuredTool
    from langchain_core.messages import HumanMessage, AIMessage
    from pydantic import BaseModel, ValidationError
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "LangChain dependencies are not installed. "
        "Run `pip install langchain langchain-anthropic` to enable /api/chat/langchain."
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
    """
    props = spec.get("input_schema", {}).get("properties", {})
    required = set(spec.get("input_schema", {}).get("required", []))

    fields: dict[str, Any] = {}
    for name, schema in props.items():
        py_type: type
        json_type = schema.get("type", "string")
        if json_type == "integer":
            py_type = int
        elif json_type == "number":
            py_type = float
        elif json_type == "boolean":
            py_type = bool
        else:
            py_type = str

        description = schema.get("description", "")
        if name in required:
            fields[name] = (py_type, ...)
        else:
            default = schema.get("default")
            fields[name] = (py_type, default)

    return type(f"{spec['name']}_Args", (BaseModel,), fields)


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
        agent = create_react_agent(model, tools)
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            max_iterations=MAX_ITERATIONS,
            return_intermediate_steps=True,
            handle_parsing_errors=True,
        )
    except Exception as e:
        yield ("error", f"Failed to build LangChain agent: {e}")
        yield ("done", None)
        return

    # Translate our {role, content} history into LangChain's message types.
    lc_messages: list[Any] = []
    for turn in messages:
        role = turn.get("role")
        content = turn.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content if isinstance(content, str) else json.dumps(content)))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content if isinstance(content, str) else json.dumps(content)))

    try:
        result = executor.invoke(
            {"input": lc_messages[-1].content if lc_messages else ""},
            config={"recursion_limit": MAX_ITERATIONS * 4},
        )
    except Exception as e:
        yield ("error", f"LangChain agent error: {e}")
        yield ("done", None)
        return

    # Re-emit intermediate steps as tool_use / tool_result events so the UI
    # renders the same cards as the native endpoint.
    for action, observation in result.get("intermediate_steps", []):
        tool_name = getattr(action, "tool", str(action))
        tool_input = getattr(tool_action_input := getattr(action, "tool_input", None), "model_dump", lambda: tool_action_input)()
        if callable(tool_input):
            tool_input = tool_input()
        yield ("tool_use", {"id": getattr(action, "tool_call_id", ""), "name": tool_name, "input": tool_input})
        yield ("tool_result", {
            "id": getattr(action, "tool_call_id", ""),
            "name": tool_name,
            "output": str(observation),
        })

    output = result.get("output", "")
    if isinstance(output, str) and output:
        yield ("text", output)
    elif not isinstance(output, str):
        yield ("text", json.dumps(output, default=str))

    yield ("done", None)
