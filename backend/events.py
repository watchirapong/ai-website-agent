"""SSE event manager: tracks and streams progress events per project."""

import asyncio
import json
from collections import defaultdict


class EventManager:
    """Manages Server-Sent Events for real-time progress streaming."""

    def __init__(self):
        self._events: dict[str, list[dict]] = defaultdict(list)
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def emit(self, project_id: str, step: str, status: str, detail: dict | None = None):
        """Emit a progress event for a project."""
        event = {
            "step": step,
            "status": status,
            "detail": detail or {},
        }
        self._events[project_id].append(event)

        for queue in self._subscribers.get(project_id, []):
            queue.put_nowait(event)

    def get_events(self, project_id: str) -> list[dict]:
        """Get all events emitted for a project."""
        return list(self._events.get(project_id, []))

    async def subscribe(self, project_id: str):
        """Async generator that yields SSE-formatted events."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[project_id].append(queue)

        # Send all past events first
        for event in self._events.get(project_id, []):
            yield f"event: {event['step']}\ndata: {json.dumps(event)}\n\n"

        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=300)
                yield f"event: {event['step']}\ndata: {json.dumps(event)}\n\n"

                if event.get("step") in ("deployer", "pipeline") and event.get("status") in ("done", "failed", "complete"):
                    break
        except asyncio.TimeoutError:
            yield "event: timeout\ndata: {}\n\n"
        finally:
            self._subscribers[project_id].remove(queue)

    def clear(self, project_id: str):
        """Clear events for a project."""
        self._events.pop(project_id, None)


event_manager = EventManager()
