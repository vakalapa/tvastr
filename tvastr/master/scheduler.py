"""Scheduler — spawn and coordinate forge agents across sub-objectives."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from rich.console import Console

from tvastr.agent.forge_agent import ForgeAgent
from tvastr.infra.validator import ValidationConfig
from tvastr.state.db import StateDB

console = Console()


class MergeStrategy(str, Enum):
    """How agents coordinate their work."""

    ISOLATED = "isolated"  # Separate branches, sequential merge
    FILE_LOCK = "file_lock"  # Shared branch, file-level locking
    SPECULATIVE = "speculative"  # Parallel branches, validate-then-merge


@dataclass
class AgentSlot:
    """Tracks a running agent and its assigned work."""

    agent_id: str
    sub_objective_id: int
    sub_objective_desc: str
    branch_name: str
    agent: ForgeAgent | None = None
    result: bool | None = None  # True = objective met, False = budget exhausted
    error: str | None = None


class Scheduler:
    """Spawns forge agents for sub-objectives and coordinates their work.

    Uses Strategy A (isolated branches, sequential merge) by default.
    Each agent works on its own git branch. When an agent succeeds,
    the merger integrates its changes into the main forge branch.
    """

    def __init__(
        self,
        repo_path: Path,
        db: StateDB,
        validate_configs: list[ValidationConfig] | None = None,
        max_iterations_per_agent: int = 50,
        max_concurrent_agents: int = 3,
        model: str = "claude-sonnet-4-20250514",
        strategy: MergeStrategy = MergeStrategy.ISOLATED,
    ):
        self.repo_path = repo_path.resolve()
        self.db = db
        self.validate_configs = validate_configs or []
        self.max_iterations_per_agent = max_iterations_per_agent
        self.max_concurrent_agents = max_concurrent_agents
        self.model = model
        self.strategy = strategy
        self.slots: list[AgentSlot] = []
        self._base_branch: str = ""

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=self.repo_path,
        )

    def _current_branch(self) -> str:
        result = self._git("rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout.strip()

    def _create_agent_branch(self, agent_id: str) -> str:
        """Create a fresh branch for the agent from the base branch."""
        branch = f"tvastr/{agent_id}"
        self._git("checkout", self._base_branch)
        self._git("checkout", "-b", branch)
        self._git("checkout", self._base_branch)
        return branch

    def schedule(
        self,
        sub_objectives: list[dict],
        objective_text: str,
    ) -> list[AgentSlot]:
        """Create agent slots for each sub-objective.

        Args:
            sub_objectives: List of dicts with 'id', 'description' keys (from StateDB).
            objective_text: The full objective for context.

        Returns:
            List of AgentSlot objects ready to be run.
        """
        self._base_branch = self._current_branch()
        self.slots = []

        for i, sub_obj in enumerate(sub_objectives):
            agent_id = f"agent-{i}"
            branch = self._create_agent_branch(agent_id)

            # Build per-agent objective: overall context + specific sub-objective
            agent_objective = (
                f"# Overall Objective\n{objective_text}\n\n"
                f"# Your Sub-Objective\n{sub_obj['description']}\n\n"
                f"Focus on this specific sub-objective. Other agents are handling "
                f"other parts of the overall objective."
            )

            agent = ForgeAgent(
                agent_id=agent_id,
                repo_path=self.repo_path,
                objective=agent_objective,
                db=self.db,
                validate_configs=self.validate_configs,
                max_iterations=self.max_iterations_per_agent,
                model=self.model,
            )

            slot = AgentSlot(
                agent_id=agent_id,
                sub_objective_id=sub_obj["id"],
                sub_objective_desc=sub_obj["description"],
                branch_name=branch,
                agent=agent,
            )
            self.slots.append(slot)

            # Mark sub-objective as in_progress
            self.db.update_sub_objective_status(sub_obj["id"], "in_progress")

        return self.slots

    def run_sequential(self) -> list[AgentSlot]:
        """Run agents sequentially (simplest strategy).

        Each agent runs on its own branch. After each agent finishes,
        its branch is available for merging.
        """
        for slot in self.slots:
            console.rule(f"[bold magenta]Agent {slot.agent_id}: {slot.sub_objective_desc[:80]}[/bold magenta]")

            # Switch to agent's branch
            self._git("checkout", slot.branch_name)

            try:
                slot.result = slot.agent.run()
            except Exception as e:
                slot.result = False
                slot.error = str(e)
                console.print(f"[red]Agent {slot.agent_id} errored: {e}[/red]")

            # Update sub-objective status
            status = "done" if slot.result else "blocked"
            self.db.update_sub_objective_status(slot.sub_objective_id, status)

            # Return to base branch
            self._git("checkout", self._base_branch)

        return self.slots

    def run_parallel(self) -> list[AgentSlot]:
        """Run agents in parallel using threads.

        Each agent works on its own worktree (directory copy) so they
        don't interfere with each other's git state.
        """
        import concurrent.futures

        worktrees: dict[str, Path] = {}

        try:
            # Create worktrees for each agent
            for slot in self.slots:
                wt_path = self.repo_path.parent / f".tvastr-wt-{slot.agent_id}"
                self._git("worktree", "add", str(wt_path), slot.branch_name)
                worktrees[slot.agent_id] = wt_path

                # Point agent at its worktree
                slot.agent = ForgeAgent(
                    agent_id=slot.agent_id,
                    repo_path=wt_path,
                    objective=slot.agent.objective,
                    db=self.db,
                    validate_configs=self.validate_configs,
                    max_iterations=self.max_iterations_per_agent,
                    model=self.model,
                )

            def _run_agent(slot: AgentSlot) -> AgentSlot:
                try:
                    slot.result = slot.agent.run()
                except Exception as e:
                    slot.result = False
                    slot.error = str(e)
                status = "done" if slot.result else "blocked"
                self.db.update_sub_objective_status(slot.sub_objective_id, status)
                return slot

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_concurrent_agents
            ) as executor:
                futures = {executor.submit(_run_agent, s): s for s in self.slots}
                for future in concurrent.futures.as_completed(futures):
                    slot = future.result()
                    status = "[green]succeeded[/green]" if slot.result else "[red]failed[/red]"
                    console.print(f"Agent {slot.agent_id} {status}")

        finally:
            # Clean up worktrees
            for agent_id, wt_path in worktrees.items():
                self._git("worktree", "remove", "--force", str(wt_path))

        return self.slots

    def get_successful_branches(self) -> list[str]:
        """Return branch names of agents that succeeded."""
        return [s.branch_name for s in self.slots if s.result]

    def get_failed_slots(self) -> list[AgentSlot]:
        """Return slots where agents failed."""
        return [s for s in self.slots if not s.result]
