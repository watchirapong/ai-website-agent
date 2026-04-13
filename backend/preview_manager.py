"""Start a single local `next dev` preview for a generated project directory."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

import requests

from agent.config import API_PREVIEW_PORT, SUBPROCESS_TEXT_KW

_HOST = "127.0.0.1"

_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_current_dir: str | None = None


def _stop_unlocked() -> None:
    global _proc, _current_dir
    if _proc is not None:
        try:
            _proc.send_signal(signal.SIGTERM)
            _proc.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            _proc.kill()
        finally:
            _proc = None
            _current_dir = None


def stop_preview_server() -> None:
    with _lock:
        _stop_unlocked()


def _popen_next_dev(cwd: Path, port: int) -> subprocess.Popen:
    tail = ["next", "dev", "-H", _HOST, "-p", str(port)]
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
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **SUBPROCESS_TEXT_KW,
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


def ensure_preview_for_output_dir(output_dir: str, port: int | None = None) -> str:
    """Ensure `next dev` is running for ``output_dir``; return base URL (no trailing slash)."""
    global _proc, _current_dir

    port = API_PREVIEW_PORT if port is None else port
    root = Path(output_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    key = str(root)
    url = f"http://{_HOST}:{port}"

    with _lock:
        if _proc is not None and _current_dir == key and _proc.poll() is None:
            try:
                r = requests.get(url, timeout=2)
                if r.status_code < 500:
                    return url
            except (requests.ConnectionError, requests.Timeout):
                pass

        _stop_unlocked()
        _proc = _popen_next_dev(root, port)
        _current_dir = key

        for _ in range(90):
            if _proc.poll() is not None:
                raise RuntimeError(
                    "next dev exited early — check Node/npm and that the folder has package.json"
                )
            try:
                r = requests.get(url, timeout=2)
                if r.status_code < 500:
                    return url
            except (requests.ConnectionError, requests.Timeout):
                pass
            time.sleep(1)

    raise TimeoutError(f"Preview did not become ready at {url}")
