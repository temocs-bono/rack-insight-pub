"""Rack Insight — Reference Plugin.

A fully independent backend + frontend service that implements the Rack Insight
Plugin Contract. It shares NO code with the Core: it is a standalone container
that the Core registers, health-checks, and proxies to (both its backend API and
its frontend). Copy this directory as the starting point for a new plugin — see
docs/plugin-development.md.

Contract endpoints:
    GET  /plugin/manifest        -> plugin metadata (incl. the UI descriptor)
    GET  /healthz                -> liveness  (200 = alive)
    GET  /readyz                 -> readiness (200 = ready to serve)
    GET  /api/status             -> a trivial plugin-specific API
    POST /api/echo               -> POST proxy demo

Long-running Job Contract (see docs/plugin-development.md §"Jobs"):
    POST /api/jobs               -> create a job              (202, state=queued)
    GET  /api/jobs               -> list jobs
    GET  /api/jobs/{id}          -> job status
    GET  /api/jobs/{id}/results  -> job results (when completed)
    POST /api/jobs/{id}/cancel   -> request cancellation

Frontend:
    GET  /ui/                    -> self-contained single-page UI (iframe)

The frontend never talks to the plugin directly. It is embedded by the Core as a
same-origin iframe at /api/plugins/<name>/ui/ and calls back through the Core
proxy (/api/plugins/<name>/proxy/...), so the browser never learns the plugin's
Service DNS name and inherits the Core's authentication.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PLUGIN_NAME = os.environ.get("PLUGIN_NAME", "example-plugin")
PLUGIN_VERSION = os.environ.get("PLUGIN_VERSION", "1.1.0")
API_VERSION = "v1"

# How long the simulated long-running job "works" for (seconds). Kept small so
# the reference UI shows the full queued -> running -> completed lifecycle fast.
JOB_DURATION_SECONDS = float(os.environ.get("JOB_DURATION_SECONDS", "4"))

app = FastAPI(title="Rack Insight Example Plugin", version=PLUGIN_VERSION)

UI_DIR = Path(__file__).parent / "ui"


MANIFEST = {
    "name": PLUGIN_NAME,
    "displayName": "Example Plugin",
    "version": PLUGIN_VERSION,
    "apiVersion": API_VERSION,
    "description": "Reference plugin: backend API, long-running jobs, and an embedded UI.",
    "healthEndpoint": "/healthz",
    "readyEndpoint": "/readyz",
    "manifestEndpoint": "/plugin/manifest",
    # The Core embeds this frontend as a same-origin iframe. `path` is served by
    # the Core at /api/plugins/<name>/ui/ — only `iframe` is supported.
    "ui": {"type": "iframe", "path": "/ui/", "title": "Example Plugin"},
    # Reserved for future dynamic extension (not consumed by the Core yet).
    "routes": [{"method": "GET", "path": "/api/status"}],
    "permissions": ["plugin.example.view", "plugin.example.execute"],
    "menus": [],
}


# --------------------------------------------------------------------------- #
# Contract: metadata + lifecycle
# --------------------------------------------------------------------------- #
@app.get("/plugin/manifest")
def manifest() -> dict:
    return MANIFEST


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "healthy"}


@app.get("/readyz")
def readyz() -> dict:
    return {"status": "ready"}


# --------------------------------------------------------------------------- #
# Backend API
# --------------------------------------------------------------------------- #
@app.get("/api/status")
def status() -> dict:
    return {"plugin": PLUGIN_NAME, "status": "running", "version": PLUGIN_VERSION}


@app.post("/api/echo")
def echo(payload: dict | None = None) -> dict:
    """Demonstrates POST proxying: returns whatever it is sent."""
    return {"plugin": PLUGIN_NAME, "echo": payload or {}}


# --------------------------------------------------------------------------- #
# Long-running Job Contract (in-memory reference implementation)
#
# States: queued -> running -> completed | failed | cancelled
#
# This is intentionally in-memory (a dict) so the reference stays dependency-free
# and easy to read. A real plugin would persist jobs in its OWN database — never
# in the Core's — and would run work in a proper worker. It must NOT store Core
# inventory or plaintext credentials; it targets a server by the opaque id the
# Core inventory endpoint returns and lets the Core hold the secrets.
# --------------------------------------------------------------------------- #
STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"

_TERMINAL_STATES = {STATE_COMPLETED, STATE_FAILED, STATE_CANCELLED}


class JobCreate(BaseModel):
    # Opaque server id from the Core inventory (GET /api/plugins/inventory/servers).
    server_id: str | None = None
    action: str = "inspect"


class Job:
    def __init__(self, server_id: str | None, action: str) -> None:
        self.id = str(uuid.uuid4())
        self.server_id = server_id
        self.action = action
        self.state = STATE_QUEUED
        self.progress = 0
        self.created_at = _now()
        self.updated_at = self.created_at
        self.error: str | None = None
        self.results: dict | None = None
        self._cancelled = False
        self._task: asyncio.Task | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "serverId": self.server_id,
            "action": self.action,
            "state": self.state,
            "progress": self.progress,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "error": self.error,
        }


_JOBS: dict[str, Job] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run_job(job: Job) -> None:
    """Simulate a long-running task, advancing state/progress. Cooperative
    cancellation: it checks the cancel flag between steps."""
    try:
        job.state = STATE_RUNNING
        job.updated_at = _now()
        steps = 8
        for step in range(1, steps + 1):
            if job._cancelled:
                job.state = STATE_CANCELLED
                job.updated_at = _now()
                return
            await asyncio.sleep(JOB_DURATION_SECONDS / steps)
            job.progress = int(step / steps * 100)
            job.updated_at = _now()
        job.results = {
            "serverId": job.server_id,
            "action": job.action,
            "summary": f"Completed '{job.action}' for server {job.server_id or '(none)'}.",
            "findings": [
                {"check": "reachability", "result": "ok"},
                {"check": "firmware", "result": "up-to-date"},
            ],
            "finishedAt": _now(),
        }
        job.state = STATE_COMPLETED
        job.progress = 100
        job.updated_at = _now()
    except Exception as exc:  # defensive: a failed job must not crash the worker
        job.state = STATE_FAILED
        job.error = str(exc)
        job.updated_at = _now()


@app.post("/api/jobs", status_code=202)
async def create_job(payload: JobCreate) -> JSONResponse:
    job = Job(server_id=payload.server_id, action=payload.action)
    _JOBS[job.id] = job
    job._task = asyncio.create_task(_run_job(job))
    return JSONResponse(status_code=202, content=job.to_dict())


@app.get("/api/jobs")
def list_jobs() -> dict:
    jobs = sorted(_JOBS.values(), key=lambda j: j.created_at, reverse=True)
    return {"jobs": [j.to_dict() for j in jobs]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/results")
def get_job_results(job_id: str) -> dict:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state != STATE_COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job is '{job.state}'; results are available only when completed",
        )
    return {"id": job.id, "state": job.state, "results": job.results}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state in _TERMINAL_STATES:
        raise HTTPException(status_code=409, detail=f"Job is already '{job.state}'")
    job._cancelled = True
    return job.to_dict()


# --------------------------------------------------------------------------- #
# Frontend (embedded by the Core as a same-origin iframe)
# --------------------------------------------------------------------------- #
# Mounted last so it never shadows the API routes above. `html=True` serves
# ui/index.html at /ui/.
app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
