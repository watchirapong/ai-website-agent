"""SSE event manager: tracks and streams progress events per project."""

import asyncio
import json
from datetime import datetime, timezone
from collections import defaultdict

# Pipeline runs in a worker thread; emit() must not call asyncio.Queue.put_nowait
# from that thread — use the event loop's thread-safe scheduler instead.


class EventManager:
    """Manages Server-Sent Events for real-time progress streaming."""

    def __init__(self):
        self._events: dict[str, list[dict]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)
        # Each subscriber: (asyncio loop that owns the queue, asyncio.Queue)
        self._subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = (
            defaultdict(list)
        )

    def emit(self, project_id: str, step: str, status: str, detail: dict | None = None):
        """Emit a progress event for a project."""
        self._seq[project_id] += 1
        event = {
            "seq": self._seq[project_id],
            "timestamp": datetime.now(timezone.utc).isoformat(),
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

    async def subscribe(self, project_id: str, skip: int = 0, after_seq: int = 0):
        """Async generator that yields SSE-formatted events.

        ``skip`` — number of already-delivered events to omit from the initial replay
        (client fetched them via GET /api/status first, so EventSource must not duplicate).
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sub = (loop, queue)
        self._subscribers[project_id].append(sub)

        if skip < 0:
            skip = 0
        if after_seq < 0:
            after_seq = 0
        buffered = self._events.get(project_id, [])

        # Yield dicts for sse_starlette — it wraps with ServerSentEvent (adds ``data:``).
        # Pre-formatted ``data: ...\\n\\n`` strings get double-wrapped and break EventSource.
        replay = buffered[skip:]
        if after_seq > 0:
            replay = [e for e in replay if int(e.get("seq", 0)) > after_seq]
        for event in replay:
            yield self._sse_chunk(event)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300)
                    yield self._sse_chunk(event)

                    # End only on terminal pipeline events. Do not close on deployer done —
                    # main.py emits pipeline complete/failed after run_pipeline returns.
                    if event.get("step") == "pipeline" and event.get("status") in (
                        "complete",
                        "failed",
                    ):
                        break
                except asyncio.TimeoutError:
                    # Keep the stream alive during long-running steps (e.g., LLM generation)
                    # instead of closing the stream or marking the pipeline failed.
                    yield self._sse_chunk(
                        {
                            "step": "stream",
                            "status": "keepalive",
                            "detail": {
                                "message": "SSE keepalive",
                                "last_seq": int(self._seq.get(project_id, 0)),
                            },
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
