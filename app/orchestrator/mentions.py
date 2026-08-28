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


def strip_mention_prefix(text: str, roles: list[Role]) -> str:
    """Remove a leading @role prefix commonly inserted by models when they reply."""
    for role in roles:
        prefix = f"@{role.name}"
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
            break
    return text
