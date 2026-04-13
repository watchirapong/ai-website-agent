"""CrewAI custom tools wrapping build, test, and deploy utilities."""

import json
import logging
from crewai.tools import tool

import agent.config as cfg
from agent.generator import materialize_site_from_raw
from agent.validator import validate
from agent.server import start as _start_server, stop as _stop_server
from agent.tester import run_tests as _run_tests
from agent.deployer import deploy_to_vercel as _deploy

logger = logging.getLogger("agent.tools")


@tool("write_website_files")
def write_website_files(raw_llm_output: str) -> str:
    """Parse the Developer agent's LLM output into files and write them to disk.
    Call this tool with the COMPLETE code output containing fenced code blocks.
    Returns a JSON summary of written files."""
    logger.info(
        "[tool:write_website_files] input_chars=%s input_preview=%s",
        len(raw_llm_output or ""),
        (raw_llm_output or "")[:220].replace("\n", " "),
    )
    result = materialize_site_from_raw(raw_llm_output or "", reset_output_dir=True)
    logger.info("[tool:write_website_files] output=%s", json.dumps(result, default=str)[:500])
    return json.dumps(result)


@tool("validate_build")
def validate_build(dummy: str = "") -> str:
    """Run npm install and next build on the generated site.
    Returns JSON with success status and build output."""
    ok, output = validate()
    result = {"success": ok, "output": output[:2000]}
    logger.info("[tool:validate_build] output=%s", json.dumps(result, default=str)[:500])
    return json.dumps(result)


@tool("test_website")
def test_website(dummy: str = "") -> str:
    """Start the preview server, run full test suite (Playwright screenshots +
    Lighthouse audit), then stop the server. Returns the complete JSON test report.
    Call this tool once — it handles the entire testing workflow automatically."""
    try:
        url = _start_server()
    except TimeoutError as e:
        result = {"error": f"Server failed to start: {e}"}
        logger.info("[tool:test_website] output=%s", json.dumps(result, default=str)[:500])
        return json.dumps(result)

    try:
        report = _run_tests(url)
    finally:
        _stop_server()

    logger.info(
        "[tool:test_website] output_summary=%s",
        json.dumps(
            {
                "lighthouse": report.get("lighthouse", {}),
                "console_errors": len(report.get("console_errors", [])),
                "broken_links": len(report.get("broken_links", [])),
                "load_time_ms": report.get("load_time_ms"),
            },
            default=str,
        )[:500],
    )
    return json.dumps(report, default=str)


@tool("deploy_to_vercel")
def deploy_to_vercel_tool(dummy: str = "") -> str:
    """Deploy the generated site to Vercel production.
    Returns the live production URL."""
    try:
        url = _deploy()
        result = {"success": True, "url": url}
        logger.info("[tool:deploy_to_vercel] output=%s", json.dumps(result, default=str))
        return json.dumps(result)
    except RuntimeError as e:
        result = {"success": False, "error": str(e)}
        logger.info("[tool:deploy_to_vercel] output=%s", json.dumps(result, default=str)[:500])
        return json.dumps(result)
