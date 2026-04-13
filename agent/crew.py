"""CrewAI pipeline: orchestrates agents through the generate -> test -> review loop."""

import json
import shutil
import time
from typing import Callable

from crewai import Agent, Task, Crew, Process

from agent.config import (
    OUTPUT_DIR,
    MAX_RETRIES,
    PROMPTS_DIR,
    ensure_dirs,
    get_llm,
)
from agent.planner import parse_plan
from agent.reviewer import check_thresholds, compute_score
from agent.tools import (
    write_website_files,
    validate_build,
    test_website,
    deploy_to_vercel_tool,
)


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def _clean_output():
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _build_agents(llm):
    """Create the five CrewAI agents."""

    planner_backstory = _load_prompt("system_planner.txt")
    developer_backstory = _load_prompt("system_generator.txt")
    reviewer_backstory = _load_prompt("system_reviewer.txt")

    planner = Agent(
        role="Website Architect",
        goal="Analyze a user's website request and produce a structured JSON site plan with pages, components, style, and features.",
        backstory=planner_backstory,
        llm=llm,
        verbose=True,
    )

    developer = Agent(
        role="Senior Next.js Developer",
        goal="Generate a complete, working Next.js 14 website from a site plan, then write all files to disk and validate the build.",
        backstory=developer_backstory,
        llm=llm,
        tools=[write_website_files, validate_build],
        verbose=True,
    )

    tester = Agent(
        role="QA Engineer",
        goal="Run the test_website tool to test the generated site and return the JSON test report.",
        backstory=(
            "You are a meticulous QA engineer. Call the test_website tool once "
            "to run the full test suite (server start, screenshots, Lighthouse audit, server stop). "
            "Return the JSON test report exactly as the tool outputs it."
        ),
        llm=llm,
        tools=[test_website],
        verbose=True,
    )

    reviewer = Agent(
        role="Tech Lead",
        goal="Review test results against quality thresholds and provide specific, actionable fix instructions if any checks fail.",
        backstory=reviewer_backstory,
        llm=llm,
        verbose=True,
    )

    deployer = Agent(
        role="DevOps Engineer",
        goal="Deploy the approved website to Vercel and return the live production URL.",
        backstory=(
            "You are a DevOps engineer responsible for deploying Next.js sites to Vercel. "
            "Use the deploy_to_vercel tool to push the site to production."
        ),
        llm=llm,
        tools=[deploy_to_vercel_tool],
        verbose=True,
    )

    return planner, developer, tester, reviewer, deployer


