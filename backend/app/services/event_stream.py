from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass, field
from uuid import uuid4

from app.security import utcnow

SYSTEM_TOPIC = "system"


@dataclass(frozen=True)
class EventEnvelope:
    id: str
    topic: str
    type: str
    created_at: str
    payload: dict

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "type": self.type,
            "created_at": self.created_at,
            "payload": self.payload,
        }


@dataclass
class _Subscriber:
    topics: set[str]
    events: queue.Queue[EventEnvelope] = field(default_factory=lambda: queue.Queue(maxsize=100))


class EventBus:
    def __init__(self):
        self._subscribers: list[_Subscriber] = []
        self._lock = threading.Lock()

    def publish(self, topic: str, event_type: str, payload: dict | None = None) -> EventEnvelope:
        envelope = EventEnvelope(
            id=uuid4().hex,
            topic=topic,
            type=event_type,
            created_at=utcnow().isoformat(),
            payload=payload or {},
        )
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            if topic not in subscriber.topics:
                continue
            try:
                subscriber.events.put_nowait(envelope)
            except queue.Full:
                continue
        return envelope

    def subscribe(self, topics: set[str]) -> _Subscriber:
        subscriber = _Subscriber(topics={*topics, SYSTEM_TOPIC})
        with self._lock:
            self._subscribers.append(subscriber)
        subscriber.events.put(
            EventEnvelope(
                id=uuid4().hex,
                topic=SYSTEM_TOPIC,
                type="connected",
                created_at=utcnow().isoformat(),
                payload={"topics": sorted(subscriber.topics)},
            )
        )
        return subscriber

    def unsubscribe(self, subscriber: _Subscriber) -> None:
        with self._lock:
            self._subscribers = [entry for entry in self._subscribers if entry is not subscriber]


event_bus = EventBus()


def sse_format(envelope: EventEnvelope) -> str:
    data = json.dumps(envelope.to_dict(), sort_keys=True)
    return f"id: {envelope.id}\nevent: {envelope.topic}.{envelope.type}\ndata: {data}\n\n"


def heartbeat_event() -> EventEnvelope:
    return EventEnvelope(
        id=uuid4().hex,
        topic=SYSTEM_TOPIC,
        type="heartbeat",
        created_at=utcnow().isoformat(),
        payload={},
    )
