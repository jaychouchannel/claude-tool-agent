from __future__ import annotations

from .room import Role


def parse_mentions(text: str, roles: list[Role]) -> list[Role]:
    """Extract roles mentioned via @name in text."""
    mentioned: list[Role] = []
    for role in roles:
        if f"@{role.name}" in text:
            mentioned.append(role)
    return mentioned


def strip_mention_prefix(text: str, roles: list[Role]) -> str:
    """Remove a leading @role prefix commonly inserted by models when they reply."""
    for role in roles:
        prefix = f"@{role.name}"
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
            break
    return text
