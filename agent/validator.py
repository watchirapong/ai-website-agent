"""Build validation: runs npm install + next build and captures errors."""

import os
import shutil
import subprocess

import agent.config as cfg


def _run_subprocess(argv: list[str], cwd: str, timeout: int) -> subprocess.CompletedProcess:
    """Run a command; on Windows retry with cmd /c and .cmd shims (avoids WinError 2)."""
    attempts: list[list[str]] = [argv]
    if os.name == "nt":
        exe = argv[0] if argv else ""
        rest = argv[1:]
        if exe == "npm":
            p = shutil.which("npm.cmd")
            if p:
                attempts.append([p, *rest])
            attempts.append(["cmd", "/c", "npm", *rest])
        elif exe == "npx":
            p = shutil.which("npx.cmd")
            if p:
                attempts.append([p, *rest])
            attempts.append(["cmd", "/c", "npx", *rest])

    last: OSError | None = None
    for cmd in attempts:
        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
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
    raise last or FileNotFoundError(argv[0] if argv else "command")


def run_install() -> tuple[bool, str]:
    """Run npm install in the output directory.

    Returns (success, output_text).
    """
    try:
        result = _run_subprocess(
            ["npm", "install"],
            str(cfg.OUTPUT_DIR),
            120,
        )
    except OSError as e:
        if not isinstance(e, FileNotFoundError) and getattr(e, "winerror", None) != 2:
            raise
        return (
            False,
            "npm not found. Install Node.js (https://nodejs.org) and ensure `npm` is on PATH, "
            "then restart the backend.",
        )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def run_build() -> tuple[bool, str]:
    """Run next build in the output directory.

    Returns (success, output_text).
    """
    try:
        result = _run_subprocess(
            ["npx", "next", "build"],
            str(cfg.OUTPUT_DIR),
            180,
        )
    except OSError as e:
        if not isinstance(e, FileNotFoundError) and getattr(e, "winerror", None) != 2:
            raise
        return (
            False,
            "npx not found. Install Node.js (https://nodejs.org) and ensure `npx` is on PATH, "
            "then restart the backend.",
        )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def validate() -> tuple[bool, str]:
    """Run full build pipeline: install → build.

    Returns (success, combined_output).
    """
    ok, install_out = run_install()
    if not ok:
        return False, f"npm install failed:\n{install_out}"

    ok, build_out = run_build()
    if not ok:
        return False, f"next build failed:\n{build_out}"

    return True, "Build succeeded"
