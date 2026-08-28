from __future__ import annotations

import re

from .room import Role


def parse_mentions(text: str, roles: list[Role]) -> list[Role]:
    """Extract roles mentioned via @name in text.

    Uses word-boundary regex to avoid false substring matches, and
    deduplicates so the same role is never yielded twice per message.
    """
    seen: set[str] = set()
    mentioned: list[Role] = []
    for role in roles:
        if role.name in seen:
            continue
        if re.search(rf"@{re.escape(role.name)}(?=\W|$)", text):
            mentioned.append(role)
            seen.add(role.name)
    return mentioned


def strip_mention_prefix(text: str, roles: list[Role], speaker: str | None = None) -> str:
    """Remove a leading @mention of the speaking role from its own reply.

    Models commonly echo their own name ("@代码手: ..."), which would then
    read as a self-mention in the history. A leading mention of a DIFFERENT
    role must be kept: it is exactly the "@链式发言" signal the chaining loop
    parses from the cleaned content, and stripping it silently breaks the
    chain whenever a reply opens by addressing the next speaker.
    """
    for role in roles:
        prefix = f"@{role.name}"
        if text.startswith(prefix):
            if speaker is not None and role.name != speaker:
                break
            text = text[len(prefix):].lstrip(" \u3000\t，,、。：:；;")
            break
    return text
