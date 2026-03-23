"""Thorough tests for the Tvastr REST API server.

Tests use FastAPI's TestClient with a mocked RunManager so no real
repository or ForgeMaster is needed.
"""

from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tvastr.server.app import RunManager, create_app, set_run_manager
from tvastr.state.db import StateDB, Iteration


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def tmp_db(tmp_path: Path) -> StateDB:
    """Create a temporary StateDB for testing."""
    db = StateDB(tmp_path / "test.db")
    return db


@pytest.fixture()
def manager() -> RunManager:
    """Create a fresh RunManager."""
    return RunManager()


@pytest.fixture()
def client(manager: RunManager) -> TestClient:
    """Create a TestClient with the RunManager injected."""
    set_run_manager(manager)
    app = create_app()
    return TestClient(app)


def _seed_run(manager: RunManager, tmp_path: Path, objective: str = "Test objective") -> str:
    """Helper: seed a run directly into the manager without launching a thread."""
    import uuid
    from datetime import datetime

    run_id = uuid.uuid4().hex[:12]
    db = StateDB(tmp_path / f"run_{run_id}.db")

    run_info = {
        "state": "running",
        "db": db,
        "repo_path": str(tmp_path),
        "objective": objective,
        "task": None,
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "cancel_flag": threading.Event(),
        "paused": False,
    }
    manager._runs[run_id] = run_info
    return run_id


# ── Run endpoints ───────────────────────────────────────────────


