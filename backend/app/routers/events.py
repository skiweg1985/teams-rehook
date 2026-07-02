from __future__ import annotations

import queue

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.deps import require_admin
from app.models import User
from app.services.event_stream import event_bus, heartbeat_event, sse_format

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
def stream_events(
    topics: str = Query(default="delivery_auth"),
    admin: User = Depends(require_admin),
):
    _ = admin
    topic_set = {topic.strip() for topic in topics.split(",") if topic.strip()}
    if not topic_set:
        topic_set = {"delivery_auth"}

    def event_iterator():
        subscriber = event_bus.subscribe(topic_set)
        try:
            while True:
                try:
                    envelope = subscriber.events.get(timeout=15)
                except queue.Empty:
                    envelope = heartbeat_event()
                yield sse_format(envelope)
        finally:
            event_bus.unsubscribe(subscriber)

    return StreamingResponse(
        event_iterator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
