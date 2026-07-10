"""Read a text file from the project's working directory (sandboxed)."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 20_000
ALLOWED_SUFFIXES = {
    ".txt", ".md", ".rst", ".json", ".yaml", ".yml",
    ".py", ".js", ".ts", ".html", ".css",
    ".csv", ".tsv", ".log", ".ini", ".toml", ".env.example",
}

TOOL_SPEC = {
    "name": "file_read",
    "description": (
        "Read a text file inside this project's working directory and return its contents. "
        "Paths outside the project root are rejected. "
        f"Files larger than {MAX_BYTES} bytes are truncated. "
        "Use to inspect source code, config files, READMEs, or data files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the project root, e.g. `README.md` or `app/agent.py`.",
            },
        },
        "required": ["path"],
    },
}


def _resolve(path: str) -> Path:
    candidate = (PROJECT_ROOT / path).resolve()
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError as e:
        raise ValueError(f"Path is outside the project sandbox: {path}") from e
    return candidate


def run(path: str) -> str:
    if not path or not path.strip():
        return "Empty path."
    try:
        target = _resolve(path)
    except ValueError as e:
        return str(e)

    if not target.exists():
        return f"File does not exist: {path}"
    if target.is_dir():
        return f"Path is a directory, not a file: {path}"
    if target.suffix.lower() not in ALLOWED_SUFFIXES:
        return f"Refusing to read file with extension `{target.suffix}` (not in allowlist)."

    try:
        raw = target.read_bytes()
    except OSError as e:
        return f"Failed to read file: {e}"

    if len(raw) > MAX_BYTES:
        raw = raw[:MAX_BYTES]
        truncated_note = f"\n...[truncated, {len(raw)} bytes total]"
    else:
        truncated_note = ""

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return f"File is not valid UTF-8 text: {path}"
    return f"== {path} ==\n{text}{truncated_note}"
