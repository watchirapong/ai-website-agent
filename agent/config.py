import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# subprocess text mode on Windows defaults to locale (cp1252); npm/Next.js emit UTF-8.
SUBPROCESS_TEXT_KW = {"encoding": "utf-8", "errors": "replace"}

# --- LLM ---
# LLM_PROVIDER: "ollama" (local, default) or "anthropic" (cloud API).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
AI_PROFILE = os.getenv("AI_PROFILE", "balanced").strip().lower()

# Ollama — CrewAI uses the native OpenAI-compatible endpoint (default http://localhost:11434/v1).
# Pull a model first, e.g.: ollama pull gemma4:latest
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:latest").strip()
OLLAMA_BASE_URL = (os.getenv("OLLAMA_BASE_URL") or "").strip()

# Anthropic — only used when LLM_PROVIDER=anthropic
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514").strip()
ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
if ANTHROPIC_API_KEY:
    # CrewAI's Anthropic client treats api_key="" as "set" and skips reading ANTHROPIC_API_KEY from the env.
    os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

# --- Ports ---
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "3001"))
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
PREVIEW_PORT = int(os.getenv("PREVIEW_PORT", "3000"))

# Deploy: "local" = `next start` bound to 127.0.0.1 only (this machine). "vercel" = public Vercel deploy.
_deploy_target = os.getenv("DEPLOY_TARGET", "local").strip().lower()
DEPLOY_TARGET = _deploy_target if _deploy_target in {"local", "vercel"} else "local"

# --- Paths ---
BASE_OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR = BASE_OUTPUT_DIR
REPORTS_DIR = BASE_DIR / "reports"
SCREENSHOTS_DIR = REPORTS_DIR / "screenshots"
PROMPTS_DIR = BASE_DIR / "prompts"
DATABASE_PATH = BASE_DIR / "projects.db"


def _crew_step_timeout_seconds(env_key: str, default: int, minimum: int = 120) -> int:
    """Seconds for ThreadPoolExecutor around crew.kickoff(). Low env values (e.g. 15) are
    clamped so local LLM steps are not killed by stray machine/user environment settings."""
    try:
        v = int(os.getenv(env_key, str(default)))
    except ValueError:
        v = default
    return max(minimum, v)


