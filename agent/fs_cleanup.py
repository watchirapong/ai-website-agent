"""Clear generated output directories safely (Windows file locks from Node / next-swc)."""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

logger = logging.getLogger("agent.fs_cleanup")


def _chmod_writable(func, path: str, exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _try_stop_api_preview() -> None:
    try:
        from backend.preview_manager import stop_preview_server

        stop_preview_server()
    except ImportError:
        pass


def _path_variants_for_windows(path: Path) -> list[str]:
    """Strings that may appear in Node command lines (mixed slashes, casing)."""
    resolved = str(path.resolve())
    parent, name = path.parent.name, path.name
    out: list[str] = [
        resolved,
        resolved.lower(),
        resolved.replace("\\", "/"),
        resolved.replace("\\", "/").lower(),
        f"{parent}\\{name}",
        f"{parent}/{name}",
        f"{parent}\\{name}".lower(),
        f"{parent}/{name}".lower(),
    ]
    seen: set[str] = set()
    uniq: list[str] = []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _kill_windows_node_using_path(path: Path) -> None:
    """Terminate ``node.exe`` processes whose command line references ``path`` (locks ``.node`` DLLs)."""
    if os.name != "nt":
        return
    variants = _path_variants_for_windows(path)
    tmp_json: str | None = None
    try:
        fd, tmp_json = tempfile.mkstemp(suffix=".json", prefix="aiagent-kill-")
        os.close(fd)
        Path(tmp_json).write_text(json.dumps(variants), encoding="utf-8")
        lit = tmp_json.replace("'", "''")
        script = (
            f"$variants = Get-Content -LiteralPath '{lit}' -Raw -Encoding UTF8 | ConvertFrom-Json; "
            "Get-CimInstance Win32_Process | Where-Object { "
            "  $_.Name -and ($_.Name.ToLower() -eq 'node.exe') -and $_.CommandLine "
            "} | ForEach-Object { "
            "  $cl = ($_.CommandLine.ToLower() -creplace '\\\\','/'); "
            "  foreach ($v in $variants) { "
            "    $vv = ([string]$v).ToLower() -creplace '\\\\','/'; "
            "    if ($cl.Contains($vv)) { "
            "      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; break } } }"
        )
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            timeout=60,
            check=False,
            text=True,
        )
        if r.returncode != 0 and (r.stderr or "").strip():
            logger.debug("kill node for path: %s", (r.stderr or r.stdout)[:500])
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.debug("kill node for path failed: %s", e)
    finally:
        if tmp_json:
            try:
                Path(tmp_json).unlink(missing_ok=True)
            except OSError:
                pass
    time.sleep(1.0)


def _windows_rd_tree(path: Path) -> None:
    """``cmd rd /s /q`` — sometimes succeeds when ``rmtree`` hits transient locks."""
    if os.name != "nt" or not path.exists():
        return
    p = str(path.resolve())
    try:
        subprocess.run(
            ["cmd.exe", "/c", "rd", "/s", "/q", p],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("rd /s /q failed: %s", e)


def _kill_all_windows_node() -> None:
    """``taskkill /F /IM node.exe`` — use only when AGENT_WINDOWS_KILL_ALL_NODE is set."""
    if os.name != "nt":
        return
    logger.warning(
        "AGENT_WINDOWS_KILL_ALL_NODE: forcing termination of all node.exe (may close unrelated Node apps)."
    )
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "node.exe", "/T"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("taskkill node.exe: %s", e)
    time.sleep(1.0)


def _fresh_sibling_dir(locked: Path) -> Path:
    alt = locked.parent / f"{locked.name}__fresh_{int(time.time() * 1000)}"
    alt.mkdir(parents=True, exist_ok=True)
    return alt


def _is_cleanup_access_denied(exc: BaseException) -> bool:
    """True for typical Windows file-lock / access-denied errors during tree delete."""
    if isinstance(exc, PermissionError):
        return True
    if not isinstance(exc, OSError):
        return False
    if os.name == "nt":
        we = getattr(exc, "winerror", None)
        if we in (5, 32):  # access denied, sharing violation
            return True
    return exc.errno in (errno.EACCES, errno.EPERM)


def _reset_output_directory_impl(
    target: Path,
    *,
    stop_api_preview: bool,
) -> Path:
    if stop_api_preview:
        _try_stop_api_preview()

    if os.name == "nt" and os.getenv("AGENT_WINDOWS_KILL_ALL_NODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        _kill_all_windows_node()

    if target.exists() and os.name == "nt":
        _kill_windows_node_using_path(target)
        _windows_rd_tree(target)

    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
        return target

    delays = (0, 0.35, 0.75, 1.5)
    for wait in delays:
        if wait:
            time.sleep(wait)
        try:
            shutil.rmtree(target, onerror=_chmod_writable)
        except OSError:
            continue
        if not target.exists():
            break

    if target.exists():
        if os.name == "nt":
            _kill_windows_node_using_path(target)
            _windows_rd_tree(target)
            time.sleep(0.5)
        trash = target.parent / f"{target.name}_quarantine_{int(time.time() * 1000)}"
        try:
            target.rename(trash)
        except OSError as e:
            alt = _fresh_sibling_dir(target)
            logger.warning(
                "Locked output dir %s could not be cleared (%s); writing to %s instead.",
                target,
                e,
                alt,
            )
            return alt

    target.mkdir(parents=True, exist_ok=True)
    return target


def reset_output_directory(
    target: Path,
    *,
    stop_api_preview: bool = False,
) -> Path:
    """Remove ``target`` so a fresh empty directory can be created.

    ``next dev`` (and native ``.node`` binaries) often lock files under
    ``node_modules`` on Windows, which makes plain ``rmtree`` fail with
    ``PermissionError`` / ``WinError 5``. We retry with chmod helpers, then
    quarantine by renaming the tree aside if needed.

    If the folder cannot be removed or renamed (still locked), returns a new
    sibling path ``{name}__fresh_{ms}`` so the pipeline can continue; the old
    tree is left on disk for manual cleanup.

    Any unexpected ``PermissionError`` / access-denied ``OSError`` during cleanup
    is handled the same way (fallback directory) so the pipeline does not hard-fail.
    """
    target = Path(target)
    try:
        return _reset_output_directory_impl(target, stop_api_preview=stop_api_preview)
    except (PermissionError, OSError) as e:
        if not _is_cleanup_access_denied(e):
            raise
        alt = _fresh_sibling_dir(target)
        logger.warning(
            "Output dir cleanup failed with %s (%s); writing to %s instead.",
            type(e).__name__,
            e,
            alt,
        )
        return alt
