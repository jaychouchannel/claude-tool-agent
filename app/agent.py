"""Agentic loop: call Claude, execute tools, stream SSE events."""
from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import anthropic

from .config import MAX_ITERATIONS, get_model
from .tools import get_tool_specs, run_tool

SYSTEM_PROMPT = (
    "You are a helpful AI assistant with access to tools.\n"
    "Always use tools when they can help answer the user's question.\n"
    "After using a tool, summarise the results for the user in a concise, helpful way."
)


def chat(
    api_key: str,
    messages: list[dict[str, Any]],
) -> Generator[tuple[str, Any], None, None]:
    """
    Agent loop: streams SSE-style events.

    Yields:
        (event_name, payload) tuples

        event_name ∈ {"text", "tool_use", "tool_result", "error", "done"}
        payload  ∈ str | dict
    """
    client = anthropic.Anthropic(api_key=api_key)
    model = get_model()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=get_tool_specs(),
            messages=messages,
        )
    except anthropic.AuthenticationError as e:
        yield ("error", f"API key invalid: {e}")
        yield ("done", None)
        return
    except anthropic.APIError as e:
        yield ("error", f"Claude API error: {e}")
        yield ("done", None)
        return

    # Append assistant's response to messages so tool calls carry forward
    messages.append({"role": "assistant", "content": response.content})

    # Extract text blocks and yield them
    for block in response.content:
        if block.type == "text":
            yield ("text", block.text)

    # If no tool call, we're done
    if response.stop_reason != "tool_use":
        yield ("done", None)
        return

    # ---------- Tool loop ----------
    for _ in range(MAX_ITERATIONS):
        # Collect tool_use blocks
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            break

        tool_results: list[dict[str, Any]] = []

        for tu in tool_uses:
            yield ("tool_use", {"id": tu.id, "name": tu.name, "input": tu.input})

            try:
                result = run_tool(tu.name, tu.input)
            except Exception as e:
                result = f"Tool error: {e}"

            yield ("tool_result", {"id": tu.id, "name": tu.name, "output": result})

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result,
                }
            )

        # Feed results back into Claude
        messages.append({"role": "user", "content": tool_results})

        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=get_tool_specs(),
                messages=messages,
            )
        except Exception as e:
            yield ("error", f"Claude API error: {e}")
            yield ("done", None)
            return

        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "text":
                yield ("text", block.text)

        if response.stop_reason != "tool_use":
            break

    yield ("done", None)
