from __future__ import annotations

import re

from .room import Role


def parse_mentions(text: str, roles: list[Role]) -> list[Role]:
    """Extract roles mentioned via @name in text.

    Sorts roles by name length descending (longest match first) so that
    ``@管理员`` matches ``管理员`` rather than its prefix ``管理`` when both
    roles exist.  No ``\\w`` boundary check is used — CJK ideographs are
    Unicode word characters in Python's re, so ``\\W`` boundaries don't fire
    reliably on CJK text.  Instead, a shorter role is suppressed at any
    position where a longer role was matched at the same offset.
    """
    seen: set[str] = set()
    mentioned: list[Role] = []
    matched_spans: list[tuple[int, int]] = []
    for role in sorted(roles, key=lambda r: len(r.name), reverse=True):
        if role.name in seen:
            continue
        pattern = rf"@{re.escape(role.name)}"
        for m in re.finditer(pattern, text):
            # Skip if a longer role (already matched in this loop, longest first)
            # covers this span.
            if any(m.start() >= s and m.end() <= e for s, e in matched_spans):
                continue
            mentioned.append(role)
            seen.add(role.name)
            matched_spans.append((m.start(), m.end()))
            break
    return mentioned


def strip_mention_prefix(text: str, roles: list[Role]) -> str:
    """Remove a leading @role prefix commonly inserted by models when they reply."""
    for role in roles:
        prefix = f"@{role.name}"
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
            break
    return text
