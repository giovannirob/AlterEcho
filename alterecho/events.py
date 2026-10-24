"""Serializable events; a bounded replay buffer with explicit snapshot recovery."""
from collections import deque
from dataclasses import asdict, dataclass, field
from uuid import uuid4
from .history import now


@dataclass
class Event:
    id: str
    type: str
    conversation_id: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=now)

    def to_dict(self):
        return asdict(self)


class EventLog:
    def __init__(self, limit=2048):
        self.epoch, self.sequence = uuid4().hex, 0
        self.events = deque(maxlen=limit)

    def append(self, kind, conversation_id, data=None):
        self.sequence += 1
        event = Event(self.cursor, kind, conversation_id, data or {})
        self.events.append(event)
        return event

    @property
    def cursor(self):
        return f"{self.epoch}:{self.sequence}"

    def after(self, cursor):
        if cursor == self.cursor:
            return []
        for index, event in enumerate(self.events):
            if event.id == cursor:
                return list(self.events)[index + 1:]
        return None
