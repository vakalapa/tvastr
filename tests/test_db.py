"""Tests for tvastr.state.db — StateDB SQLite state store."""

import time
import tempfile
from pathlib import Path

import pytest

from tvastr.state.db import Iteration, StateDB


@pytest.fixture
def db(tmp_path):
    """Create a fresh StateDB for each test."""
    return StateDB(tmp_path / "test.db")


class TestSubObjectives:
    def test_add_and_get_sub_objectives(self, db):
        """Add 2 sub-objectives, verify get returns them in priority ASC order."""
        id1 = db.add_sub_objective("Second task", priority=2)
        id2 = db.add_sub_objective("First task", priority=1)

        objs = db.get_sub_objectives()
        assert len(objs) == 2
        # priority ASC: priority=1 first, priority=2 second
        assert objs[0]["description"] == "First task"
        assert objs[0]["priority"] == 1
        assert objs[1]["description"] == "Second task"
        assert objs[1]["priority"] == 2

    def test_depends_on_round_trip(self, db):
        """Add sub-objective with depends_on=[1,2], verify get returns a list (not string)."""
        db.add_sub_objective("Dependent task", priority=0, depends_on=[1, 2])

        objs = db.get_sub_objectives()
        assert len(objs) == 1
        assert objs[0]["depends_on"] == [1, 2]
        assert isinstance(objs[0]["depends_on"], list)

    def test_update_status(self, db):
        """Update to 'in_progress' and 'done', verify completed_at set for done."""
        obj_id = db.add_sub_objective("Some task", priority=0)

        db.update_sub_objective_status(obj_id, "in_progress")
        objs = db.get_sub_objectives()
        assert objs[0]["status"] == "in_progress"
        assert objs[0]["completed_at"] is None

        db.update_sub_objective_status(obj_id, "done")
        objs = db.get_sub_objectives()
        assert objs[0]["status"] == "done"
        assert objs[0]["completed_at"] is not None

    def test_update_with_assigned_agent(self, db):
        """Update with assigned_agent, verify it's stored."""
        obj_id = db.add_sub_objective("Agent task", priority=0)

        db.update_sub_objective_status(obj_id, "in_progress", assigned_agent="agent-0")
        objs = db.get_sub_objectives()
        assert objs[0]["assigned_agent"] == "agent-0"


class TestIterations:
    def test_log_and_get_iterations(self, db):
        """Log iteration, get it back, verify fields."""
        it = Iteration(
            agent_id="agent-0",
            sub_objective_id=None,
            iteration_num=1,
            hypothesis="Try adding a cache",
            files_changed=["src/cache.py"],
            patch_sha="abc123",
            validate_results=[{"status": "pass", "name": "tests"}],
            outcome="advanced",
            lesson="Cache improved latency.",
        )
        row_id = db.log_iteration(it)
        assert row_id is not None

        rows = db.get_iterations(agent_id="agent-0")
        assert len(rows) == 1
        row = rows[0]
        assert row["agent_id"] == "agent-0"
        assert row["iteration_num"] == 1
        assert row["hypothesis"] == "Try adding a cache"
        assert row["outcome"] == "advanced"
        assert row["lesson"] == "Cache improved latency."

    def test_get_latest_iteration_num(self, db):
        """Log 3 iterations, verify returns 3."""
        for i in range(1, 4):
            db.log_iteration(Iteration(
                agent_id="agent-0",
                sub_objective_id=None,
                iteration_num=i,
                outcome="advanced",
            ))

        assert db.get_latest_iteration_num("agent-0") == 3


class TestResourceLocks:
    def test_lock_acquire_release(self, db):
        """Acquire lock, verify second acquire fails, release, verify re-acquire works."""
        assert db.acquire_lock("file.py", "agent-0") is True
        assert db.acquire_lock("file.py", "agent-1") is False

        db.release_lock("file.py", "agent-0")
        assert db.acquire_lock("file.py", "agent-1") is True

    def test_lock_expiry(self, db):
        """Acquire lock with TTL=1, sleep 2, verify expired lock is cleaned on next acquire."""
        assert db.acquire_lock("file.py", "agent-0", ttl_seconds=1) is True
        time.sleep(2)
        # Expired lock should be cleaned up and new acquire should succeed
        assert db.acquire_lock("file.py", "agent-1") is True


class TestBaselines:
    def test_baseline_set_get(self, db):
        """Set and get baseline value."""
        db.set_baseline("test_login", "duration_ms", 42.5, patch_sha="abc")
        value = db.get_baseline("test_login", "duration_ms")
        assert value == 42.5

        # Overwrite
        db.set_baseline("test_login", "duration_ms", 38.0, patch_sha="def")
        value = db.get_baseline("test_login", "duration_ms")
        assert value == 38.0

        # Non-existent
        assert db.get_baseline("nonexistent", "metric") is None
