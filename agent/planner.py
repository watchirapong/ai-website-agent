"""Agent 1 — Website Architect: JSON plan parsing and validation utilities.

LLM interaction is handled by CrewAI. This module provides post-processing
for the planner agent's output.
"""

import json


def parse_plan(raw: str) -> dict:
    """Parse raw LLM output into a structured site plan dict.

    Returns a dict with keys: site_name, pages, components, style.
    """
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in planner output")
        plan = json.loads(raw[start:end])

    required = ["site_name", "pages", "components", "style"]
    for key in required:
        if key not in plan:
            raise ValueError(f"Plan missing required key: {key}")

    return plan
