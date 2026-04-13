"""CrewAI custom tools wrapping build, test, and deploy utilities."""

import json
from crewai.tools import tool

from agent.config import OUTPUT_DIR, PREVIEW_PORT
from agent.generator import parse_files_from_response, write_files, ensure_package_json, ensure_configs
from agent.validator import validate
from agent.server import start as _start_server, stop as _stop_server
from agent.tester import run_tests as _run_tests
from agent.deployer import deploy_to_vercel as _deploy


@tool("write_website_files")
def write_website_files(raw_llm_output: str) -> str:
    """Parse the Developer agent's LLM output into files and write them to disk.
    Call this tool with the COMPLETE code output containing fenced code blocks.
    Returns a JSON summary of written files."""
    import shutil
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = parse_files_from_response(raw_llm_output)
    files = ensure_package_json(files)
    files = ensure_configs(files)
    written = write_files(files)
    return json.dumps({"files_written": len(written), "paths": written})


@tool("validate_build")
def validate_build(dummy: str = "") -> str:
    """Run npm install and next build on the generated site.
    Returns JSON with success status and build output."""
    ok, output = validate()
    return json.dumps({"success": ok, "output": output[:2000]})


@tool("test_website")
def test_website(dummy: str = "") -> str:
    """Start the preview server, run full test suite (Playwright screenshots +
    Lighthouse audit), then stop the server. Returns the complete JSON test report.
    Call this tool once — it handles the entire testing workflow automatically."""
    try:
        url = _start_server()
    except TimeoutError as e:
        return json.dumps({"error": f"Server failed to start: {e}"})

    try:
        report = _run_tests(url)
    finally:
        _stop_server()

    return json.dumps(report, default=str)


@tool("deploy_to_vercel")
def deploy_to_vercel_tool(dummy: str = "") -> str:
    """Deploy the generated site to Vercel production.
    Returns the live production URL."""
    try:
        url = _deploy()
        return json.dumps({"success": True, "url": url})
    except RuntimeError as e:
        return json.dumps({"success": False, "error": str(e)})
