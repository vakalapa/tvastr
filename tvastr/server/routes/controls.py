"""Run control endpoints — pause, resume, kill agent."""

from fastapi import APIRouter, Depends, HTTPException

from tvastr.server.app import RunManager, get_run_manager
from tvastr.server.schema import MessageOut

router = APIRouter(prefix="/api/runs/{run_id}", tags=["controls"])


@router.post("/pause", response_model=MessageOut)
def pause_run(
    run_id: str,
    mgr: RunManager = Depends(get_run_manager),
) -> MessageOut:
    """Pause a running forge run."""
    if not mgr.pause_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return MessageOut(message=f"Run {run_id} paused")


@router.post("/resume", response_model=MessageOut)
def resume_run(
    run_id: str,
    mgr: RunManager = Depends(get_run_manager),
) -> MessageOut:
    """Resume a paused forge run."""
    if not mgr.resume_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return MessageOut(message=f"Run {run_id} resumed")


@router.post("/agents/{agent_id}/kill", response_model=MessageOut)
def kill_agent(
    run_id: str,
    agent_id: str,
    mgr: RunManager = Depends(get_run_manager),
) -> MessageOut:
    """Kill a specific agent in a run.

    Note: this is a best-effort signal — it marks the agent as killed
    but does not forcibly terminate the thread.
    """
    run = mgr.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Store killed agents in the run info
    killed = run.setdefault("killed_agents", set())
    killed.add(agent_id)

    return MessageOut(message=f"Agent {agent_id} kill signal sent")
