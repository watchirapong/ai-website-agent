"""Agent 1 — Website Architect: parses user prompt into a structured site plan."""

import json
import ollama as ollama_client
from agent.config import OLLAMA_MODEL, OLLAMA_BASE_URL, PROMPTS_DIR


def _load_system_prompt() -> str:
    path = PROMPTS_DIR / "system_planner.txt"
    return path.read_text()


def plan_site(user_prompt: str) -> dict:
    """Convert a free-form user prompt into a structured site plan.

    Returns a dict with keys: site_name, pages, components, style, features.
    """
    system_prompt = _load_system_prompt()

    client = ollama_client.Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        format="json",
    )

    raw = response["message"]["content"]
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        plan = json.loads(raw[start:end])

    required = ["site_name", "pages", "components", "style"]
    for key in required:
        if key not in plan:
            raise ValueError(f"Plan missing required key: {key}")

    return plan
