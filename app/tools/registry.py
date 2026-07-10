"""Tool registry — maps names to run-functions & builds Anthropic tool specs."""
from typing import Any

from . import code_runner, file_read, search, wikipedia

_TOOLS: dict[str, callable] = {
    code_runner.TOOL_SPEC["name"]: code_runner.run,
    file_read.TOOL_SPEC["name"]: file_read.run,
    search.TOOL_SPEC["name"]: search.run,
    wikipedia.TOOL_SPEC["name"]: wikipedia.run,
}

REGISTRY = _TOOLS


def get_tool_specs() -> list[dict[str, Any]]:
    """Return the list of tool definitions for Anthropic's tools parameter."""
    return [
        code_runner.TOOL_SPEC,
        file_read.TOOL_SPEC,
        search.TOOL_SPEC,
        wikipedia.TOOL_SPEC,
    ]


def run_tool(name: str, args: dict[str, Any]) -> str:
    """Execute a tool by name with the given keyword arguments."""
    fn = REGISTRY.get(name)
    if not fn:
        raise ValueError(f"Unknown tool: {name}")
    return fn(**args)
