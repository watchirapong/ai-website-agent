"""CrewAI pipeline: orchestrates all agents through the generate → test → review loop."""

import shutil
import time
from typing import Callable

from agent.config import OUTPUT_DIR, MAX_RETRIES, ensure_dirs
from agent.planner import plan_site
from agent.generator import generate_site
from agent.validator import validate
from agent.server import start as start_server, stop as stop_server
from agent.tester import run_tests
from agent.reviewer import review
from agent.deployer import deploy_to_vercel


def _clean_output():
    """Remove previous generated site."""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_pipeline(
    user_prompt: str,
    on_event: Callable[[str, str, dict], None] | None = None,
    skip_deploy: bool = False,
) -> dict:
    """Run the full agent pipeline.

    Args:
        user_prompt: The user's website description.
        on_event: Optional callback(step, status, detail) for progress updates.
        skip_deploy: If True, skip the deployment step.

    Returns:
        Final result dict with keys: url, scores, attempts, report, time_seconds.
    """
    ensure_dirs()

    def emit(step: str, status: str, detail: dict | None = None):
        if on_event:
            on_event(step, status, detail or {})

    pipeline_start = time.time()
    best_score = 0
    best_attempt_report = None

    # Step 1: Plan
    emit("planner", "running")
    plan = plan_site(user_prompt)
    emit("planner", "done", {"plan": plan})

    fix_instructions = None

    for attempt in range(1, MAX_RETRIES + 1):
        emit("attempt", "start", {"attempt": attempt, "max": MAX_RETRIES})

        # Step 2: Generate
        _clean_output()
        emit("developer", "running")
        files = generate_site(plan, fix_instructions)
        emit("developer", "done", {"files": files, "count": len(files)})

        # Step 3: Build
        emit("build", "running")
        build_ok, build_output = validate()
        if not build_ok:
            emit("build", "failed", {"output": build_output[:500]})
            fix_instructions = f"Build failed with errors:\n{build_output[:1000]}"
            continue
        emit("build", "done")

        # Step 4: Serve
        emit("server", "running")
        try:
            url = start_server()
        except TimeoutError as e:
            emit("server", "failed", {"error": str(e)})
            fix_instructions = "The generated site failed to start. Check for runtime errors."
            continue
        emit("server", "done", {"url": url})

        # Step 5: Test
        emit("tester", "running")
        test_report = run_tests(url)
        stop_server()
        emit("tester", "done", {"report": test_report})

        # Step 6: Review
        emit("reviewer", "running")
        review_result = review(test_report, user_prompt)
        emit("reviewer", "done", review_result)

        # Track best version
        if review_result["score"] > best_score:
            best_score = review_result["score"]
            best_attempt_report = {
                "attempt": attempt,
                "report": test_report,
                "review": review_result,
            }

        if review_result["passed"]:
            break

        fix_instructions = review_result.get("fix_instructions")

    # Step 7: Deploy
    deployed_url = None
    if not skip_deploy:
        emit("deployer", "running")
        try:
            deployed_url = deploy_to_vercel()
            emit("deployer", "done", {"url": deployed_url})
        except RuntimeError as e:
            emit("deployer", "failed", {"error": str(e)})

    elapsed = round(time.time() - pipeline_start, 1)

    final_report = best_attempt_report or {}
    return {
        "url": deployed_url,
        "scores": final_report.get("review", {}).get("score", 0),
        "lighthouse": final_report.get("report", {}).get("lighthouse", {}),
        "attempts": attempt,
        "passed": review_result["passed"] if "review_result" in dir() else False,
        "time_seconds": elapsed,
    }
