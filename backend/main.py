"""FastAPI backend: REST API + SSE for the AI Website Agent dashboard."""

import sys
import os
import threading

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.database import init_db, create_project, update_project, get_project, list_projects, delete_project
from backend.events import event_manager
from backend.pipeline_logging import pipeline_log_context
from agent.crew import run_pipeline
from agent.config import REPORTS_DIR, SCREENSHOTS_DIR

app = FastAPI(title="AI Website Agent", version="1.0.0")

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


# --- Request/Response models ---

class GenerateRequest(BaseModel):
    prompt: str
    skip_deploy: bool = False


class GenerateResponse(BaseModel):
    project_id: str
    status: str
    stream_url: str


# --- Routes ---

@app.post("/api/generate", response_model=GenerateResponse)
def start_generation(req: GenerateRequest):
    """Start a new website generation pipeline."""
    project_id = create_project(req.prompt)

    def _run_in_background():
        def on_event(step: str, status: str, detail: dict):
            event_manager.emit(project_id, step, status, detail)

            if step == "reviewer" and status == "done":
                update_project(
                    project_id,
                    status="reviewing",
                    scores=detail.get("score", 0),
                    lighthouse=detail.get("report", {}).get("lighthouse", {}),
                )

        try:
            with pipeline_log_context(project_id):
                result = run_pipeline(
                    user_prompt=req.prompt,
                    on_event=on_event,
                    skip_deploy=req.skip_deploy,
                )
            update_project(
                project_id,
                status="completed",
                deployed_url=result.get("url"),
                scores=result.get("scores", 0),
                lighthouse=result.get("lighthouse", {}),
                attempts=result.get("attempts", 0),
                time_seconds=result.get("time_seconds", 0),
            )
            event_manager.emit(project_id, "pipeline", "complete", result)
        except Exception as e:
            update_project(project_id, status="failed", error=str(e))
            event_manager.emit(project_id, "pipeline", "failed", {"error": str(e)})

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
async def stream_status(project_id: str):
    """SSE stream for real-time progress updates."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return EventSourceResponse(event_manager.subscribe(project_id))


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

    import json
    return json.loads(report_path.read_text())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
