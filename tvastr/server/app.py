"""FastAPI application factory and RunManager for the Tvastr REST API."""

from __future__ import annotations

import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tvastr.state.db import StateDB


class RunManager:
    """Tracks active and completed forge runs.

    Each run is stored as a dict with keys:
        state, db, repo_path, objective, task, created_at, completed_at
    """

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start_run(
        self,
        repo_path: str,
        objective: str,
        forge_master_factory: Any | None = None,
    ) -> str:
        """Start a new forge run in a background thread.

        Args:
            repo_path: Path to the target repository.
            objective: High-level objective string.
            forge_master_factory: Optional callable(repo_path, objective, db) -> ForgeMaster.
                                  If None, imports and creates the real ForgeMaster.

        Returns:
            The generated run_id.
        """
        run_id = uuid.uuid4().hex[:12]
        db_path = Path(repo_path) / ".tvastr" / f"run_{run_id}.db"
        db = StateDB(db_path)

        run_info: dict[str, Any] = {
            "state": "running",
            "db": db,
            "repo_path": repo_path,
            "objective": objective,
            "task": None,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "cancel_flag": threading.Event(),
            "paused": False,
        }

        with self._lock:
            self._runs[run_id] = run_info

        def _run_forge() -> None:
            try:
                if forge_master_factory is not None:
                    master = forge_master_factory(repo_path, objective, db)
                else:
                    from tvastr.master.orchestrator import ForgeMaster

                    master = ForgeMaster(
                        repo_path=Path(repo_path),
                        objective=objective,
                        db=db,
                    )

                result = master.run()
                with self._lock:
                    run_info["state"] = "completed" if result else "failed"
                    run_info["completed_at"] = datetime.utcnow().isoformat()
            except Exception:
                with self._lock:
                    run_info["state"] = "failed"
                    run_info["completed_at"] = datetime.utcnow().isoformat()

        t = threading.Thread(target=_run_forge, daemon=True)
        run_info["task"] = t
        t.start()

        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return run info dict or None if not found."""
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        """Return a list of all runs with their IDs."""
        with self._lock:
            result = []
            for run_id, info in self._runs.items():
                result.append({"run_id": run_id, **info})
            return result

    def cancel_run(self, run_id: str) -> bool:
        """Set the cancel flag for a run. Returns False if run not found."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return False
            run["cancel_flag"].set()
            run["state"] = "cancelled"
            run["completed_at"] = datetime.utcnow().isoformat()
            return True

    def pause_run(self, run_id: str) -> bool:
        """Pause a run. Returns False if run not found."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return False
            run["paused"] = True
            run["state"] = "paused"
            return True

    def resume_run(self, run_id: str) -> bool:
        """Resume a paused run. Returns False if run not found."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return False
            run["paused"] = False
            run["state"] = "running"
            return True


# ── Module-level manager (used as FastAPI dependency) ───────────

_manager: RunManager | None = None


def get_run_manager() -> RunManager:
    """FastAPI dependency — returns the global RunManager."""
    global _manager
    if _manager is None:
        _manager = RunManager()
    return _manager


def set_run_manager(manager: RunManager) -> None:
    """Override the global RunManager (used in tests)."""
    global _manager
    _manager = manager


# ── App factory ─────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler — setup and teardown."""
    # Startup: ensure RunManager exists
    get_run_manager()
    yield
    # Shutdown: nothing special needed


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="Tvastr Forge API",
        description="REST API for the Tvastr autonomous code forge orchestrator",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount route modules
    from tvastr.server.routes.agents import router as agents_router
    from tvastr.server.routes.controls import router as controls_router
    from tvastr.server.routes.objectives import router as objectives_router
    from tvastr.server.routes.runs import router as runs_router

    app.include_router(runs_router)
    app.include_router(agents_router)
    app.include_router(controls_router)
    app.include_router(objectives_router)

    return app