def run_pipeline(
    user_prompt: str,
    on_event: Callable[[str, str, dict], None] | None = None,
    skip_deploy: bool = False,
) -> dict:
    """Run the full CrewAI agent pipeline.

    Args:
        user_prompt: The user's website description.
        on_event: Optional callback(step, status, detail) for progress updates.
        skip_deploy: If True, skip the deployment step.

    Returns:
        dict with keys: url, scores, lighthouse, attempts, passed, time_seconds.
    """
    ensure_dirs()
    llm = get_llm()

    def emit(step: str, status: str, detail: dict | None = None):
        if on_event:
            on_event(step, status, detail or {})

    pipeline_start = time.time()
    best_score = 0
    best_attempt_report: dict | None = None

    planner_agent, developer_agent, tester_agent, reviewer_agent, deployer_agent = _build_agents(llm)

    # ── Step 1: Plan ──────────────────────────────────────────────
    emit("planner", "running")

    plan_task = Task(
        description=(
            f"Analyze this website request and produce a structured JSON site plan.\n\n"
            f"User request: {user_prompt}\n\n"
            f"Return ONLY valid JSON with keys: site_name, pages, components, style, features."
        ),
        expected_output="A valid JSON object with site_name, pages, components, style, and features.",
        agent=planner_agent,
    )

    plan_crew = Crew(
        agents=[planner_agent],
        tasks=[plan_task],
        process=Process.sequential,
        verbose=True,
    )

    plan_result = plan_crew.kickoff()
    plan = parse_plan(plan_result.raw)
    emit("planner", "done", {"plan": plan})

    # ── Steps 2-6: Generate → Build → Test → Review (retry loop) ─
    fix_instructions = None
    review_result = {"passed": False, "score": 0, "issues": [], "fix_instructions": None}
    attempt = 0

    for attempt in range(1, MAX_RETRIES + 1):
        emit("attempt", "start", {"attempt": attempt, "max": MAX_RETRIES})

        # Step 2: Generate code
        _clean_output()
        emit("developer", "running")

        dev_description = (
            f"Generate a complete Next.js 14 website based on this site plan:\n\n"
            f"{json.dumps(plan, indent=2)}\n\n"
            f"After generating all the code, you MUST call the write_website_files tool "
            f"with your complete output to write the files to disk. "
            f"Then call the validate_build tool to run npm install and next build."
        )
        if fix_instructions:
            dev_description += (
                f"\n\nPREVIOUS REVIEW FEEDBACK — fix these issues:\n{fix_instructions}"
            )

        dev_task = Task(
            description=dev_description,
            expected_output="JSON summary of written files and build result.",
            agent=developer_agent,
        )

        dev_crew = Crew(
            agents=[developer_agent],
            tasks=[dev_task],
            process=Process.sequential,
            verbose=True,
        )

        dev_result = dev_crew.kickoff()
        emit("developer", "done", {"output": dev_result.raw[:500]})

        # Check if build passed by looking at the output
        build_output = dev_result.raw
        if "success" in build_output.lower() and "false" in build_output.lower():
            emit("build", "failed", {"output": build_output[:500]})
            fix_instructions = f"Build failed. Developer output:\n{build_output[:1000]}"
            continue
        emit("build", "done")

        # Step 4: Test
        emit("tester", "running")

        test_task = Task(
            description=(
                "Test the generated website by calling the test_website tool. "
                "It handles everything automatically (starts server, runs tests, stops server). "
                "Return the complete JSON test report from the tool output."
            ),
            expected_output="Complete JSON test report with lighthouse scores, screenshots, console_errors, broken_links, and load_time_ms.",
            agent=tester_agent,
        )

        test_crew = Crew(
            agents=[tester_agent],
            tasks=[test_task],
            process=Process.sequential,
            verbose=True,
        )

        test_result = test_crew.kickoff()

        # Parse the test report from the tester's output
        try:
            test_report = json.loads(test_result.raw)
        except (json.JSONDecodeError, ValueError):
            raw = test_result.raw
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > 0:
                try:
                    test_report = json.loads(raw[start:end])
                except json.JSONDecodeError:
                    test_report = {"lighthouse": {"performance": 0, "accessibility": 0, "best_practices": 0, "seo": 0}}
            else:
                test_report = {"lighthouse": {"performance": 0, "accessibility": 0, "best_practices": 0, "seo": 0}}

        emit("tester", "done", {"report": test_report})

        # Step 5: Review
        emit("reviewer", "running")

        threshold_issues = check_thresholds(test_report)
        overall_score = compute_score(test_report)

        if not threshold_issues:
            review_result = {
                "passed": True,
                "score": overall_score,
                "issues": [],
                "fix_instructions": None,
            }
            emit("reviewer", "done", review_result)
        else:
            review_task = Task(
                description=(
                    f"Review these test results and provide specific fix instructions.\n\n"
                    f"Original user request: {user_prompt}\n\n"
                    f"Test report:\n{json.dumps(test_report, indent=2)}\n\n"
                    f"Failed checks:\n" + "\n".join(f"- {i}" for i in threshold_issues) +
                    f"\n\nProvide a numbered list of specific, actionable fixes."
                ),
                expected_output="Numbered list of specific fixes with categories.",
                agent=reviewer_agent,
            )

            review_crew = Crew(
                agents=[reviewer_agent],
                tasks=[review_task],
                process=Process.sequential,
                verbose=True,
            )

            review_crew_result = review_crew.kickoff()
            fix_instructions = review_crew_result.raw

            review_result = {
                "passed": False,
                "score": overall_score,
                "issues": threshold_issues,
                "fix_instructions": fix_instructions,
            }
            emit("reviewer", "done", review_result)

        # Track best version
        if overall_score > best_score:
            best_score = overall_score
            best_attempt_report = {
                "attempt": attempt,
                "report": test_report,
                "review": review_result,
            }

        if review_result["passed"]:
            break

    # ── Step 7: Deploy ────────────────────────────────────────────
    deployed_url = None
    if not skip_deploy:
        emit("deployer", "running")

        deploy_task = Task(
            description="Deploy the generated website to Vercel by calling the deploy_to_vercel tool. Return the live URL.",
            expected_output="The live production URL from Vercel.",
            agent=deployer_agent,
        )

        deploy_crew = Crew(
            agents=[deployer_agent],
            tasks=[deploy_task],
            process=Process.sequential,
            verbose=True,
        )

        try:
            deploy_result = deploy_crew.kickoff()
            try:
                deploy_data = json.loads(deploy_result.raw)
                deployed_url = deploy_data.get("url")
            except (json.JSONDecodeError, ValueError):
                deployed_url = deploy_result.raw.strip()
            emit("deployer", "done", {"url": deployed_url})
        except Exception as e:
            emit("deployer", "failed", {"error": str(e)})

    elapsed = round(time.time() - pipeline_start, 1)

    final_report = best_attempt_report or {}
    return {
        "url": deployed_url,
        "scores": final_report.get("review", {}).get("score", 0),
        "lighthouse": final_report.get("report", {}).get("lighthouse", {}),
        "attempts": attempt,
        "passed": review_result.get("passed", False),
        "time_seconds": elapsed,
    }
