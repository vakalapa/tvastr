"""Shared API schema — Pydantic models for REST + WebSocket contracts.

This is the single source of truth for the API boundary between
the FastAPI backend and the React frontend.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────

class RunState(str, Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentState(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    killed = "killed"


class SubObjectiveStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    blocked = "blocked"


class WSEventType(str, Enum):
    iteration_start = "iteration_start"
    iteration_end = "iteration_end"
    agent_output = "agent_output"
    agent_status_change = "agent_status_change"
    validation_result = "validation_result"
    run_status_change = "run_status_change"
    run_complete = "run_complete"
    agent_error = "agent_error"
    merge_start = "merge_start"
    merge_result = "merge_result"


# ── Request Models ─────────────────────────────────────────────────

class RunCreateRequest(BaseModel):
    """POST /api/runs — start a new forge run."""
    repo_path: str
    objective: str
    multi_agent: bool = False
    max_iterations: int = 50
    max_agents: int = 3
    parallel: bool = False
    model: str = "claude-sonnet-4-20250514"
    strategy: str = "isolated"


class ControlAction(BaseModel):
    """POST /api/runs/{run_id}/control — control a running forge."""
    action: str  # "pause" | "resume" | "cancel"


# ── Response Models ────────────────────────────────────────────────

class SubObjectiveOut(BaseModel):
    id: int
    description: str
    status: SubObjectiveStatus = SubObjectiveStatus.pending
    assigned_agent: Optional[str] = None
    priority: int = 0
    depends_on: list[int] = Field(default_factory=list)
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class ValidationResultOut(BaseModel):
    name: str
    status: str  # "pass" | "fail" | "error" | "skip"
    output: str = ""
    duration_secs: float = 0.0
    failed_tests: Optional[list[str]] = None


class IterationOut(BaseModel):
    id: int
    agent_id: str
    sub_objective_id: Optional[int] = None
    iteration_num: int
    hypothesis: str = ""
    files_changed: list[str] = Field(default_factory=list)
    patch_sha: str = ""
    validate_results: Optional[list[ValidationResultOut]] = None
    outcome: str = ""
    lesson: str = ""
    created_at: Optional[str] = None


class AgentOut(BaseModel):
    agent_id: str
    sub_objective_id: int
    sub_objective_desc: str
    branch_name: str
    state: AgentState = AgentState.pending
    current_iteration: int = 0
    total_iterations: int = 0
    error: Optional[str] = None


class MergeResultOut(BaseModel):
    branch: str
    success: bool
    conflict_files: list[str] = Field(default_factory=list)
    validation_passed: Optional[bool] = None
    error: Optional[str] = None


class RunOut(BaseModel):
    run_id: str
    repo_path: str
    objective: str
    state: RunState = RunState.pending
    multi_agent: bool = False
    strategy: str = "isolated"
    agents: list[AgentOut] = Field(default_factory=list)
    sub_objectives: list[SubObjectiveOut] = Field(default_factory=list)
    merge_results: list[MergeResultOut] = Field(default_factory=list)
    created_at: str = ""
    completed_at: Optional[str] = None
    overall_success: Optional[bool] = None


class RunSummary(BaseModel):
    """Lightweight run info for list endpoints."""
    run_id: str
    repo_path: str
    state: RunState
    agent_count: int = 0
    created_at: str = ""


# ── WebSocket Messages ─────────────────────────────────────────────

class WSMessage(BaseModel):
    """Envelope for all WebSocket messages."""
    type: WSEventType
    run_id: str
    agent_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
