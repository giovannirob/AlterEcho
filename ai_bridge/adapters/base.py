from dataclasses import dataclass, field
from typing import Protocol, Callable

from ..history import Conversation


@dataclass
class Reply:
    text: str
    model: str
    usage: dict = field(default_factory=dict)


class Adapter(Protocol):
    async def generate(self, conversation: Conversation, checkpoint: Callable[[], None]) -> Reply: ...
    async def close(self) -> None: ...
