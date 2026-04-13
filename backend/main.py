"""FastAPI backend: REST API + SSE for the AI Website Agent dashboard."""

import sys
import os
import json
import threading
from pathlib import Path
from urllib import request as urllib_request
from urllib import error as urllib_error
from collections import defaultdict

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.database import init_db, create_project, update_project, get_project, list_projects, delete_project
from backend.events import event_manager
from backend.pipeline_logging import pipeline_log_context
from backend.preview_manager import ensure_preview_for_output_dir
from agent.crew import run_pipeline
from agent.config import (
    REPORTS_DIR,
    SCREENSHOTS_DIR,
    PIPELINE_STEP_TIMEOUT_SECONDS,
    PLANNER_TIMEOUT_SECONDS,
    DEVELOPER_TIMEOUT_SECONDS,
    TESTER_TIMEOUT_SECONDS,
    REVIEWER_TIMEOUT_SECONDS,
    DEPLOYER_TIMEOUT_SECONDS,
    LLM_PROVIDER,
    OLLAMA_MODEL,
    OLLAMA_BASE_URL,
    ENABLE_TESTER,
    ENABLE_REVIEWER,
    DEPLOY_TARGET,
    API_PREVIEW_PORT,
    AI_PROFILE,
    PIPELINE_UNLIMITED,
)

app = FastAPI(title="AI Website Agent", version="1.0.0")
APPROVAL_STEPS = {"planner", "developer", "tester", "reviewer", "deployer"}
_approval_events: dict[str, dict[str, threading.Event]] = defaultdict(dict)
_approval_lock = threading.Lock()
_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()
_terminal_emitted: dict[str, bool] = {}
_terminal_lock = threading.Lock()

# EventSource from localhost:3001 is cross-origin; ``credentials=True`` + ``origins=["*"]`` is invalid CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve screenshots as static files
if SCREENSHOTS_DIR.exists():
    app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS_DIR)), name="screenshots")


@app.on_event("startup")
def startup():
    init_db()
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS_DIR)), name="screenshots")
    print(
        "[startup] effective timeouts: "
        f"pipeline={PIPELINE_STEP_TIMEOUT_SECONDS}s "
        f"planner={PLANNER_TIMEOUT_SECONDS}s "
        f"developer={DEVELOPER_TIMEOUT_SECONDS}s "
        f"tester={TESTER_TIMEOUT_SECONDS}s "
        f"reviewer={REVIEWER_TIMEOUT_SECONDS}s "
        f"deployer={DEPLOYER_TIMEOUT_SECONDS}s "
        f"flags(tester={ENABLE_TESTER}, reviewer={ENABLE_REVIEWER}) "
        f"deploy_target={DEPLOY_TARGET}"
    )


# --- Request/Response models ---

class GenerateRequest(BaseModel):
    prompt: str
    skip_deploy: bool = False
    manual_approval: bool = False


class GenerateResponse(BaseModel):
    project_id: str
    status: str
    stream_url: str


class ApproveStepRequest(BaseModel):
    step: str


def _get_approval_event(project_id: str, step: str) -> threading.Event:
    with _approval_lock:
        event = _approval_events[project_id].get(step)
        if event is None:
            event = threading.Event()
            _approval_events[project_id][step] = event
        return event


def _get_cancel_event(project_id: str) -> threading.Event:
    with _cancel_lock:
        event = _cancel_events.get(project_id)
        if event is None:
            event = threading.Event()
            _cancel_events[project_id] = event
        return event


def _is_cancelled(project_id: str) -> bool:
    with _cancel_lock:
        ev = _cancel_events.get(project_id)
        return bool(ev and ev.is_set())


def _emit_terminal_once(project_id: str, status: str, detail: dict):
    """Emit terminal pipeline event once per project."""
    with _terminal_lock:
        if _terminal_emitted.get(project_id):
            return
        _terminal_emitted[project_id] = True
    event_manager.emit(project_id, "pipeline", status, detail)


def _provider_aware_error_text(error: Exception | str) -> str:
    msg = str(error or "").strip()
    if not msg:
        return "Unknown pipeline error."

    if LLM_PROVIDER == "ollama":
        base = (OLLAMA_BASE_URL or "http://127.0.0.1:11434").rstrip("/")
        if "None or empty" in msg or "empty LLM response" in msg:
            return (
                f"Ollama returned an empty model response. Check model health "
                f"and try again. Endpoint: {base}"
            )
        if "Failed to connect to OpenAI API" in msg or "Connection error" in msg:
            return (
                f"Ollama endpoint unreachable at {base}. "
                f"Start/restart Ollama and verify model '{OLLAMA_MODEL}' is available."
            )
    return msg


