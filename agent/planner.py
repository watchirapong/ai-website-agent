"""Agent 1 — Website Architect: JSON plan parsing and validation utilities.

LLM interaction is handled by CrewAI. This module provides post-processing
for the planner agent's output.
"""

import json
import re


def _extract_json_block(raw: str) -> str:
    """Extract the most likely JSON object block from raw model output."""
    text = (raw or "").strip()

    # Prefer full fenced body (do not use non-greedy ``{...}`` — breaks nested objects).
    fence = re.search(r"```(?:json)?\s*\r?\n([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        inner = fence.group(1).strip()
        if inner.startswith("{"):
            return inner

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in planner output")
    return text[start : end + 1]


def _cleanup_json_like(text: str) -> str:
    """Normalize common LLM JSON mistakes (trailing commas, smart quotes)."""
    s = text.strip()
    # Normalize smart quotes to standard double quote.
    s = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
    # Remove trailing commas before object/array closers.
    s = re.sub(r",\s*([}\]])", r"\1", s)
    # Add likely-missing commas between adjacent JSON values and next keys across lines.
    # Example:  "foo"\n  "bar": 123  -> "foo",\n  "bar": 123
    s = re.sub(r'(["}\]0-9])\s*\n(\s*")', r"\1,\n\2", s)
    # Add likely-missing commas before array/object starts when key follows value.
    s = re.sub(r'(["}\]0-9])\s*(\s*")', r"\1,\2", s)
    # After a closing brace (object in array), often missing comma before next "{"
    s = re.sub(r"}\s*\n(\s*\{)", r"},\n\1", s)
    return s


def parse_plan(raw: str) -> dict:
    """Parse raw LLM output into a structured site plan dict.

    Returns a dict with keys: site_name, pages, components, style.
    """
    candidate = _extract_json_block(raw)
    attempts = [candidate]
    cleaned_once = _cleanup_json_like(candidate)
    if cleaned_once != candidate:
        attempts.append(cleaned_once)
    cleaned_twice = _cleanup_json_like(cleaned_once)
    if cleaned_twice not in attempts:
        attempts.append(cleaned_twice)

    last_error: Exception | None = None
    plan = None
    for payload in attempts:
        try:
            plan = json.loads(payload)
            break
        except json.JSONDecodeError as e:
            last_error = e

    if plan is None:
        raise ValueError(f"Planner JSON parse failed: {last_error}")

    required = ["site_name", "pages", "components", "style"]
    for key in required:
        if key not in plan:
            raise ValueError(f"Plan missing required key: {key}")

    return plan


def fallback_plan_from_prompt(user_prompt: str) -> dict:
    """Build a safe default plan when planner JSON is unavailable."""
    p = (user_prompt or "").strip()
    site_name = (
        re.sub(r"[^a-z0-9]+", "-", p.lower())[:40].strip("-") or "generated-site"
    )
    sections = ["Hero", "Features", "Contact"]
    if "restaurant" in p.lower():
        sections = ["Hero", "Menu", "Reservation", "Contact"]
    elif "portfolio" in p.lower():
        sections = ["Hero", "Projects", "About", "Contact"]

    return {
        "site_name": site_name,
        "pages": [{"name": "Home", "route": "/", "sections": sections}],
        "components": ["Navbar", "Footer", *sections],
        "style": {
            "theme": "modern",
            "primary_color": "#2563eb",
            "secondary_color": "#0f172a",
            "font": "Inter",
            "mood": "clean and conversion-focused",
        },
        "features": ["responsive layout", "cta section", "contact form"],
    }
