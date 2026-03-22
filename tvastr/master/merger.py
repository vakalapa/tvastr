"""Merger — merge agent branches and handle conflicts."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from tvastr.infra.validator import ValidationConfig, run_validation_suite

console = Console()


@dataclass
class MergeResult:
    """Result of merging an agent branch."""

    branch: str
    success: bool
    conflict_files: list[str]
    validation_passed: bool | None  # None = not yet validated
    error: str | None = None


class Merger:
    """Merges successful agent branches into the forge main branch.

    Strategy A (default): Sequential merge — merge one branch at a time,
    validate after each merge. If merge conflicts or validation fails,
    skip that branch and report it.
    """

    def __init__(
        self,
        repo_path: Path,
        base_branch: str,
        validate_configs: list[ValidationConfig] | None = None,
    ):
        self.repo_path = repo_path.resolve()
        self.base_branch = base_branch
        self.validate_configs = validate_configs or []

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=self.repo_path,
        )

    def merge_branches(
        self,
        branches: list[str],
        validate_after_each: bool = True,
    ) -> list[MergeResult]:
        """Merge branches sequentially into the base branch.

        Args:
            branches: Branch names to merge (in priority order).
            validate_after_each: Run validation after each merge.

        Returns:
            List of MergeResult for each branch.
        """
        results: list[MergeResult] = []

        # Ensure we're on the base branch
        self._git("checkout", self.base_branch)

        # Save current HEAD SHA for rollback
        head_result = self._git("rev-parse", "HEAD")
        self._pre_merge_sha = head_result.stdout.strip()

        for branch in branches:
            console.print(f"[dim]Merging {branch}...[/dim]")
            result = self._merge_one(branch)

            if result.success and validate_after_each and self.validate_configs:
                console.print(f"[dim]Validating after merge of {branch}...[/dim]")
                val_results = run_validation_suite(
                    self.validate_configs, self.repo_path, fail_fast=True
                )
                result.validation_passed = all(r.status == "pass" for r in val_results)

                if not result.validation_passed:
                    # Revert this merge
                    console.print(f"[yellow]Validation failed after merging {branch}, reverting.[/yellow]")
                    self._git("reset", "--hard", "HEAD~1")
                    failed_names = [r.name for r in val_results if r.status != "pass"]
                    result.error = f"Validation failed: {', '.join(failed_names)}"
            elif result.success:
                result.validation_passed = True  # No validation configured

            results.append(result)

            if result.success and result.validation_passed:
                console.print(f"[green]Merged {branch} successfully.[/green]")
            else:
                console.print(f"[red]Failed to integrate {branch}: {result.error}[/red]")

        return results

    def _merge_one(self, branch: str) -> MergeResult:
        """Attempt to merge a single branch."""
        merge_result = self._git("merge", branch, "--no-ff", "-m", f"tvastr: merge {branch}")

        if merge_result.returncode == 0:
            return MergeResult(
                branch=branch,
                success=True,
                conflict_files=[],
                validation_passed=None,
            )

        # Check for merge conflicts
        conflict_files = self._get_conflict_files()

        if conflict_files:
            # Abort the merge
            self._git("merge", "--abort")
            return MergeResult(
                branch=branch,
                success=False,
                conflict_files=conflict_files,
                validation_passed=None,
                error=f"Merge conflicts in: {', '.join(conflict_files)}",
            )

        # Some other merge error
        self._git("merge", "--abort")
        return MergeResult(
            branch=branch,
            success=False,
            conflict_files=[],
            validation_passed=None,
            error=merge_result.stderr.strip()[:500],
        )

    def _get_conflict_files(self) -> list[str]:
        """Get list of files with merge conflicts."""
        result = self._git("diff", "--name-only", "--diff-filter=U")
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return result.stdout.strip().split("\n")

    def combined_validation(self, rollback_sha: str | None = None) -> bool:
        """Run full validation suite on the current merged state.

        Args:
            rollback_sha: If provided and validation fails, revert to this SHA.
        """
        if not self.validate_configs:
            console.print("[dim]No validation configs — skipping combined validation.[/dim]")
            return True

        console.print("[dim]Running combined validation on merged result...[/dim]")
        results = run_validation_suite(self.validate_configs, self.repo_path, fail_fast=False)
        passed = all(r.status == "pass" for r in results)

        if passed:
            console.print("[bold green]Combined validation passed![/bold green]")
        else:
            failed = [r.name for r in results if r.status != "pass"]
            console.print(f"[bold red]Combined validation failed: {', '.join(failed)}[/bold red]")
            if rollback_sha:
                console.print(f"[yellow]Rolling back to {rollback_sha}[/yellow]")
                self._git("reset", "--hard", rollback_sha)

        return passed
