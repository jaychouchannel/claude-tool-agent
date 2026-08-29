from __future__ import annotations

import re

from .room import Role


def parse_mentions(text: str, roles: list[Role]) -> list[Role]:
    """Extract roles mentioned via @name in text.

    Longer names are matched first so that ``@翻译社`` does not also match
    role ``翻译``. A mention stays valid when CJK or other non-ASCII text is
    glued to it (``@研究员你好``); only ASCII word characters right after the
    name count as a different word (``@botman`` does not match role ``bot``).
    Roles are returned in the order they first appear in the text.
    """
    by_name: dict[str, Role] = {}
    for role in roles:
        if role.name and role.name not in by_name:
            by_name[role.name] = role
    if not by_name:
        return []
    pattern = re.compile(
        "@("
        + "|".join(re.escape(n) for n in sorted(by_name, key=len, reverse=True))
        + ")(?![A-Za-z0-9_])"
    )
    mentioned: list[Role] = []
    seen: set[str] = set()
    for m in pattern.finditer(text):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        mentioned.append(by_name[name])
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
