"""Agent 5 — DevOps Engineer: deploys the site to Vercel or local preview."""

import subprocess
import re
import os

import agent.config as cfg


def deploy_local_server() -> str:
    """Run production Next.js on this machine only (127.0.0.1), not a public URL.

    Requires `next build` to have succeeded in OUTPUT_DIR.
    """
    from agent.server import start as start_preview

    return start_preview()


def deploy_to_vercel() -> str:
    """Deploy the output directory to Vercel and return the production URL."""
    base_cmd = ["vercel", "--prod", "--yes"]
    try:
        result = subprocess.run(
            base_cmd,
            cwd=str(cfg.OUTPUT_DIR),
            capture_output=True,
            text=True,
            timeout=180,
            **cfg.SUBPROCESS_TEXT_KW,
        )
    except FileNotFoundError:
        if os.name == "nt":
            # Windows often resolves CLI shims only through cmd /c or npx.
            try:
                result = subprocess.run(
                    ["cmd", "/c", "vercel", "--prod", "--yes"],
                    cwd=str(cfg.OUTPUT_DIR),
                    capture_output=True,
                    text=True,
                    timeout=180,
                    **cfg.SUBPROCESS_TEXT_KW,
                )
            except FileNotFoundError:
                result = subprocess.run(
                    ["cmd", "/c", "npx", "vercel", "--prod", "--yes"],
                    cwd=str(cfg.OUTPUT_DIR),
                    capture_output=True,
                    text=True,
                    timeout=180,
                    **cfg.SUBPROCESS_TEXT_KW,
                )
        else:
            raise RuntimeError(
                "Vercel CLI not found. Install with `npm i -g vercel` or ensure `vercel` is on PATH."
            )

    combined = result.stdout + result.stderr

    if result.returncode != 0:
        raise RuntimeError(f"Vercel deployment failed:\n{combined}")

    # Vercel prints the production URL on stdout
    url_match = re.search(r"https://[\w.-]+\.vercel\.app", combined)
    if url_match:
        return url_match.group(0)

    # Fall back to any https URL in output
    url_match = re.search(r"https://\S+", combined)
    if url_match:
        return url_match.group(0)

    return combined.strip().split("\n")[-1]