# --- Retry ---
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
PIPELINE_STEP_TIMEOUT_SECONDS = _crew_step_timeout_seconds(
    "PIPELINE_STEP_TIMEOUT_SECONDS", 600
)
PLANNER_TIMEOUT_SECONDS = _crew_step_timeout_seconds(
    "PLANNER_TIMEOUT_SECONDS", PIPELINE_STEP_TIMEOUT_SECONDS
)
DEVELOPER_TIMEOUT_SECONDS = _crew_step_timeout_seconds(
    "DEVELOPER_TIMEOUT_SECONDS", PIPELINE_STEP_TIMEOUT_SECONDS
)
TESTER_TIMEOUT_SECONDS = _crew_step_timeout_seconds(
    "TESTER_TIMEOUT_SECONDS", PIPELINE_STEP_TIMEOUT_SECONDS
)
REVIEWER_TIMEOUT_SECONDS = _crew_step_timeout_seconds(
    "REVIEWER_TIMEOUT_SECONDS", PIPELINE_STEP_TIMEOUT_SECONDS
)
DEPLOYER_TIMEOUT_SECONDS = _crew_step_timeout_seconds(
    "DEPLOYER_TIMEOUT_SECONDS", PIPELINE_STEP_TIMEOUT_SECONDS
)
ENABLE_REVIEWER = (os.getenv("ENABLE_REVIEWER", "0").strip().lower() in {"1", "true", "yes", "on"})
ENABLE_TESTER = (os.getenv("ENABLE_TESTER", "0").strip().lower() in {"1", "true", "yes", "on"})
LLM_EMPTY_RESULT_RETRIES = int(os.getenv("LLM_EMPTY_RESULT_RETRIES", "2"))
LLM_EMPTY_RESULT_BACKOFF_SECONDS = float(os.getenv("LLM_EMPTY_RESULT_BACKOFF_SECONDS", "2"))

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
    for d in (BASE_OUTPUT_DIR, OUTPUT_DIR, REPORTS_DIR, SCREENSHOTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def set_output_dir(path: Path) -> Path:
    """Update active output directory at runtime (used per attempt)."""
    global OUTPUT_DIR
    OUTPUT_DIR = Path(path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


_CREWAI_OLLAMA_PATCHED = False
_OPENAI_KEEP_ALIVE_PATCHED = False


def _patch_openai_completions_create() -> None:
    """Patch OpenAI chat completions to ignore unsupported provider extras.

    CrewAI/OpenAI-compatible paths may pass ``keep_alive`` through kwargs.
    The OpenAI client rejects this argument, so we drop it here globally.
    """

    global _OPENAI_KEEP_ALIVE_PATCHED
    if _OPENAI_KEEP_ALIVE_PATCHED:
        return

    from openai.resources.chat.completions.completions import Completions

    original_create = Completions.create

    def _wrapped_create(self, *args, **kwargs):
        kwargs.pop("keep_alive", None)
        kwargs.pop("drop_params", None)
        return original_create(self, *args, **kwargs)

    Completions.create = _wrapped_create
    _OPENAI_KEEP_ALIVE_PATCHED = True


def _patch_crewai_openai_compatible() -> None:
    """Patch CrewAI OpenAI-compatible provider to drop unsupported Ollama params.

    Some CrewAI/OpenAI-compatible combinations may forward provider-specific keys
    (e.g. ``keep_alive``) directly to the OpenAI Python client, which rejects them.
    """

    global _CREWAI_OLLAMA_PATCHED
    if _CREWAI_OLLAMA_PATCHED:
        return

    from crewai.llms.providers.openai.completion import OpenAICompletion

    original = OpenAICompletion._handle_completion
    original_prepare = OpenAICompletion._prepare_completion_params

    def _wrapped_handle_completion(
        self,
        params: dict[str, Any],
        available_functions: dict[str, Any] | None = None,
        from_task: Any | None = None,
        from_agent: Any | None = None,
        response_model: type[Any] | None = None,
    ):
        cleaned = dict(params or {})
        cleaned.pop("keep_alive", None)
        cleaned.pop("drop_params", None)
        return original(
            self,
            cleaned,
            available_functions=available_functions,
            from_task=from_task,
            from_agent=from_agent,
            response_model=response_model,
        )

    OpenAICompletion._handle_completion = _wrapped_handle_completion

    def _wrapped_prepare_completion_params(self, messages, tools=None):
        params = original_prepare(self, messages, tools)
        params.pop("keep_alive", None)
        params.pop("drop_params", None)
        return params

    OpenAICompletion._prepare_completion_params = _wrapped_prepare_completion_params
    _CREWAI_OLLAMA_PATCHED = True


def get_llm():
    """Return a CrewAI LLM instance (Ollama local or Anthropic API)."""
    _patch_openai_completions_create()
    _patch_crewai_openai_compatible()
    from crewai import LLM

    if LLM_PROVIDER == "ollama":
        profile_defaults = {
            "speed": {"temperature": 0.0, "max_tokens": 128},
            "fast": {"temperature": 0.0, "max_tokens": 256},
            "balanced": {"temperature": 0.2, "max_tokens": 700},
            "quality": {"temperature": 0.3, "max_tokens": 1400},
        }
        defaults = profile_defaults.get(AI_PROFILE, profile_defaults["balanced"])

        kwargs: dict = {
            "model": OLLAMA_MODEL,
            "provider": "ollama",
            "temperature": defaults["temperature"],
            "max_tokens": defaults["max_tokens"],
        }
        if OLLAMA_BASE_URL:
            kwargs["base_url"] = OLLAMA_BASE_URL
        temp = os.getenv("LLM_TEMPERATURE")
        if temp is not None and temp.strip() != "":
            kwargs["temperature"] = float(temp)
        max_tokens = os.getenv("LLM_MAX_TOKENS")
        if max_tokens is not None and max_tokens.strip() != "":
            kwargs["max_tokens"] = int(max_tokens)
        return LLM(**kwargs)

    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise ValueError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY in the environment (.env)."
            )
        return LLM(
            model=f"anthropic/{LLM_MODEL}",
            api_key=ANTHROPIC_API_KEY,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}. Use 'ollama' or 'anthropic'."
    )