def _ollama_preflight():
    """Validate Ollama endpoint and configured model before background run."""
    base = (OLLAMA_BASE_URL or "http://127.0.0.1:11434").rstrip("/")
    tags_url = f"{base}/api/tags"
    try:
        with urllib_request.urlopen(tags_url, timeout=5) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
    except (urllib_error.URLError, TimeoutError) as e:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Ollama preflight failed: cannot reach {tags_url}. "
                f"Start Ollama and retry. ({e})"
            ),
        ) from e

    try:
        data = json.loads(payload or "{}")
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama preflight failed: invalid response from {tags_url}.",
        ) from e

    names = {str(m.get("name", "")).strip() for m in data.get("models", []) if isinstance(m, dict)}
    if OLLAMA_MODEL not in names:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ollama model '{OLLAMA_MODEL}' is not available. "
                f"Run: ollama pull {OLLAMA_MODEL}"
            ),
        )


# --- Routes ---

@app.post("/api/generate", response_model=GenerateResponse)
def start_generation(req: GenerateRequest):
    """Start a new website generation pipeline."""
    if LLM_PROVIDER == "ollama":
        _ollama_preflight()
    project_id = create_project(req.prompt)
    _get_cancel_event(project_id).clear()
    with _terminal_lock:
        _terminal_emitted.pop(project_id, None)
    event_manager.emit(
        project_id,
        "pipeline",
        "started",
        {"message": "Generation job queued"},
    )
    event_manager.emit(
        project_id,
        "log",
        "line",
        {"message": "Pipeline starting (CrewAI + local LLM)…"},
    )
    event_manager.emit(
        project_id,
        "runtime",
        "config",
        {
            "pid": os.getpid(),
            "manual_approval": req.manual_approval,
            "flags": {
                "enable_tester": ENABLE_TESTER,
                "enable_reviewer": ENABLE_REVIEWER,
                "pipeline_unlimited": PIPELINE_UNLIMITED,
                "ai_profile": AI_PROFILE,
            },
            "timeouts": {
                "pipeline": PIPELINE_STEP_TIMEOUT_SECONDS,
                "planner": PLANNER_TIMEOUT_SECONDS,
                "developer": DEVELOPER_TIMEOUT_SECONDS,
                "tester": TESTER_TIMEOUT_SECONDS,
                "reviewer": REVIEWER_TIMEOUT_SECONDS,
                "deployer": DEPLOYER_TIMEOUT_SECONDS,
            },
        },
    )
    runner_done = threading.Event()

    def _emit_heartbeat():
        while not runner_done.wait(timeout=10):
            if _is_cancelled(project_id):
                continue
            events = event_manager.get_events(project_id)
            last = events[-1] if events else {}
            event_manager.emit(
                project_id,
                "pipeline",
                "heartbeat",
                {
                    "message": "Pipeline still running",
                    "last_step": last.get("step"),
                    "last_status": last.get("status"),
                    "event_count": len(events),
                },
            )

    def _run_in_background():
        def on_event(step: str, status: str, detail: dict):
            if _is_cancelled(project_id):
                return
            event_manager.emit(project_id, step, status, detail)
            if step != "log":
                detail_text = ""
                if detail:
                    try:
                        detail_text = f" | detail={json.dumps(detail, ensure_ascii=False, default=str)}"
                    except Exception:
                        detail_text = f" | detail={str(detail)}"
                event_manager.emit(
                    project_id,
                    "log",
                    "line",
                    {"message": f"[{step}] {status}{detail_text}"},
                )

            if step == "reviewer" and status == "done":
                update_project(
                    project_id,
                    status="reviewing",
                    scores=detail.get("score", 0),
                    lighthouse=detail.get("report", {}).get("lighthouse", {}),
                )

        def wait_for_approval(step: str, detail: dict):
            if _is_cancelled(project_id):
                raise RuntimeError("Cancelled by user")
            event_manager.emit(
                project_id,
                step,
                "waiting_approval",
                {"message": f"Approve {step} to continue", **(detail or {})},
            )
            gate = _get_approval_event(project_id, step)
            approved = False
            for _ in range(60 * 60):  # up to 1 hour, check cancel every second
                if _is_cancelled(project_id):
                    raise RuntimeError("Cancelled by user")
                if gate.wait(timeout=1):
                    approved = True
                    break
            if not approved:
                raise TimeoutError(f"Approval timed out for step: {step}")
            event_manager.emit(project_id, step, "approved", detail or {})

        try:
            with pipeline_log_context(project_id):
                result = run_pipeline(
                    user_prompt=req.prompt,
                    on_event=on_event,
                    skip_deploy=req.skip_deploy,
                    wait_for_approval=wait_for_approval if req.manual_approval else None,
                    should_stop=lambda: _is_cancelled(project_id),
                )
            if _is_cancelled(project_id):
                update_project(project_id, status="failed", error="Cancelled by user")
                _emit_terminal_once(project_id, "failed", {"error": "Cancelled by user"})
                return
            update_project(
                project_id,
                status="completed",
                deployed_url=result.get("url"),
                scores=result.get("scores", 0),
                lighthouse=result.get("lighthouse", {}),
                attempts=result.get("attempts", 0),
                time_seconds=result.get("time_seconds", 0),
                output_dir=result.get("output_dir"),
            )
            _emit_terminal_once(project_id, "complete", result)
        except Exception as e:
            provider_error = _provider_aware_error_text(e)
            update_project(project_id, status="failed", error=provider_error)
            _emit_terminal_once(project_id, "failed", {"error": provider_error})
        finally:
            runner_done.set()
            with _approval_lock:
                _approval_events.pop(project_id, None)
            with _cancel_lock:
                _cancel_events.pop(project_id, None)
            with _terminal_lock:
                _terminal_emitted.pop(project_id, None)

    heartbeat_thread = threading.Thread(target=_emit_heartbeat, daemon=True)
    heartbeat_thread.start()
    thread = threading.Thread(target=_run_in_background, daemon=True)
    thread.start()

    return GenerateResponse(
        project_id=project_id,
        status="started",
        stream_url=f"/api/status/{project_id}/stream",
    )