class TestCreateRun:
    def test_create_run_returns_201(self, client: TestClient, tmp_path: Path):
        """POST /api/runs should return 201 with RunOut."""
        resp = client.post(
            "/api/runs",
            json={"repo_path": str(tmp_path), "objective": "Build feature X"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "run_id" in data
        assert data["state"] == "running"
        assert data["objective"] == "Build feature X"
        assert data["repo_path"] == str(tmp_path)
        assert data["created_at"] is not None

    def test_create_run_missing_fields(self, client: TestClient):
        """POST /api/runs with missing fields should return 422."""
        resp = client.post("/api/runs", json={})
        assert resp.status_code == 422


class TestListRuns:
    def test_list_runs_empty(self, client: TestClient):
        """GET /api/runs should return empty list when no runs exist."""
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_runs_after_creation(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET /api/runs should include created runs."""
        _seed_run(manager, tmp_path, "Objective A")
        _seed_run(manager, tmp_path, "Objective B")

        resp = client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        objectives = {r["objective"] for r in data}
        assert objectives == {"Objective A", "Objective B"}


class TestGetRun:
    def test_get_run_detail(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET /api/runs/{run_id} should return RunOut for an existing run."""
        run_id = _seed_run(manager, tmp_path)
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id
        assert data["state"] == "running"
        assert data["repo_path"] == str(tmp_path)

    def test_get_run_not_found(self, client: TestClient):
        """GET /api/runs/{run_id} should return 404 for missing run."""
        resp = client.get("/api/runs/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Run not found"


class TestCancelRun:
    def test_cancel_run(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """POST /api/runs/{run_id}/cancel should cancel an existing run."""
        run_id = _seed_run(manager, tmp_path)
        resp = client.post(f"/api/runs/{run_id}/cancel")
        assert resp.status_code == 200
        assert "cancelled" in resp.json()["message"]

        # Verify state changed
        run = manager.get_run(run_id)
        assert run["state"] == "cancelled"

    def test_cancel_run_not_found(self, client: TestClient):
        """POST /api/runs/{run_id}/cancel should return 404 for missing run."""
        resp = client.post("/api/runs/nonexistent/cancel")
        assert resp.status_code == 404


# ── Agent endpoints ─────────────────────────────────────────────


class TestAgents:
    def test_list_agents_empty(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET /api/runs/{run_id}/agents should return empty list when no iterations."""
        run_id = _seed_run(manager, tmp_path)
        resp = client.get(f"/api/runs/{run_id}/agents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_agents_with_iterations(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET /api/runs/{run_id}/agents should show agents from iterations."""
        run_id = _seed_run(manager, tmp_path)
        db = manager.get_run(run_id)["db"]

        # Log some iterations for two agents
        db.log_iteration(Iteration(
            agent_id="agent-0", sub_objective_id=1, iteration_num=1,
            hypothesis="Try X", outcome="success", lesson="learned",
        ))
        db.log_iteration(Iteration(
            agent_id="agent-0", sub_objective_id=1, iteration_num=2,
            hypothesis="Try Y", outcome="partial", lesson="more",
        ))
        db.log_iteration(Iteration(
            agent_id="agent-1", sub_objective_id=2, iteration_num=1,
            hypothesis="Try Z", outcome="failure", lesson="nope",
        ))

        resp = client.get(f"/api/runs/{run_id}/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        agent_map = {a["agent_id"]: a for a in data}
        assert agent_map["agent-0"]["iteration_count"] == 2
        assert agent_map["agent-1"]["iteration_count"] == 1

    def test_get_agent_detail(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET /api/runs/{run_id}/agents/{agent_id} should return agent info."""
        run_id = _seed_run(manager, tmp_path)
        db = manager.get_run(run_id)["db"]
        db.log_iteration(Iteration(
            agent_id="agent-0", sub_objective_id=1, iteration_num=1,
            hypothesis="H1", outcome="success",
        ))

        resp = client.get(f"/api/runs/{run_id}/agents/agent-0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "agent-0"
        assert data["iteration_count"] == 1
        assert data["latest_outcome"] == "success"

    def test_get_agent_not_found(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET /api/runs/{run_id}/agents/{agent_id} should return 404 if agent missing."""
        run_id = _seed_run(manager, tmp_path)
        resp = client.get(f"/api/runs/{run_id}/agents/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Agent not found"

    def test_agents_run_not_found(self, client: TestClient):
        """GET /api/runs/{run_id}/agents should return 404 for missing run."""
        resp = client.get("/api/runs/nonexistent/agents")
        assert resp.status_code == 404


class TestIterations:
    def test_list_iterations(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET /api/runs/{run_id}/agents/{agent_id}/iterations should return history."""
        run_id = _seed_run(manager, tmp_path)
        db = manager.get_run(run_id)["db"]
        db.log_iteration(Iteration(
            agent_id="agent-0", sub_objective_id=1, iteration_num=1,
            hypothesis="H1", files_changed=["a.py", "b.py"],
            patch_sha="abc123", validate_results=[{"name": "unit", "status": "pass", "output": "ok", "duration_secs": 1.0}],
            outcome="success", lesson="it worked",
        ))
        db.log_iteration(Iteration(
            agent_id="agent-0", sub_objective_id=1, iteration_num=2,
            hypothesis="H2", outcome="partial",
        ))

        resp = client.get(f"/api/runs/{run_id}/agents/agent-0/iterations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        # Check the first iteration has parsed JSON fields
        it = next(i for i in data if i["iteration_num"] == 1)
        assert it["files_changed"] == ["a.py", "b.py"]
        assert it["validate_results"][0]["name"] == "unit"
        assert it["validate_results"][0]["status"] == "pass"
        assert it["patch_sha"] == "abc123"

    def test_iterations_agent_not_found(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET iterations for missing agent should return 404."""
        run_id = _seed_run(manager, tmp_path)
        resp = client.get(f"/api/runs/{run_id}/agents/ghost/iterations")
        assert resp.status_code == 404


# ── Objectives endpoints ────────────────────────────────────────


class TestObjectives:
    def test_list_objectives_empty(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET /api/runs/{run_id}/objectives should return empty list."""
        run_id = _seed_run(manager, tmp_path)
        resp = client.get(f"/api/runs/{run_id}/objectives")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_objectives_with_data(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """GET /api/runs/{run_id}/objectives should return sub-objectives."""
        run_id = _seed_run(manager, tmp_path)
        db = manager.get_run(run_id)["db"]

        obj_id1 = db.add_sub_objective("Build feature A", priority=2)
        obj_id2 = db.add_sub_objective("Build feature B", priority=1, depends_on=[obj_id1])

        resp = client.get(f"/api/runs/{run_id}/objectives")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        # Ordered by priority ASC (lower = higher priority)
        assert data[0]["description"] == "Build feature B"
        assert data[0]["priority"] == 1
        assert data[0]["depends_on"] == [obj_id1]

        assert data[1]["description"] == "Build feature A"
        assert data[1]["priority"] == 2
        assert data[1]["status"] == "pending"

    def test_objectives_run_not_found(self, client: TestClient):
        """GET /api/runs/{run_id}/objectives should return 404 for missing run."""
        resp = client.get("/api/runs/nonexistent/objectives")
        assert resp.status_code == 404


# ── Control endpoints ───────────────────────────────────────────


class TestControls:
    def test_pause_run(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """POST /api/runs/{run_id}/pause should pause a run."""
        run_id = _seed_run(manager, tmp_path)
        resp = client.post(f"/api/runs/{run_id}/pause")
        assert resp.status_code == 200
        assert "paused" in resp.json()["message"]

        run = manager.get_run(run_id)
        assert run["state"] == "paused"
        assert run["paused"] is True

    def test_resume_run(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """POST /api/runs/{run_id}/resume should resume a paused run."""
        run_id = _seed_run(manager, tmp_path)
        manager.pause_run(run_id)

        resp = client.post(f"/api/runs/{run_id}/resume")
        assert resp.status_code == 200
        assert "resumed" in resp.json()["message"]

        run = manager.get_run(run_id)
        assert run["state"] == "running"
        assert run["paused"] is False

    def test_kill_agent(self, client: TestClient, manager: RunManager, tmp_path: Path):
        """POST /api/runs/{run_id}/agents/{agent_id}/kill should send kill signal."""
        run_id = _seed_run(manager, tmp_path)
        resp = client.post(f"/api/runs/{run_id}/agents/agent-0/kill")
        assert resp.status_code == 200
        assert "kill" in resp.json()["message"].lower()

        run = manager.get_run(run_id)
        assert "agent-0" in run["killed_agents"]

    def test_pause_run_not_found(self, client: TestClient):
        """POST /api/runs/{run_id}/pause should return 404 for missing run."""
        resp = client.post("/api/runs/nonexistent/pause")
        assert resp.status_code == 404

    def test_resume_run_not_found(self, client: TestClient):
        """POST /api/runs/{run_id}/resume should return 404 for missing run."""
        resp = client.post("/api/runs/nonexistent/resume")
        assert resp.status_code == 404

    def test_kill_agent_run_not_found(self, client: TestClient):
        """POST kill for a missing run should return 404."""
        resp = client.post("/api/runs/nonexistent/agents/agent-0/kill")
        assert resp.status_code == 404


# ── RunManager unit tests ───────────────────────────────────────


class TestRunManager:
    def test_start_run_with_mock_factory(self, tmp_path: Path):
        """RunManager.start_run should launch a background thread with factory."""
        mgr = RunManager()

        mock_master = MagicMock()
        mock_master.run.return_value = True

        def factory(repo_path, objective, db):
            return mock_master

        run_id = mgr.start_run(
            repo_path=str(tmp_path),
            objective="Test",
            forge_master_factory=factory,
        )

        # Wait for thread to finish
        run = mgr.get_run(run_id)
        run["task"].join(timeout=5)

        run = mgr.get_run(run_id)
        assert run["state"] == "completed"
        assert run["completed_at"] is not None
        mock_master.run.assert_called_once()

    def test_start_run_factory_failure(self, tmp_path: Path):
        """RunManager should mark run as failed if forge master raises."""
        mgr = RunManager()

        def factory(repo_path, objective, db):
            raise RuntimeError("boom")

        run_id = mgr.start_run(
            repo_path=str(tmp_path),
            objective="Test",
            forge_master_factory=factory,
        )

        run = mgr.get_run(run_id)
        run["task"].join(timeout=5)

        run = mgr.get_run(run_id)
        assert run["state"] == "failed"

    def test_list_runs_returns_ids(self, tmp_path: Path):
        """list_runs should include run_id in each entry."""
        mgr = RunManager()
        _seed_run(mgr, tmp_path, "A")
        _seed_run(mgr, tmp_path, "B")

        runs = mgr.list_runs()
        assert len(runs) == 2
        assert all("run_id" in r for r in runs)
