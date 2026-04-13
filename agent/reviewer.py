"""Agent 4 — Tech Lead: threshold checking utilities.

LLM interaction for generating fix instructions is handled by CrewAI.
This module provides the deterministic pass/fail logic.
"""

from agent.config import (
    THRESHOLD_PERFORMANCE,
    THRESHOLD_ACCESSIBILITY,
    THRESHOLD_BEST_PRACTICES,
    THRESHOLD_SEO,
    MAX_CONSOLE_ERRORS,
    MAX_BROKEN_LINKS,
    MAX_LOAD_TIME_MS,
)


def check_thresholds(report: dict) -> list[str]:
    """Compare test results against quality thresholds. Return list of failures."""
    issues: list[str] = []
    lh = report.get("lighthouse", {})

    checks = [
        ("Performance", lh.get("performance", 0), THRESHOLD_PERFORMANCE),
        ("Accessibility", lh.get("accessibility", 0), THRESHOLD_ACCESSIBILITY),
        ("Best Practices", lh.get("best_practices", 0), THRESHOLD_BEST_PRACTICES),
        ("SEO", lh.get("seo", 0), THRESHOLD_SEO),
    ]

    for name, score, threshold in checks:
        if score < threshold:
            issues.append(f"{name} score {score} < {threshold}")

    console_errors = report.get("console_errors", [])
    if len(console_errors) > MAX_CONSOLE_ERRORS:
        issues.append(f"{len(console_errors)} console error(s): {', '.join(console_errors[:3])}")

    broken_links = report.get("broken_links", [])
    if len(broken_links) > MAX_BROKEN_LINKS:
        issues.append(f"{len(broken_links)} broken link(s): {', '.join(broken_links[:3])}")

    load_time = report.get("load_time_ms", 0)
    if load_time > MAX_LOAD_TIME_MS:
        issues.append(f"Load time {load_time}ms > {MAX_LOAD_TIME_MS}ms")

    return issues


def compute_score(report: dict) -> int:
    """Compute overall score as the average of Lighthouse categories."""
    lh = report.get("lighthouse", {})
    scores = [
        lh.get("performance", 0),
        lh.get("accessibility", 0),
        lh.get("best_practices", 0),
        lh.get("seo", 0),
    ]
    return int(sum(scores) / max(len(scores), 1))
