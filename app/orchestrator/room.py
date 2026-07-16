from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Role:
    name: str
    system_prompt: str
    model: str


@dataclass
class Message:
    role: Literal["user", "assistant"]
    name: str
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "name": self.name, "content": self.content}


@dataclass
class RoomConfig:
    room_id: str = "default"
    roles: list[Role] = field(default_factory=list)
    group_rules: str = ""
