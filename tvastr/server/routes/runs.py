"""Run management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tvastr.server.app import RunManager, get_run_manager
from tvastr.server.schema import MessageOut, RunCreate, RunOut, RunSummary

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunOut, status_code=201)
def create_run(
    body: RunCreate,
    mgr: RunManager = Depends(get_run_manager),
) -> RunOut:
    """Start a new forge run."""
    run_id = mgr.start_run(repo_path=body.repo_path, objective=body.objective)
    run = mgr.get_run(run_id)
    return RunOut(
        run_id=run_id,
        state=run["state"],
        objective=run["objective"],
        repo_path=run["repo_path"],
        created_at=run["created_at"],
        completed_at=run["completed_at"],
    )


@router.get("", response_model=list[RunSummary])
def list_runs(
    mgr: RunManager = Depends(get_run_manager),
) -> list[RunSummary]:
    """List all runs."""
    runs = mgr.list_runs()
    return [
        RunSummary(
            run_id=r["run_id"],
            status=r["state"],
            objective=r["objective"],
            created_at=r["created_at"],
            completed_at=r["completed_at"],
        )
        for r in runs
    ]


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    run_id: str,
    mgr: RunManager = Depends(get_run_manager),
) -> RunOut:
    """Get detailed info for a single run."""
    run = mgr.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunOut(
        run_id=run_id,
        state=run["state"],
        objective=run["objective"],
        repo_path=run["repo_path"],
        created_at=run["created_at"],
        completed_at=run["completed_at"],
    )


@router.post("/{run_id}/cancel", response_model=MessageOut)
def cancel_run(
    run_id: str,
    mgr: RunManager = Depends(get_run_manager),
) -> MessageOut:
    """Cancel a running forge run."""
    if not mgr.cancel_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return MessageOut(message=f"Run {run_id} cancelled")
