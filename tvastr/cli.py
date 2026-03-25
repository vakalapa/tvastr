"""Tvastr CLI — entry point for forge runs."""
from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel

from tvastr.agent.forge_agent import ForgeAgent
from tvastr.infra.validator import ValidationConfig
from tvastr.state.db import StateDB

console = Console()


@click.group()
def main():
    """Tvastr — autonomous craftsman that forges code changes."""
    pass


@main.command()
@click.option("--objective", "-o", required=True, type=click.Path(exists=True), help="Path to objective.md")
@click.option("--repo", "-r", required=True, type=click.Path(exists=True), help="Path to the target repo")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to repo.yaml config (optional)")
@click.option("--max-iterations", "-n", default=50, help="Max iterations before stopping")
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model to use")
@click.option("--agent-id", default="forge-1", help="Agent identifier")
@click.option("--multi-agent", is_flag=True, default=False, help="Use multi-agent mode with Forge Master")
@click.option("--max-agents", default=3, help="Max concurrent agents (multi-agent mode)")
@click.option("--parallel", is_flag=True, default=False, help="Run agents in parallel (multi-agent mode)")
def run(objective, repo, config, max_iterations, model, agent_id, multi_agent, max_agents, parallel):
    """Run the forge loop against a repo.

    The agent discovers how to build and test the repo by reading its
    documentation (README.md, CLAUDE.md, Makefile, etc.). Optionally,
    provide a repo.yaml with validation commands as an outer safety net.

    Use --multi-agent to decompose the objective and run multiple agents.
    """
    repo_path = Path(repo).resolve()
    objective_text = Path(objective).read_text()

    console.print(Panel(
        f"[bold]Objective:[/bold]\n{objective_text[:500]}",
        title="Tvastr",
        border_style="blue",
    ))

    # Load validation config (optional — agent discovers build/test from repo docs)
    validate_configs = _load_validate_configs(config, repo_path)

    if validate_configs:
        console.print(f"[dim]Loaded {len(validate_configs)} validation config(s) as outer safety net.[/dim]")
    else:
        console.print("[dim]No validation configs — agent will discover build/test from repo docs.[/dim]")

    # Init state DB
    db_path = repo_path / ".tvastr" / "tvastr.db"
    db = StateDB(db_path)

    if multi_agent:
        # Multi-agent mode: Forge Master decomposes and coordinates
        from tvastr.master.orchestrator import ForgeMaster

        master = ForgeMaster(
            repo_path=repo_path,
            objective=objective_text,
            db=db,
            validate_configs=validate_configs,
            max_iterations_per_agent=max_iterations,
            max_concurrent_agents=max_agents,
            model=model,
            parallel=parallel,
        )
        success = master.run()
    else:
        # Single-agent mode
        agent = ForgeAgent(
            agent_id=agent_id,
            repo_path=repo_path,
            objective=objective_text,
            db=db,
            validate_configs=validate_configs,
            max_iterations=max_iterations,
            model=model,
        )
        success = agent.run()

    sys.exit(0 if success else 1)


@main.command()
@click.option("--repo", "-r", required=True, type=click.Path(exists=True), help="Path to the target repo")
@click.option("--agent-id", default=None, help="Filter by agent ID")
@click.option("--limit", "-n", default=20, help="Number of iterations to show")
def journal(repo, agent_id, limit):
    """View the forge journal for a repo."""
    repo_path = Path(repo).resolve()
    db_path = repo_path / ".tvastr" / "tvastr.db"

    if not db_path.exists():
        console.print("[yellow]No forge journal found for this repo.[/yellow]")
        sys.exit(0)

    db = StateDB(db_path)
    iterations = db.get_iterations(agent_id=agent_id, limit=limit)

    if not iterations:
        console.print("[yellow]No iterations recorded yet.[/yellow]")
        return

    for it in reversed(iterations):
        color = "green" if it["outcome"] == "advanced" else "red"
        console.print(Panel(
            f"[bold]Hypothesis:[/bold] {it['hypothesis'][:300]}\n"
            f"[bold]Files:[/bold] {it['files_changed']}\n"
            f"[bold]Outcome:[/bold] [{color}]{it['outcome']}[/{color}]\n"
            f"[bold]Lesson:[/bold] {it['lesson'][:500]}",
            title=f"Iteration {it['iteration_num']} — {it['agent_id']}",
            border_style=color,
        ))


@main.command()
@click.option("--repo", "-r", required=True, type=click.Path(exists=True))
def init(repo):
    """Initialize tvastr config for a repo (optional — agents can discover everything from docs)."""
    repo_path = Path(repo).resolve()
    tvastr_dir = repo_path / ".tvastr"
    tvastr_dir.mkdir(exist_ok=True)

    config_path = tvastr_dir / "repo.yaml"
    if config_path.exists():
        console.print(f"[yellow]Config already exists: {config_path}[/yellow]")
        return

    default_config = {
        "repo": str(repo_path),
        "hints": {
            "test_command": "pytest",
        },
    }
    config_path.write_text(yaml.dump(default_config, default_flow_style=False))
    console.print(f"[green]Created {config_path}[/green]")
    console.print("This config is optional — the agent discovers build/test from repo docs.")
    console.print("Add 'validate' section if you want an outer safety net for test commands.")


def _load_validate_configs(config_path: str | None, repo_path: Path) -> list[ValidationConfig]:
    """Load validation configs from repo.yaml (optional)."""
    paths_to_try = []
    if config_path:
        paths_to_try.append(Path(config_path))
    paths_to_try.append(repo_path / ".tvastr" / "repo.yaml")

    for p in paths_to_try:
        if p.exists():
            raw = yaml.safe_load(p.read_text())
            return _parse_validate_configs(raw)

    return []


def _parse_validate_configs(raw: dict) -> list[ValidationConfig]:
    """Parse validation configs from raw YAML dict."""
    configs = []
    validate = raw.get("validate", {})

    for tier in ("functional", "regression", "performance"):
        for item in validate.get(tier, []):
            configs.append(ValidationConfig(
                name=item["name"],
                command=item["command"],
                timeout=item.get("timeout", 300),
            ))

    return configs


if __name__ == "__main__":
    main()
