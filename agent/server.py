"""Local preview server: start/stop Next.js on localhost (127.0.0.1 only)."""

import os
import shutil
import subprocess
import time
import signal

import requests as http_requests

import agent.config as cfg

_process: subprocess.Popen | None = None

# Bind to loopback so the preview is not exposed on the LAN by default.
_PREVIEW_HOST = "127.0.0.1"


def _popen_next_start() -> subprocess.Popen:
    """Start `next start` with Windows-friendly npx resolution."""
    port = str(cfg.PREVIEW_PORT)
    tail = ["next", "start", "-H", _PREVIEW_HOST, "-p", port]
    candidates: list[list[str]] = [["npx", *tail]]
    if os.name == "nt":
        npx = shutil.which("npx.cmd") or shutil.which("npx")
        if npx:
            candidates.insert(0, [npx, *tail])
        candidates.append(["cmd", "/c", "npx", *tail])

    last: OSError | None = None
    for cmd in candidates:
        try:
            return subprocess.Popen(
                cmd,
                cwd=str(cfg.OUTPUT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **cfg.SUBPROCESS_TEXT_KW,
            )
        except FileNotFoundError as e:
            last = e
            continue
        except OSError as e:
            if getattr(e, "winerror", None) == 2:
                last = e
                continue
            raise
    raise last or FileNotFoundError("npx")


def start() -> str:
    """Start `next start` and wait until it's ready.

    Returns the local URL (127.0.0.1 only).
    """
    global _process

    stop()

    _process = _popen_next_start()

    url = f"http://{_PREVIEW_HOST}:{cfg.PREVIEW_PORT}"

    for _ in range(30):
        try:
            resp = http_requests.get(url, timeout=2)
            if resp.status_code == 200:
                return url
        except (http_requests.ConnectionError, http_requests.Timeout):
            pass
        time.sleep(1)

    raise TimeoutError(f"Server did not start within 30 seconds on {url}")


def stop():
    """Stop the preview server if running."""
    global _process
    if _process is not None:
        try:
            _process.send_signal(signal.SIGTERM)
            _process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            _process.kill()
        finally:
            _process = None
