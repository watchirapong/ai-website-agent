"""SSE event manager: tracks and streams progress events per project."""

import asyncio
import json
from collections import defaultdict

# Pipeline runs in a worker thread; emit() must not call asyncio.Queue.put_nowait
# from that thread — use the event loop's thread-safe scheduler instead.


class EventManager:
    """Manages Server-Sent Events for real-time progress streaming."""

    def __init__(self):
        self._events: dict[str, list[dict]] = defaultdict(list)
        # Each subscriber: (asyncio loop that owns the queue, asyncio.Queue)
        self._subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = (
            defaultdict(list)
        )

    def emit(self, project_id: str, step: str, status: str, detail: dict | None = None):
        """Emit a progress event for a project."""
        event = {
            "step": step,
            "status": status,
            "detail": detail or {},
        }
        self._events[project_id].append(event)

        for loop, queue in self._subscribers.get(project_id, []):
            loop.call_soon_threadsafe(queue.put_nowait, event)

    @staticmethod
    def _sse_chunk(event: dict) -> dict:
        """Format for sse_starlette.EventSourceResponse (do not pre-prefix ``data:``)."""
        return {"data": json.dumps(event, default=str)}

    def get_events(self, project_id: str) -> list[dict]:
        """Get all events emitted for a project."""
        return list(self._events.get(project_id, []))

    async def subscribe(self, project_id: str):
        """Async generator that yields SSE-formatted events."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sub = (loop, queue)
        self._subscribers[project_id].append(sub)

        # Yield dicts for sse_starlette — it wraps with ServerSentEvent (adds ``data:``).
        # Pre-formatted ``data: ...\\n\\n`` strings get double-wrapped and break EventSource.
        for event in self._events.get(project_id, []):
            yield self._sse_chunk(event)

        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=300)
                yield self._sse_chunk(event)

                if event.get("step") in ("deployer", "pipeline") and event.get("status") in ("done", "failed", "complete"):
                    break
        except asyncio.TimeoutError:
            yield self._sse_chunk(
                {
                    "step": "pipeline",
                    "status": "failed",
                    "detail": {"error": "SSE stream timeout"},
                }
            )
        finally:
            try:
                self._subscribers[project_id].remove(sub)
            except ValueError:
                pass

    def clear(self, project_id: str):
        """Clear events for a project."""
        self._events.pop(project_id, None)


event_manager = EventManager()
