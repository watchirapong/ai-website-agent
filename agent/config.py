import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- LLM ---
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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
