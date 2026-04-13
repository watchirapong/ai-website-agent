"""Capture Python logging during a pipeline run and forward lines to the SSE event stream."""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

from backend.events import event_manager

_MAX_MSG = 4000
_MAX_LOG_EVENTS = 2500
# Named loggers (not root — root is attached once separately).
_LOGGERS = ("crewai", "LiteLLM", "litellm", "anthropic", "httpx", "openai", "ollama", "uvicorn", "agent")


class _PipelineLogHandler(logging.Handler):
    """Forward log records to ``event_manager`` as ``log`` / ``line`` events."""

    def __init__(self, project_id: str):
        super().__init__(level=logging.INFO)
        self.project_id = project_id
        self._lock = threading.Lock()
        self._count = 0
        self.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            with self._lock:
                if self._count >= _MAX_LOG_EVENTS:
                    return
                self._count += 1
            msg = self.format(record)
            if len(msg) > _MAX_MSG:
                msg = msg[:_MAX_MSG] + "…"
            event_manager.emit(self.project_id, "log", "line", {"message": msg})
        except Exception:
            self.handleError(record)


@contextmanager
def pipeline_log_context(project_id: str) -> Iterator[None]:
    """Attach a handler so logs during ``run_pipeline`` are streamed to the dashboard."""
    handler = _PipelineLogHandler(project_id)
    root = logging.getLogger()
    root.addHandler(handler)

    previous_levels: dict[str, int] = {}
    for name in _LOGGERS:
        log = logging.getLogger(name)
        previous_levels[name] = log.level
        log.addHandler(handler)
        if log.level > logging.INFO:
            log.setLevel(logging.INFO)

    try:
        yield
    finally:
        root.removeHandler(handler)
        for name in _LOGGERS:
            log = logging.getLogger(name)
            try:
                log.removeHandler(handler)
            except ValueError:
                pass
            log.setLevel(previous_levels.get(name, logging.NOTSET))
