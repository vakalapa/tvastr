"""Tests for tvastr.master.orchestrator — ForgeMaster orchestration logic."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tvastr.master.decomposer import SubObjective
from tvastr.master.orchestrator import ForgeMaster
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


class TestFallbackSingleAgent:
    @patch("tvastr.master.orchestrator.decompose_objective")
    @patch("tvastr.master.orchestrator.decompose_from_checklist")
    @patch("tvastr.master.orchestrator.ForgeAgent", create=True)
    def test_fallback_single_agent(
        self, MockForgeAgent, mock_checklist, mock_decompose, git_repo, db
    ):
        """Mock decompose_from_checklist to return None and decompose_objective to raise,
        verify fallback runs single agent."""
        mock_checklist.return_value = None
        mock_decompose.side_effect = RuntimeError("LLM unavailable")

        # The fallback imports ForgeAgent inside _fallback_single_agent,
        # so we need to patch it at the agent module level.
        mock_agent_instance = MagicMock()
        mock_agent_instance.run.return_value = True

        with patch("tvastr.master.orchestrator.ForgeAgent", create=True) as MockFA:
            # Patch the import inside _fallback_single_agent
            with patch("tvastr.agent.forge_agent.ForgeAgent") as MockFAInner:
                MockFAInner.return_value = mock_agent_instance
                MockFA.return_value = mock_agent_instance

                master = ForgeMaster(
                    repo_path=git_repo,
                    objective="Build something",
                    db=db,
                )
                # Override _decompose to return empty list (triggers fallback)
                # and _fallback_single_agent to use our mock
                result = master.run()

        assert result is True
        mock_agent_instance.run.assert_called_once()


class TestDisplaySubObjectives:
    def test_display_sub_objectives_no_crash(self, git_repo, db):
        """Verify _display_sub_objectives doesn't crash with valid data."""
        master = ForgeMaster(
            repo_path=git_repo,
            objective="Build something",
            db=db,
        )

        sub_objectives = [
            SubObjective(
                description="Implement feature A",
                acceptance_criteria=["Tests pass"],
                priority=0,
                depends_on=[],
                suggested_files=["src/a.py"],
            ),
            SubObjective(
                description="Implement feature B",
                acceptance_criteria=["Lint passes"],
                priority=1,
                depends_on=[0],
                suggested_files=["src/b.py"],
            ),
        ]

        # Should not raise any exception
        master._display_sub_objectives(sub_objectives)
