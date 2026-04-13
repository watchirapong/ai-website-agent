"""Agent 5 — DevOps Engineer: deploys the site to Vercel."""

import subprocess
import re
from agent.config import OUTPUT_DIR


def deploy_to_vercel() -> str:
    """Deploy the output directory to Vercel and return the production URL."""
    result = subprocess.run(
        ["vercel", "--prod", "--yes"],
        cwd=str(OUTPUT_DIR),
        capture_output=True,
        text=True,
        timeout=120,
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
