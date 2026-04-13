#!/usr/bin/env python3
"""CLI entry point for the AI Website Agent."""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import config
from agent.crew import run_pipeline


def _print_event(step: str, status: str, detail: dict):
    """Pretty-print pipeline progress events."""
    icons = {
        "running": "...",
        "done": " OK",
        "failed": "ERR",
        "start": ">>>",
        "complete": " OK",
    }
    icon = icons.get(status, "   ")

    step_labels = {
        "planner": "Planner  ",
        "developer": "Developer",
        "build": "Build    ",
        "server": "Server   ",
        "tester": "Tester   ",
        "reviewer": "Reviewer ",
        "deployer": "Deployer ",
        "attempt": "Attempt  ",
        "pipeline": "Pipeline ",
    }
    label = step_labels.get(step, step.ljust(9))

    if step == "attempt" and status == "start":
        attempt = detail.get("attempt", "?")
        mx = detail.get("max", "?")
        print(f"\n--- Attempt {attempt}/{mx} {'─' * 43}")
        return

    msg = ""
    if step == "planner" and status == "done":
        plan = detail.get("plan", {})
        pages = len(plan.get("pages", []))
        comps = len(plan.get("components", []))
        mood = plan.get("style", {}).get("mood", "")
        msg = f"Parsed: {pages} pages, {comps} components, {mood}"
    elif step == "developer" and status == "done":
        count = detail.get("count", 0)
        msg = f"Generated {count} files"
    elif step == "build" and status == "done":
        msg = "next build passed"
    elif step == "build" and status == "failed":
        msg = f"Build failed: {detail.get('output', '')[:80]}"
    elif step == "server" and status == "done":
        msg = f"Running on {detail.get('url', '')}"
    elif step == "tester" and status == "done":
        report = detail.get("report", {})
        lh = report.get("lighthouse", {})
        msg = (
            f"perf={lh.get('performance', '?')} "
            f"a11y={lh.get('accessibility', '?')} "
            f"bp={lh.get('best_practices', '?')} "
            f"seo={lh.get('seo', '?')}"
        )
    elif step == "reviewer" and status == "done":
        if detail.get("passed"):
            msg = "PASS"
        else:
            issues = detail.get("issues", [])
            msg = f"FAIL — {'; '.join(issues[:2])}"
    elif step == "deployer" and status == "done":
        msg = f"Live: {detail.get('url', '')}"
    elif step == "deployer" and status == "failed":
        msg = f"Deploy failed: {detail.get('error', '')[:80]}"
    elif step == "pipeline" and status == "complete":
        return  # handled in main
    else:
        msg = status

    print(f"  [{icon}] {label}  {msg}")


def main():
    parser = argparse.ArgumentParser(
        description="AI Website Agent — generate, test & deploy websites from a prompt"
    )
    parser.add_argument("prompt", help="Describe the website you want to build")
    parser.add_argument("--no-deploy", action="store_true", help="Skip deployment")
    parser.add_argument("--max-retries", type=int, default=None, help="Max retry attempts")
    parser.add_argument("--port", type=int, default=None, help="Preview server port")

    args = parser.parse_args()

    if args.max_retries is not None:
        config.MAX_RETRIES = args.max_retries
    if args.port is not None:
        config.PREVIEW_PORT = args.port

    print(f"\nStarting AI Website Agent...")
    print(f'Prompt: "{args.prompt}"')

    result = run_pipeline(
        user_prompt=args.prompt,
        on_event=_print_event,
        skip_deploy=args.no_deploy,
    )

    print(f"\n--- Report {'─' * 48}")
    print(f"  Attempts:       {result.get('attempts', '?')}/{config.MAX_RETRIES}")
    lh = result.get("lighthouse", {})
    print(
        f"  Final scores:   "
        f"perf={lh.get('performance', '?')} "
        f"a11y={lh.get('accessibility', '?')} "
        f"bp={lh.get('best_practices', '?')} "
        f"seo={lh.get('seo', '?')}"
    )
    if result.get("url"):
        print(f"  Live URL:       {result['url']}")
    print(f"  Screenshots:    ./reports/screenshots/")
    print(f"  Full report:    ./reports/test_report.json")
    print(f"  Time:           {result.get('time_seconds', 0)}s")
    print()


if __name__ == "__main__":
    main()
