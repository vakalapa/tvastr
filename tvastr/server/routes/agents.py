"""Agent-related endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException

from tvastr.server.app import RunManager, get_run_manager
from tvastr.server.schema import AgentOut, IterationOut

router = APIRouter(prefix="/api/runs/{run_id}/agents", tags=["agents"])


def _parse_json_field(value, default=None):
    """Safely parse a JSON string field from the database."""
    if value is None:
        return default if default is not None else []
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


@router.get("", response_model=list[AgentOut])
def list_agents(
    run_id: str,
    mgr: RunManager = Depends(get_run_manager),
) -> list[AgentOut]:
    """List all agents that have recorded iterations in a run."""
    run = mgr.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    db = run["db"]
    iterations = db.get_iterations()

    # Group by agent_id
    agents: dict[str, dict] = {}
    for it in iterations:
        aid = it["agent_id"]
        if aid not in agents:
            agents[aid] = {
                "agent_id": aid,
                "iteration_count": 0,
                "latest_outcome": "",
                "sub_objective_id": it.get("sub_objective_id"),
            }
        agents[aid]["iteration_count"] += 1
        # Latest outcome comes from the most recent iteration (first in desc order)
        if agents[aid]["latest_outcome"] == "":
            agents[aid]["latest_outcome"] = it.get("outcome", "")

    return [AgentOut(**a) for a in agents.values()]


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(
    run_id: str,
    agent_id: str,
    mgr: RunManager = Depends(get_run_manager),
) -> AgentOut:
    """Get detail for a specific agent."""
    run = mgr.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    db = run["db"]
    iterations = db.get_iterations(agent_id=agent_id)
    if not iterations:
        raise HTTPException(status_code=404, detail="Agent not found")

    return AgentOut(
        agent_id=agent_id,
        iteration_count=len(iterations),
        latest_outcome=iterations[0].get("outcome", ""),
        sub_objective_id=iterations[0].get("sub_objective_id"),
    )


@router.get("/{agent_id}/iterations", response_model=list[IterationOut])
def list_iterations(
    run_id: str,
    agent_id: str,
    mgr: RunManager = Depends(get_run_manager),
) -> list[IterationOut]:
    """Get iteration history for an agent."""
    run = mgr.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    db = run["db"]
    iterations = db.get_iterations(agent_id=agent_id)
    if not iterations:
        raise HTTPException(status_code=404, detail="Agent not found")

    return [
        IterationOut(
            id=it.get("id"),
            agent_id=it["agent_id"],
            sub_objective_id=it.get("sub_objective_id"),
            iteration_num=it["iteration_num"],
            hypothesis=it.get("hypothesis", ""),
            files_changed=_parse_json_field(it.get("files_changed"), []),
            patch_sha=it.get("patch_sha", ""),
            validate_results=_parse_json_field(it.get("validate_results")),
            outcome=it.get("outcome", ""),
            lesson=it.get("lesson", ""),
            created_at=it.get("created_at"),
        )
        for it in iterations
    ]
