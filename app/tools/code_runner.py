"""Run Python code in a subprocess. Demo-grade sandbox only — do not deploy publicly."""
import subprocess
import sys
import os

TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 5000

TOOL_SPEC = {
    "name": "run_python_code",
    "description": "Execute a snippet of Python code and return stdout and stderr. Use for calculations, data manipulation, or verifying logic. WARNING: runs as your user — do not use untrusted code.",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute. Capture output via print().",
            },
        },
        "required": ["code"],
    },
}


def run(code: str) -> str:
    """Execute arbitrary Python code via subprocess. Truncates long output."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return f"Execution timed out after {TIMEOUT_SECONDS} seconds."
    except Exception as e:
        return f"Failed to execute: {e}"

    out = proc.stdout or ""
    err = proc.stderr or ""
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS] + f"\n...[truncated, {len(out)} total chars]"
    if len(err) > MAX_OUTPUT_CHARS:
        err = err[:MAX_OUTPUT_CHARS] + f"\n...[truncated, {len(err)} total chars]"
    return f"[stdout]\n{out}\n\n[stderr]\n{err}"
