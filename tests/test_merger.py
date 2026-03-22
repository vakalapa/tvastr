"""Tests for tvastr.master.merger — branch merging and conflict detection."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from tvastr.master.merger import Merger, MergeResult


def _git(repo_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Helper to run git commands in a repo."""
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

    # Initial commit with a file
    (repo / "file.txt").write_text("line 1\nline 2\nline 3\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial commit")

    return repo


def _create_branch_with_change(repo: Path, branch_name: str, filename: str, content: str):
    """Create a branch from main with a file change."""
    _git(repo, "checkout", "master")
    _git(repo, "checkout", "-b", branch_name)
    (repo / filename).write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", f"changes on {branch_name}")
    _git(repo, "checkout", "master")


class TestMergeClean:
    def test_merge_clean_branch(self, git_repo):
        """Create branch with non-conflicting change, merge succeeds."""
        _create_branch_with_change(git_repo, "feature-a", "new_file.txt", "hello\n")

        merger = Merger(repo_path=git_repo, base_branch="master")
        results = merger.merge_branches(["feature-a"], validate_after_each=False)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].conflict_files == []


class TestMergeConflict:
    def test_merge_conflict(self, git_repo):
        """Create two branches modifying same line, second merge detects conflict."""
        # Branch A modifies file.txt
        _create_branch_with_change(git_repo, "branch-a", "file.txt", "branch A content\nline 2\nline 3\n")
        # Branch B also modifies file.txt (same line)
        _create_branch_with_change(git_repo, "branch-b", "file.txt", "branch B content\nline 2\nline 3\n")

        merger = Merger(repo_path=git_repo, base_branch="master")
        results = merger.merge_branches(["branch-a", "branch-b"], validate_after_each=False)

        # First merge should succeed
        assert results[0].success is True
        # Second merge should fail with conflict
        assert results[1].success is False

    def test_merge_conflict_reports_files(self, git_repo):
        """Verify conflict_files list is populated."""
        _create_branch_with_change(git_repo, "branch-a", "file.txt", "AAA\n")
        _create_branch_with_change(git_repo, "branch-b", "file.txt", "BBB\n")

        merger = Merger(repo_path=git_repo, base_branch="master")
        results = merger.merge_branches(["branch-a", "branch-b"], validate_after_each=False)

        conflict_result = results[1]
        assert conflict_result.success is False
        assert "file.txt" in conflict_result.conflict_files


class TestCombinedValidation:
    def test_combined_validation_no_configs(self, git_repo):
        """Returns True when no validation configs."""
        merger = Merger(repo_path=git_repo, base_branch="master", validate_configs=[])
        assert merger.combined_validation() is True
