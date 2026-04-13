"""CrewAI pipeline: orchestrates agents through the generate -> test -> review loop."""

import json
import time
import textwrap
from typing import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from crewai import Agent, Task, Crew, Process

import agent.config as cfg
from agent.config import (
    BASE_OUTPUT_DIR,
    MAX_RETRIES,
    PIPELINE_STEP_TIMEOUT_SECONDS,
    PLANNER_TIMEOUT_SECONDS,
    DEVELOPER_TIMEOUT_SECONDS,
    TESTER_TIMEOUT_SECONDS,
    REVIEWER_TIMEOUT_SECONDS,
    DEPLOYER_TIMEOUT_SECONDS,
    ENABLE_TESTER,
    ENABLE_REVIEWER,
    LLM_EMPTY_RESULT_RETRIES,
    LLM_EMPTY_RESULT_BACKOFF_SECONDS,
    PROMPTS_DIR,
    ensure_dirs,
    get_llm,
)
from agent.fs_cleanup import reset_output_directory
from agent.generator import materialize_site_from_raw
from agent.planner import parse_plan, fallback_plan_from_prompt
from agent.reviewer import check_thresholds, compute_score
from agent.validator import validate as run_validate_build
from agent.tools import (
    write_website_files,
    validate_build,
    test_website,
    deploy_to_vercel_tool,
)


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _clean_output():
    resolved = reset_output_directory(cfg.OUTPUT_DIR, stop_api_preview=True)
    if resolved.resolve() != cfg.OUTPUT_DIR.resolve():
        cfg.set_output_dir(resolved)


