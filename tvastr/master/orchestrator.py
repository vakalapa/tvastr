"""Forge Master Orchestrator — coordinates multi-agent forge runs.

The orchestrator is the top-level entry point for multi-agent mode.
It decomposes an objective, spawns agents, manages merging, and
determines when the overall objective is met.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tvastr.infra.validator import ValidationConfig
from tvastr.master.decomposer import (
    SubObjective,
    decompose_from_checklist,
    decompose_objective,
)
from tvastr.master.merger import Merger
from tvastr.master.scheduler import AgentSlot, MergeStrategy, Scheduler
from tvastr.state.db import StateDB

console = Console()


class ForgeMaster:
    """Orchestrates a multi-agent forge run.

    Flow:
        1. Decompose objective into sub-objectives
        2. Store sub-objectives in DB
        3. Schedule agents (one per sub-objective)
        4. Run agents (sequential or parallel)
        5. Merge successful branches
        6. Run combined validation
        7. Report results
    """

    def __init__(
        self,
        repo_path: Path,
        objective: str,
        db: StateDB,
        validate_configs: list[ValidationConfig] | None = None,
        max_iterations_per_agent: int = 50,
        max_concurrent_agents: int = 3,
        model: str = "claude-sonnet-4-20250514",
        strategy: MergeStrategy = MergeStrategy.ISOLATED,
        parallel: bool = False,
    ):
        self.repo_path = repo_path.resolve()
        self.objective = objective
        self.db = db
        self.validate_configs = validate_configs or []
        self.max_iterations_per_agent = max_iterations_per_agent
        self.max_concurrent_agents = max_concurrent_agents
        self.model = model
        self.strategy = strategy
        self.parallel = parallel

    def run(self) -> bool:
        """Run the full multi-agent forge flow. Returns True if objective met."""
        console.print(Panel(
            "[bold]Tvastr Forge Master[/bold] — Multi-Agent Mode\n"
            f"Repo: {self.repo_path}\n"
            f"Strategy: {self.strategy.value}\n"
            f"Max agents: {self.max_concurrent_agents}\n"
            f"Parallel: {self.parallel}",
            title="Forge Master",
            border_style="magenta",
        ))

        # Step 1: Decompose objective
        console.rule("[bold]Phase 1: Decompose Objective[/bold]")
        sub_objectives = self._decompose()

        if not sub_objectives:
            console.print("[red]Failed to decompose objective. Falling back to single-agent mode.[/red]")
            return self._fallback_single_agent()

        self._display_sub_objectives(sub_objectives)

        # Step 2: Store sub-objectives in DB
        db_sub_objs = []
        for sub_obj in sub_objectives:
            obj_id = self.db.add_sub_objective(
                description=sub_obj.description,
                priority=sub_obj.priority,
                depends_on=sub_obj.depends_on,
            )
            db_sub_objs.append({
                "id": obj_id,
                "description": sub_obj.description,
                "priority": sub_obj.priority,
            })

        # Step 3: Schedule agents
        console.rule("[bold]Phase 2: Schedule Agents[/bold]")
        scheduler = Scheduler(
            repo_path=self.repo_path,
            db=self.db,
            validate_configs=self.validate_configs,
            max_iterations_per_agent=self.max_iterations_per_agent,
            max_concurrent_agents=self.max_concurrent_agents,
            model=self.model,
            strategy=self.strategy,
        )
        slots = scheduler.schedule(db_sub_objs, self.objective)
        console.print(f"Scheduled {len(slots)} agents.")

        # Step 4: Run agents
        console.rule("[bold]Phase 3: Run Agents[/bold]")
        if self.parallel:
            scheduler.run_parallel()
        else:
            scheduler.run_sequential()

        # Step 5: Report agent results
        self._display_agent_results(slots)

        successful_branches = scheduler.get_successful_branches()
        if not successful_branches:
            console.print("[red]No agents succeeded. Objective not met.[/red]")
            return False

        # Step 6: Merge successful branches
        console.rule("[bold]Phase 4: Merge & Validate[/bold]")
        base_branch = self._current_branch()
        merger = Merger(
            repo_path=self.repo_path,
            base_branch=base_branch,
            validate_configs=self.validate_configs,
        )

        merge_results = merger.merge_branches(
            successful_branches,
            validate_after_each=True,
        )

        merged_count = sum(1 for r in merge_results if r.success and r.validation_passed)
        console.print(f"Merged {merged_count}/{len(successful_branches)} branches successfully.")

        # Step 7: Combined validation
        if merged_count > 0:
            overall_pass = merger.combined_validation()
        else:
            overall_pass = False

        # Final report
        self._display_final_report(slots, merge_results, overall_pass)
        return overall_pass

    def _decompose(self) -> list[SubObjective]:
        """Decompose the objective into sub-objectives."""
        # Try checklist extraction first (fast, no LLM call)
        checklist_result = decompose_from_checklist(self.objective)
        if checklist_result:
            console.print(f"[dim]Extracted {len(checklist_result)} sub-objectives from checklist.[/dim]")
            return checklist_result

        # Fall back to LLM decomposition
        console.print("[dim]Using LLM to decompose objective...[/dim]")
        repo_context = self._build_repo_context()

        try:
            return asyncio.run(
                decompose_objective(self.objective, repo_context, self.model)
            )
        except Exception as e:
            console.print(f"[red]Decomposition failed: {e}[/red]")
            return []

    def _build_repo_context(self) -> str:
        """Build a brief context about the repo for the decomposer."""
        lines = [f"Repository: {self.repo_path.name}"]

        # File listing (top-level)
        result = subprocess.run(
            ["find", ".", "-maxdepth", "2", "-type", "f", "-not", "-path", "./.git/*"],
            capture_output=True, text=True, cwd=self.repo_path,
        )
        if result.returncode == 0:
            files = result.stdout.strip().split("\n")[:50]
            lines.append(f"\nFiles:\n" + "\n".join(files))

        # README snippet
        readme = self.repo_path / "README.md"
        if readme.exists():
            content = readme.read_text()[:2000]
            lines.append(f"\nREADME.md:\n{content}")

        return "\n".join(lines)

    def _fallback_single_agent(self) -> bool:
        """Fall back to single-agent mode if decomposition fails."""
        from tvastr.agent.forge_agent import ForgeAgent

        agent = ForgeAgent(
            agent_id="agent-0",
            repo_path=self.repo_path,
            objective=self.objective,
            db=self.db,
            validate_configs=self.validate_configs,
            max_iterations=self.max_iterations_per_agent,
            model=self.model,
        )
        return agent.run()

    def _current_branch(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=self.repo_path,
        )
        return result.stdout.strip()

    def _display_sub_objectives(self, sub_objectives: list[SubObjective]):
        table = Table(title="Sub-Objectives")
        table.add_column("#", style="dim")
        table.add_column("Description")
        table.add_column("Priority", justify="center")
        table.add_column("Depends On", justify="center")

        for i, sub in enumerate(sub_objectives):
            deps = ", ".join(str(d) for d in sub.depends_on) if sub.depends_on else "—"
            table.add_row(str(i), sub.description[:80], str(sub.priority), deps)

        console.print(table)

    def _display_agent_results(self, slots: list[AgentSlot]):
        table = Table(title="Agent Results")
        table.add_column("Agent")
        table.add_column("Sub-Objective")
        table.add_column("Status")
        table.add_column("Branch")

        for slot in slots:
            if slot.result:
                status = "[green]succeeded[/green]"
            elif slot.error:
                status = f"[red]error: {slot.error[:40]}[/red]"
            else:
                status = "[red]failed[/red]"

            table.add_row(
                slot.agent_id,
                slot.sub_objective_desc[:50],
                status,
                slot.branch_name,
            )

        console.print(table)

    def _display_final_report(self, slots, merge_results, overall_pass):
        merged = sum(1 for r in merge_results if r.success and r.validation_passed)
        total = len(slots)
        succeeded = sum(1 for s in slots if s.result)

        status_color = "green" if overall_pass else "red"
        status_text = "OBJECTIVE MET" if overall_pass else "OBJECTIVE NOT MET"

        console.print(Panel(
            f"[bold {status_color}]{status_text}[/bold {status_color}]\n\n"
            f"Agents: {succeeded}/{total} succeeded\n"
            f"Branches merged: {merged}/{succeeded}\n"
            f"Combined validation: {'passed' if overall_pass else 'failed'}",
            title="Final Report",
            border_style=status_color,
        ))
