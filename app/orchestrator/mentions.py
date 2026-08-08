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
        # Use explicit punctuation/space/EOF boundary instead of \W,
        # because Python 3 re treats CJK characters as \w, causing
        # @{role.name} followed by CJK text to not match.
        # Supported boundaries: whitespace, common CJK/ASCII punctuation,
        # brackets, quotes, or end of string.
        pattern = rf"@{re.escape(role.name)}(?=\s|[\u3000-\u303f\uFF00-\uFFEF,.\!?;:()\[\]{}\"']|$)"
        if re.search(pattern, text):
            mentioned.append(role)
            seen.add(role.name)
    return mentioned


def strip_mention_prefix(text: str, roles: list[Role]) -> str:
    """Remove a leading @role prefix commonly inserted by models when they reply."""
    for role in roles:
        prefix = f"@{role.name}"
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
            break
    return text