def _kickoff_with_timeout(
    crew: Crew,
    step_name: str,
    timeout_seconds: int = PIPELINE_STEP_TIMEOUT_SECONDS,
    on_empty_retry: Callable[[dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
):
    """Run crew kickoff with a hard timeout to avoid indefinite hangs.

    Polls ``should_stop`` every ~2s so Stop can interrupt a long LLM call.

    Important: we intentionally do not block executor shutdown on timeout. CrewAI
    may keep provider calls alive; waiting for thread join here can freeze the
    whole pipeline loop and hide retry/cancel progress from the UI.
    """
    for retry_idx in range(LLM_EMPTY_RESULT_RETRIES + 1):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(crew.kickoff)
        try:
            deadline = time.time() + timeout_seconds
            result = None
            while True:
                if should_stop and should_stop():
                    raise RuntimeError("Cancelled by user")
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(
                        f"{step_name} timed out after {timeout_seconds}s"
                    )
                try:
                    result = future.result(timeout=min(2.0, remaining))
                    break
                except FuturesTimeoutError:
                    continue
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        raw = getattr(result, "raw", None)
        raw_text = (raw if isinstance(raw, str) else "").strip()
        if result is not None and raw_text:
            return result

        if retry_idx < LLM_EMPTY_RESULT_RETRIES:
            backoff = LLM_EMPTY_RESULT_BACKOFF_SECONDS * (2 ** retry_idx)
            if on_empty_retry:
                on_empty_retry(
                    {
                        "step": step_name,
                        "retry": retry_idx + 1,
                        "max_retries": LLM_EMPTY_RESULT_RETRIES,
                        "sleep_seconds": backoff,
                    }
                )
            end_sleep = time.time() + backoff
            while time.time() < end_sleep:
                if should_stop and should_stop():
                    raise RuntimeError("Cancelled by user")
                time.sleep(min(0.25, end_sleep - time.time()))
            continue

        raise RuntimeError(
            f"{step_name} returned empty LLM response after {LLM_EMPTY_RESULT_RETRIES + 1} attempt(s)"
        )

    raise RuntimeError(f"{step_name} kickoff exhausted unexpectedly")


def _short(value: str, limit: int = 240) -> str:
    v = (value or "").strip().replace("\r", " ").replace("\n", " ")
    return textwrap.shorten(v, width=limit, placeholder="...")


def _required_paths_from_plan(plan: dict) -> list[str]:
    """Derive expected App Router file paths from plan pages (for developer checklist)."""
    base = ["app/page.tsx", "app/layout.tsx", "app/globals.css"]
    seen = set(base)
    for page in plan.get("pages") or []:
        if not isinstance(page, dict):
            continue
        route = str(page.get("route") or "/").strip() or "/"
        if route in ("/", ""):
            continue
        parts = [seg for seg in route.strip("/").split("/") if seg]
        if not parts:
            continue
        rel = "/".join(["app", *parts, "page.tsx"])
        if rel not in seen:
            seen.add(rel)
            base.append(rel)
    return base


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
    wait_for_approval: Callable[[str, dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    """Run the full CrewAI agent pipeline.

    Args:
        user_prompt: The user's website description.
        on_event: Optional callback(step, status, detail) for progress updates.
        skip_deploy: If True, skip the deployment step.
        wait_for_approval: Optional callback invoked before each major step starts.

    Returns:
        dict with keys: url, scores, lighthouse, attempts, passed, time_seconds,
        output_dir (absolute path to the final generated site on disk).
    """
    ensure_dirs()
    llm = get_llm()

    def emit(step: str, status: str, detail: dict | None = None):
        if on_event:
            on_event(step, status, detail or {})

    def require_approval(step: str, detail: dict | None = None):
        if wait_for_approval:
            wait_for_approval(step, detail or {})

    def ensure_not_stopped():
        if should_stop and should_stop():
            raise RuntimeError("Cancelled by user")

    pipeline_start = time.time()
    best_score = 0
    best_attempt_report: dict | None = None

    planner_agent, developer_agent, tester_agent, reviewer_agent, deployer_agent = _build_agents(llm)

    # ── Step 1: Plan ──────────────────────────────────────────────
    ensure_not_stopped()
    emit(
        "trace",
        "decision",
        {
            "agent": "planner",
            "why": "Parse user intent into a strict site plan JSON before code generation.",
            "input_preview": _short(user_prompt, 300),
            "timeout_seconds": PLANNER_TIMEOUT_SECONDS,
        },
    )
    require_approval("planner")
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

    planner_detail: dict
    try:
        ensure_not_stopped()
        plan_result = _kickoff_with_timeout(
            plan_crew,
            "planner",
            timeout_seconds=PLANNER_TIMEOUT_SECONDS,
            on_empty_retry=lambda info: emit(
                "trace",
                "result",
                {
                    "agent": "planner",
                    "decision": "empty_llm_response_retry",
                    **info,
                },
            ),
            should_stop=should_stop,
        )
        emit(
            "trace",
            "result",
            {
                "agent": "planner",
                "raw_output_preview": _short(plan_result.raw, 320),
            },
        )
        try:
            plan = parse_plan(plan_result.raw)
            planner_detail = {"plan": plan}
        except Exception as e:
            plan = fallback_plan_from_prompt(user_prompt)
            planner_detail = {
                "plan": plan,
                "fallback_used": True,
                "fallback_reason": str(e),
            }
            emit(
                "trace",
                "result",
                {
                    "agent": "planner",
                    "decision": "fallback_plan_used",
                    "reason": str(e),
                },
            )
    except TimeoutError as e:
        plan = fallback_plan_from_prompt(user_prompt)
        planner_detail = {
            "plan": plan,
            "fallback_used": True,
            "fallback_reason": str(e),
        }
        emit(
            "trace",
            "result",
            {
                "agent": "planner",
                "decision": "fallback_plan_used",
                "reason": str(e),
            },
        )
    emit("planner", "done", planner_detail)

    # ── Steps 2-6: Generate → Build → Test → Review (retry loop) ─
    fix_instructions = None
    review_result = {"passed": False, "score": 0, "issues": [], "fix_instructions": None}
    attempt = 0

    for attempt in range(1, MAX_RETRIES + 1):
        ensure_not_stopped()
        attempt_output_dir = BASE_OUTPUT_DIR.parent / f"{BASE_OUTPUT_DIR.name}_attempt_{attempt}"
        cfg.set_output_dir(attempt_output_dir)
        emit("attempt", "start", {"attempt": attempt, "max": MAX_RETRIES})
        emit(
            "trace",
            "decision",
            {
                "agent": "developer",
                "why": "Generate full Next.js project, then call write_website_files and validate_build.",
                "attempt": attempt,
                "has_fix_feedback": bool(fix_instructions),
                "fix_preview": _short(fix_instructions or "", 260),
                "timeout_seconds": DEVELOPER_TIMEOUT_SECONDS,
            },
        )

        # Step 2: Generate code
        _clean_output()
        resolved_out = cfg.OUTPUT_DIR.resolve()
        if resolved_out != attempt_output_dir.resolve():
            emit(
                "trace",
                "result",
                {
                    "agent": "runtime",
                    "decision": "output_dir_fallback",
                    "reason": "output_cleanup_used_alternate_path",
                    "planned_path": str(attempt_output_dir.resolve()),
                    "actual_path": str(resolved_out),
                    "attempt": attempt,
                },
            )
        emit(
            "runtime",
            "output_dir",
            {"attempt": attempt, "path": str(resolved_out)},
        )
        ensure_not_stopped()
        require_approval("developer", {"attempt": attempt, "max": MAX_RETRIES})
        emit("developer", "running")

        req_paths = _required_paths_from_plan(plan)
        checklist = "\n".join(f"- `{p}`" for p in req_paths)
        dev_description = (
            f"Generate a complete Next.js 14 website based on this site plan:\n\n"
            f"{json.dumps(plan, indent=2)}\n\n"
            f"Required file paths from this plan (include every one; use exact paths):\n"
            f"{checklist}\n\n"
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

        try:
            ensure_not_stopped()
            dev_result = _kickoff_with_timeout(
                dev_crew,
                "developer",
                timeout_seconds=DEVELOPER_TIMEOUT_SECONDS,
                on_empty_retry=lambda info: emit(
                    "trace",
                    "result",
                    {
                        "agent": "developer",
                        "decision": "empty_llm_response_retry",
                        "attempt": attempt,
                        **info,
                    },
                ),
                should_stop=should_stop,
            )
        except TimeoutError as e:
            emit("developer", "failed", {"error": str(e)})
            emit(
                "trace",
                "result",
                {"agent": "developer", "status": "timeout", "error": str(e)},
            )
            fix_instructions = (
                f"Developer step timed out. Keep output concise and always call tools once. Error: {e}"
            )
            continue
        emit(
            "trace",
            "result",
            {
                "agent": "developer",
                "raw_output_preview": _short(dev_result.raw, 320),
            },
        )

        site_name = plan.get("site_name")
        if site_name is not None and not isinstance(site_name, str):
            site_name = str(site_name)
        plan_style = plan.get("style") if isinstance(plan.get("style"), dict) else None
        try:
            mat = materialize_site_from_raw(
                dev_result.raw or "",
                reset_output_dir=True,
                site_name=site_name,
                plan_style=plan_style,
            )
        except ValueError as e:
            emit("developer", "failed", {"error": str(e)})
            emit(
                "trace",
                "result",
                {
                    "agent": "developer",
                    "materialized": False,
                    "error": str(e),
                },
            )
            fix_instructions = (
                "Could not parse file fences from your output. For each file use:\n"
                "```app/page.tsx\n// file content\n```\n"
                "The opening fence line must be the relative path (e.g. app/page.tsx), not bare ```tsx. "
                "Put the path on that same line if you use a language-only fence."
            )
            continue

        paths_preview = mat["paths"][:12] if isinstance(mat.get("paths"), list) else []
        stub_paths = mat.get("stub_paths") or []
        if stub_paths:
            emit(
                "trace",
                "result",
                {
                    "agent": "developer",
                    "stub_files_added": [str(p) for p in stub_paths],
                },
            )
        emit(
            "trace",
            "result",
            {
                "agent": "developer",
                "materialized_from_raw": True,
                "files_written": mat.get("files_written", 0),
                "paths_preview": [str(p) for p in paths_preview],
            },
        )
        emit(
            "developer",
            "done",
            {
                "files_written": mat.get("files_written", 0),
                "stub_files_added": stub_paths,
                "output_preview": _short(dev_result.raw, 500),
            },
        )

        build_ok, build_output = run_validate_build()
        if not build_ok:
            emit("build", "failed", {"output": build_output[:2000]})
            emit(
                "trace",
                "decision",
                {
                    "agent": "review-loop",
                    "why": "npm install or next build failed after materializing files.",
                    "build_output_preview": _short(build_output, 320),
                },
            )
            fix_instructions = f"Build failed.\n{build_output[:1500]}"
            continue
        emit("build", "done", {"output": build_output[:500]})

        # Step 4: Test
        if not ENABLE_TESTER:
            test_report = {}
            emit(
                "tester",
                "done",
                {
                    "skipped": True,
                    "reason": "Tester disabled by ENABLE_TESTER=0",
                    "report": test_report,
                },
            )
            emit(
                "trace",
                "result",
                {
                    "agent": "tester",
                    "decision": "skipped",
                    "reason": "Tester disabled by ENABLE_TESTER=0",
                },
            )
        else:
            require_approval("tester", {"attempt": attempt, "max": MAX_RETRIES})
            ensure_not_stopped()
            emit("tester", "running")
            emit(
                "trace",
                "decision",
                {
                    "agent": "tester",
                    "why": "Run tool-driven quality checks (screenshots, Lighthouse, console, links, load time).",
                    "attempt": attempt,
                    "timeout_seconds": TESTER_TIMEOUT_SECONDS,
                },
            )

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

            try:
                ensure_not_stopped()
                test_result = _kickoff_with_timeout(
                    test_crew,
                    "tester",
                    timeout_seconds=TESTER_TIMEOUT_SECONDS,
                    on_empty_retry=lambda info: emit(
                        "trace",
                        "result",
                        {
                            "agent": "tester",
                            "decision": "empty_llm_response_retry",
                            "attempt": attempt,
                            **info,
                        },
                    ),
                    should_stop=should_stop,
                )
            except TimeoutError as e:
                emit("tester", "failed", {"error": str(e)})
                emit(
                    "trace",
                    "result",
                    {"agent": "tester", "status": "timeout", "error": str(e)},
                )
                fix_instructions = f"Tester step timed out: {e}"
                continue

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
            emit(
                "trace",
                "result",
                {
                    "agent": "tester",
                    "lighthouse": test_report.get("lighthouse", {}),
                    "console_error_count": len(test_report.get("console_errors", [])),
                    "broken_link_count": len(test_report.get("broken_links", [])),
                    "load_time_ms": test_report.get("load_time_ms"),
                },
            )

        # Step 5: Review
        if not ENABLE_REVIEWER:
            overall_score = compute_score(test_report)
            review_result = {
                "passed": True,
                "score": overall_score,
                "issues": [],
                "fix_instructions": None,
                "skipped": True,
                "reason": "Reviewer disabled by ENABLE_REVIEWER=0",
            }
            emit("reviewer", "done", review_result)
            emit(
                "trace",
                "result",
                {
                    "agent": "reviewer",
                    "decision": "skipped",
                    "reason": "Reviewer disabled by ENABLE_REVIEWER=0",
                },
            )
            if overall_score > best_score:
                best_score = overall_score
                best_attempt_report = {
                    "attempt": attempt,
                    "report": test_report,
                    "review": review_result,
                }
            break

        require_approval("reviewer", {"attempt": attempt, "max": MAX_RETRIES})
        ensure_not_stopped()
        emit("reviewer", "running")

        threshold_issues = check_thresholds(test_report)
        overall_score = compute_score(test_report)
        emit(
            "trace",
            "decision",
            {
                "agent": "reviewer",
                "why": "Evaluate thresholds and decide PASS vs RETRY.",
                "score": overall_score,
                "issues": threshold_issues,
                "timeout_seconds": REVIEWER_TIMEOUT_SECONDS,
            },
        )

        if not threshold_issues:
            review_result = {
                "passed": True,
                "score": overall_score,
                "issues": [],
                "fix_instructions": None,
            }
            emit("reviewer", "done", review_result)
            emit("trace", "result", {"agent": "reviewer", "decision": "pass"})
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

            review_crew_result = _kickoff_with_timeout(
                review_crew,
                "reviewer",
                timeout_seconds=REVIEWER_TIMEOUT_SECONDS,
                on_empty_retry=lambda info: emit(
                    "trace",
                    "result",
                    {
                        "agent": "reviewer",
                        "decision": "empty_llm_response_retry",
                        "attempt": attempt,
                        **info,
                    },
                ),
                should_stop=should_stop,
            )
            fix_instructions = review_crew_result.raw

            review_result = {
                "passed": False,
                "score": overall_score,
                "issues": threshold_issues,
                "fix_instructions": fix_instructions,
            }
            emit("reviewer", "done", review_result)
            emit(
                "trace",
                "result",
                {
                    "agent": "reviewer",
                    "decision": "retry",
                    "issues": threshold_issues,
                    "fix_instructions_preview": _short(fix_instructions, 320),
                },
            )

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
        ensure_not_stopped()
        local_deploy = cfg.DEPLOY_TARGET == "local"
        emit(
            "trace",
            "decision",
            {
                "agent": "deployer",
                "why": (
                    "Serve the site on this machine only (127.0.0.1) via next start."
                    if local_deploy
                    else "Deploy to Vercel (public URL) when DEPLOY_TARGET=vercel."
                ),
                "deploy_target": cfg.DEPLOY_TARGET,
                "timeout_seconds": DEPLOYER_TIMEOUT_SECONDS,
            },
        )
        require_approval("deployer")
        emit("deployer", "running")

        if local_deploy:
            try:
                ensure_not_stopped()
                from agent.deployer import deploy_local_server

                deployed_url = deploy_local_server()
                emit(
                    "deployer",
                    "done",
                    {"url": deployed_url, "local_only": True},
                )
            except Exception as e:
                emit("deployer", "failed", {"error": str(e)})
        else:
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
                ensure_not_stopped()
                deploy_result = _kickoff_with_timeout(
                    deploy_crew,
                    "deployer",
                    timeout_seconds=DEPLOYER_TIMEOUT_SECONDS,
                    on_empty_retry=lambda info: emit(
                        "trace",
                        "result",
                        {
                            "agent": "deployer",
                            "decision": "empty_llm_response_retry",
                            **info,
                        },
                    ),
                    should_stop=should_stop,
                )
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
        "output_dir": str(cfg.OUTPUT_DIR.resolve()),
    }
