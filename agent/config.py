import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# --- LLM ---
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
if ANTHROPIC_API_KEY:
    # CrewAI's Anthropic client treats api_key="" as "set" and skips reading ANTHROPIC_API_KEY from the env.
    os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

# --- Ports ---
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "3001"))
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
PREVIEW_PORT = int(os.getenv("PREVIEW_PORT", "3000"))

# --- Paths ---
OUTPUT_DIR = BASE_DIR / "output"
REPORTS_DIR = BASE_DIR / "reports"
SCREENSHOTS_DIR = REPORTS_DIR / "screenshots"
PROMPTS_DIR = BASE_DIR / "prompts"
DATABASE_PATH = BASE_DIR / "projects.db"

# --- Retry ---
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# --- Lighthouse thresholds ---
THRESHOLD_PERFORMANCE = 80
THRESHOLD_ACCESSIBILITY = 90
THRESHOLD_BEST_PRACTICES = 80
THRESHOLD_SEO = 80

# --- Functional thresholds ---
MAX_CONSOLE_ERRORS = 0
MAX_BROKEN_LINKS = 0
MAX_LOAD_TIME_MS = 3000

# --- Viewports for screenshots ---
VIEWPORTS = {
    "desktop": {"width": 1920, "height": 1080},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 375, "height": 667},
}


def ensure_dirs():
    """Create required directories if they don't exist."""
    for d in (OUTPUT_DIR, REPORTS_DIR, SCREENSHOTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def get_llm():
    """Return a CrewAI LLM instance."""
    from crewai import LLM
    return LLM(
        model=f"anthropic/{LLM_MODEL}",
        # Must be None if unset — empty string breaks CrewAI (it won't fall back to ANTHROPIC_API_KEY).
        api_key=ANTHROPIC_API_KEY or None,
    )
