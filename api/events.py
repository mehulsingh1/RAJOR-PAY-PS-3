"""In-process async pub/sub for streaming events to SSE clients."""

import asyncio
import json
from collections import deque
from datetime import datetime, timezone


class EventBus:
    def __init__(self, history: int = 200):
        self._subscribers: set[asyncio.Queue] = set()
        self._history: deque = deque(maxlen=history)

    def publish(self, kind: str, data: dict) -> None:
        evt = {
            "kind": kind,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data": data,
        }
        self._history.append(evt)
        for q in list(self._subscribers):
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                pass

    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        try:
            for evt in list(self._history):
                q.put_nowait(evt)
            while True:
                evt = await q.get()
                yield f"data: {json.dumps(evt)}\n\n"
        finally:
            self._subscribers.discard(q)

    def recent(self, n: int = 50) -> list[dict]:
        return list(self._history)[-n:]


BUS = EventBus()
