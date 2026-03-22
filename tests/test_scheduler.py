"""Tests for tvastr.master.scheduler — agent scheduling and slot management."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tvastr.master.scheduler import AgentSlot, Scheduler
from tvastr.state.db import StateDB


def _git(repo_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with an initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgSign", "false")
    (repo / "file.txt").write_text("initial\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial commit")
    return repo


@pytest.fixture
def db(tmp_path):
    return StateDB(tmp_path / "test.db")


@pytest.fixture
def sub_objectives(db):
    """Create 2 sub-objectives in the DB and return them as dicts."""
    id1 = db.add_sub_objective("Implement feature A", priority=0)
    id2 = db.add_sub_objective("Implement feature B", priority=1)
    return [
        {"id": id1, "description": "Implement feature A"},
        {"id": id2, "description": "Implement feature B"},
    ]


class TestScheduleCreation:
    @patch("tvastr.master.scheduler.ForgeAgent")
    def test_schedule_creates_slots(self, MockForgeAgent, git_repo, db, sub_objectives):
        """Schedule 2 sub-objectives, verify 2 AgentSlot objects with correct fields."""
        MockForgeAgent.return_value = MagicMock()

        scheduler = Scheduler(repo_path=git_repo, db=db)
        slots = scheduler.schedule(sub_objectives, "Build the app")

        assert len(slots) == 2
        assert all(isinstance(s, AgentSlot) for s in slots)
        assert slots[0].agent_id == "agent-0"
        assert slots[0].sub_objective_desc == "Implement feature A"
        assert slots[0].branch_name == "tvastr/agent-0"
        assert slots[1].agent_id == "agent-1"
        assert slots[1].sub_objective_desc == "Implement feature B"
        assert slots[1].branch_name == "tvastr/agent-1"

    @patch("tvastr.master.scheduler.ForgeAgent")
    def test_schedule_creates_branches(self, MockForgeAgent, git_repo, db, sub_objectives):
        """Verify git branches tvastr/agent-0 and tvastr/agent-1 exist after scheduling."""
        MockForgeAgent.return_value = MagicMock()

        scheduler = Scheduler(repo_path=git_repo, db=db)
        scheduler.schedule(sub_objectives, "Build the app")

        result = _git(git_repo, "branch", "--list")
        branches = result.stdout.strip()
        assert "tvastr/agent-0" in branches
        assert "tvastr/agent-1" in branches


class TestSlotFiltering:
    def test_get_successful_branches(self):
        """Set slot results, verify get_successful_branches filter works."""
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.slots = [
            AgentSlot(agent_id="agent-0", sub_objective_id=1,
                      sub_objective_desc="A", branch_name="tvastr/agent-0", result=True),
            AgentSlot(agent_id="agent-1", sub_objective_id=2,
                      sub_objective_desc="B", branch_name="tvastr/agent-1", result=False),
            AgentSlot(agent_id="agent-2", sub_objective_id=3,
                      sub_objective_desc="C", branch_name="tvastr/agent-2", result=True),
        ]

        successful = scheduler.get_successful_branches()
        assert successful == ["tvastr/agent-0", "tvastr/agent-2"]

    def test_get_failed_slots(self):
        """Set slot results, verify get_failed_slots filter works."""
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.slots = [
            AgentSlot(agent_id="agent-0", sub_objective_id=1,
                      sub_objective_desc="A", branch_name="tvastr/agent-0", result=True),
            AgentSlot(agent_id="agent-1", sub_objective_id=2,
                      sub_objective_desc="B", branch_name="tvastr/agent-1", result=False),
            AgentSlot(agent_id="agent-2", sub_objective_id=3,
                      sub_objective_desc="C", branch_name="tvastr/agent-2", result=None),
        ]

        failed = scheduler.get_failed_slots()
        assert len(failed) == 2
        assert failed[0].agent_id == "agent-1"
        assert failed[1].agent_id == "agent-2"
