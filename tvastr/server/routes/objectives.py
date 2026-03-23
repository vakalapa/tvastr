"""Sub-objective endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException

from tvastr.server.app import RunManager, get_run_manager
from tvastr.server.schema import SubObjectiveOut

router = APIRouter(prefix="/api/runs/{run_id}/objectives", tags=["objectives"])


def _parse_depends_on(value) -> list[int]:
    """Parse depends_on JSON field to a list of ints."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


@router.get("", response_model=list[SubObjectiveOut])
def list_objectives(
    run_id: str,
    mgr: RunManager = Depends(get_run_manager),
) -> list[SubObjectiveOut]:
    """List all sub-objectives for a run."""
    run = mgr.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    db = run["db"]
    objs = db.get_sub_objectives()

    return [
        SubObjectiveOut(
            id=o["id"],
            description=o["description"],
            status=o.get("status", "pending"),
            assigned_agent=o.get("assigned_agent"),
            priority=o.get("priority", 0),
            depends_on=_parse_depends_on(o.get("depends_on")),
            created_at=o.get("created_at"),
            completed_at=o.get("completed_at"),
        )
        for o in objs
    ]
