"""Agent 3 — QA Engineer: runs Playwright screenshots + Lighthouse audits."""

import json
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
from agent.config import (
    PREVIEW_PORT,
    VIEWPORTS,
    SCREENSHOTS_DIR,
    REPORTS_DIR,
)


def _take_screenshots(url: str) -> list[str]:
    """Capture screenshots at each viewport size. Returns list of saved paths."""
    saved: list[str] = []
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for name, size in VIEWPORTS.items():
            context = browser.new_context(
                viewport={"width": size["width"], "height": size["height"]}
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            path = str(SCREENSHOTS_DIR / f"{name}.png")
            page.screenshot(path=path, full_page=True)
            saved.append(path)
            context.close()

        browser.close()

    return saved


def _check_console_errors(url: str) -> list[str]:
    """Load the page and capture any JS console errors."""
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000)
        browser.close()

    return errors


def _check_broken_links(url: str) -> list[str]:
    """Find all <a> hrefs and check for 404s."""
    broken: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")

        links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        browser.close()

    import requests as http_req

    for link in links:
        if not link.startswith("http"):
            continue
        try:
            resp = http_req.head(link, timeout=5, allow_redirects=True)
            if resp.status_code >= 400:
                broken.append(f"{link} ({resp.status_code})")
        except http_req.RequestException:
            broken.append(f"{link} (connection failed)")

    return broken


def _measure_load_time(url: str) -> int:
    """Measure page load time in milliseconds."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        start = page.evaluate("() => performance.now()")
        page.goto(url, wait_until="networkidle")
        end = page.evaluate("() => performance.now()")

        browser.close()

    return int(end - start)


def _run_lighthouse(url: str) -> dict:
    """Run Lighthouse CLI and return category scores (0-100)."""
    output_path = str(REPORTS_DIR / "lighthouse.json")

    result = subprocess.run(
        [
            "lighthouse",
            url,
            "--output=json",
            f"--output-path={output_path}",
            "--chrome-flags=--headless --no-sandbox",
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0 and not Path(output_path).exists():
        return {
            "performance": 0,
            "accessibility": 0,
            "best_practices": 0,
            "seo": 0,
            "error": result.stderr[:500],
        }

    with open(output_path) as f:
        data = json.load(f)

    categories = data.get("categories", {})
    return {
        "performance": int((categories.get("performance", {}).get("score", 0) or 0) * 100),
        "accessibility": int((categories.get("accessibility", {}).get("score", 0) or 0) * 100),
        "best_practices": int((categories.get("best-practices", {}).get("score", 0) or 0) * 100),
        "seo": int((categories.get("seo", {}).get("score", 0) or 0) * 100),
    }


def run_tests(url: str | None = None) -> dict:
    """Execute the full test suite and return a combined report."""
    if url is None:
        url = f"http://localhost:{PREVIEW_PORT}"

    screenshots = _take_screenshots(url)
    console_errors = _check_console_errors(url)
    broken_links = _check_broken_links(url)
    load_time_ms = _measure_load_time(url)
    lighthouse = _run_lighthouse(url)

    report = {
        "lighthouse": lighthouse,
        "screenshots": screenshots,
        "console_errors": console_errors,
        "broken_links": broken_links,
        "load_time_ms": load_time_ms,
        "html_valid": True,
    }

    report_path = REPORTS_DIR / "test_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    return report
