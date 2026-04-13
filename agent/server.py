"""Local preview server: start/stop Next.js on localhost."""

import subprocess
import time
import signal
import requests as http_requests
from agent.config import OUTPUT_DIR, PREVIEW_PORT


_process: subprocess.Popen | None = None


def start() -> str:
    """Start `next start` and wait until it's ready.

    Returns the local URL.
    """
    global _process

    stop()

    _process = subprocess.Popen(
        ["npx", "next", "start", "-p", str(PREVIEW_PORT)],
        cwd=str(OUTPUT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    url = f"http://localhost:{PREVIEW_PORT}"

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