@app.get("/api/status/{project_id}")
def get_status(project_id: str):
    """Get the current status of a project."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    events = event_manager.get_events(project_id)
    return {**project, "events": events}


@app.get("/api/status/{project_id}/stream")
async def stream_status(project_id: str, after: int = 0, after_seq: int = 0):
    """SSE stream for real-time progress updates.

    Use ``after`` (event count already received from GET /api/status) to avoid replaying
    duplicate events when the client hydrates before opening EventSource.
    """
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if after < 0:
        after = 0
    if after_seq < 0:
        after_seq = 0
    return EventSourceResponse(
        event_manager.subscribe(project_id, skip=after, after_seq=after_seq)
    )


@app.post("/api/approve/{project_id}")
def approve_step(project_id: str, req: ApproveStepRequest):
    """Approve a pending step in manual-approval mode."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    step = (req.step or "").strip().lower()
    if step not in APPROVAL_STEPS:
        raise HTTPException(status_code=400, detail=f"Invalid step: {req.step}")

    gate = _get_approval_event(project_id, step)
    gate.set()
    event_manager.emit(project_id, step, "approval_received", {"step": step})
    return {"ok": True, "project_id": project_id, "step": step}


@app.post("/api/stop/{project_id}")
def stop_project(project_id: str):
    """Cancel a running generation pipeline."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    cancel_event = _get_cancel_event(project_id)
    cancel_event.set()
    update_project(project_id, status="stopping", error="Stop requested")
    event_manager.emit(project_id, "pipeline", "stopping", {"message": "Stop requested"})
    return {"ok": True, "project_id": project_id, "stopped": True}


@app.get("/api/projects")
def get_projects():
    """List all projects."""
    return list_projects()


@app.get("/api/projects/{project_id}")
def get_project_detail(project_id: str):
    """Get a single project's details."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/api/projects/{project_id}/preview")
def get_project_preview(project_id: str):
    """Return the API path to open a local Next dev preview (redirect endpoint)."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.get("output_dir"):
        raise HTTPException(
            status_code=404,
            detail="No output_dir stored for this project",
        )
    return {"url": f"/output/{project_id}"}


@app.get("/output/{project_id}")
def open_output_preview(project_id: str):
    """Redirect to a local `next dev` server for the project's generated folder."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    out = project.get("output_dir")
    if not out:
        raise HTTPException(
            status_code=404,
            detail="No output_dir stored for this project",
        )
    root = Path(out)
    if not root.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Generated site folder is missing on disk",
        )
    try:
        preview_url = ensure_preview_for_output_dir(str(root), API_PREVIEW_PORT)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except TimeoutError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return RedirectResponse(url=f"{preview_url}/", status_code=307)


@app.delete("/api/projects/{project_id}")
def remove_project(project_id: str):
    """Delete a project."""
    if not delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"deleted": True}


@app.get("/api/report/{project_id}")
def get_report(project_id: str):
    """Get the test report for a project."""
    report_path = REPORTS_DIR / "test_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No report found")

    return json.loads(report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
