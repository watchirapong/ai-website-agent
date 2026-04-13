"""Agent 4 — Tech Lead: reviews test results and decides pass/fail."""

import json
import ollama as ollama_client
from agent.config import (
    OLLAMA_MODEL,
    OLLAMA_BASE_URL,
    PROMPTS_DIR,
    THRESHOLD_PERFORMANCE,
    THRESHOLD_ACCESSIBILITY,
    THRESHOLD_BEST_PRACTICES,
    THRESHOLD_SEO,
    MAX_CONSOLE_ERRORS,
    MAX_BROKEN_LINKS,
    MAX_LOAD_TIME_MS,
)


def _load_system_prompt() -> str:
    path = PROMPTS_DIR / "system_reviewer.txt"
    return path.read_text()


def _check_thresholds(report: dict) -> list[str]:
    """Compare test results against thresholds. Return list of failures."""
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


def review(test_report: dict, original_prompt: str) -> dict:
    """Review test results and return a pass/fail verdict.

    Returns dict with keys: passed, score, issues, fix_instructions.
    """
    threshold_issues = _check_thresholds(test_report)

    lh = test_report.get("lighthouse", {})
    scores = [
        lh.get("performance", 0),
        lh.get("accessibility", 0),
        lh.get("best_practices", 0),
        lh.get("seo", 0),
    ]
    overall_score = int(sum(scores) / max(len(scores), 1))

    if not threshold_issues:
        return {
            "passed": True,
            "score": overall_score,
            "issues": [],
            "fix_instructions": None,
        }

    # Ask LLM for specific fix instructions
    system_prompt = _load_system_prompt()
    user_message = (
        f"Original prompt: {original_prompt}\n\n"
        f"Test report:\n{json.dumps(test_report, indent=2)}\n\n"
        f"Failed checks:\n" + "\n".join(f"- {i}" for i in threshold_issues)
    )

    client = ollama_client.Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    fix_instructions = response["message"]["content"]

    return {
        "passed": False,
        "score": overall_score,
        "issues": threshold_issues,
        "fix_instructions": fix_instructions,
    }
