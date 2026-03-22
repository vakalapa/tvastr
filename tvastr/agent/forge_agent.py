"""Forge Agent — the core iteration loop.

DISCOVER → PLAN → PATCH → VALIDATE → keep/revert → repeat

The agent discovers how to build/test by reading the repo's own documentation.
Tvastr only orchestrates the iteration loop and manages state.
"""

import json
import subprocess
import time
from pathlib import Path

import anthropic
from rich.console import Console
from rich.panel import Panel

from tvastr.agent.tools import TOOL_DEFINITIONS, execute_tool
from tvastr.infra.validator import ValidationConfig, run_validation_suite
from tvastr.state.db import Iteration, StateDB

console = Console()


class ForgeAgent:
    def __init__(
        self,
        agent_id: str,
        repo_path: Path,
        objective: str,
        db: StateDB,
        validate_configs: list[ValidationConfig] | None = None,
        max_iterations: int = 50,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.agent_id = agent_id
        self.repo_path = repo_path.resolve()
        self.objective = objective
        self.db = db
        self.validate_configs = validate_configs or []
        self.max_iterations = max_iterations
        self.model = model
        self.client = anthropic.Anthropic()
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        prompt_path = Path(__file__).parent.parent / "prompts" / "agent_system.md"
        return prompt_path.read_text()

    def run(self):
        """Run the forge loop until objective is met or budget exhausted."""
        console.print(Panel(
            f"[bold]Tvastr Forge Agent[/bold] — {self.agent_id}\n"
            f"Repo: {self.repo_path}\n"
            f"Max iterations: {self.max_iterations}\n"
            f"Validation: {'repo.yaml configs' if self.validate_configs else 'agent-driven (discovers from repo docs)'}",
            title="Starting Forge",
            border_style="blue",
        ))

        start_iter = self.db.get_latest_iteration_num(self.agent_id)

        for i in range(start_iter + 1, start_iter + self.max_iterations + 1):
            console.rule(f"[bold cyan]Iteration {i}[/bold cyan]")
            outcome = self._run_iteration(i)

            if outcome == "objective_met":
                console.print(Panel(
                    f"[bold green]Objective met after {i} iterations![/bold green]",
                    border_style="green",
                ))
                return True

            if outcome == "budget_exhausted":
                break

        console.print(Panel(
            "[bold red]Budget exhausted. Objective not fully met.[/bold red]",
            border_style="red",
        ))
        return False

    def _run_iteration(self, iteration_num: int) -> str:
        """Run a single forge iteration. Returns 'advanced', 'reverted', or 'objective_met'."""

        # Snapshot current state so we can revert
        snapshot_sha = self._git_snapshot()

        # Build context for the agent
        journal_context = self._build_journal_context()
        user_message = self._build_iteration_prompt(iteration_num, journal_context)

        # Run the agent (discover + plan + patch + self-validate phase)
        console.print("[dim]Agent is working (discover → plan → patch → validate)...[/dim]")
        hypothesis, files_changed = self._run_agent_turn(user_message)

        if not files_changed:
            console.print("[yellow]Agent made no changes this iteration.[/yellow]")
            self.db.log_iteration(Iteration(
                agent_id=self.agent_id,
                sub_objective_id=None,
                iteration_num=iteration_num,
                hypothesis=hypothesis,
                outcome="no_changes",
                lesson="Agent chose not to make changes.",
            ))
            return "reverted"

        console.print(f"[dim]Files changed: {', '.join(files_changed)}[/dim]")
        console.print(f"[dim]Hypothesis: {hypothesis}[/dim]")

        # Commit the patch
        patch_sha = self._git_commit(iteration_num, hypothesis)

        # Outer validation — if configs are provided, run them as a safety net.
        # If no configs, trust the agent's self-validation via run_command.
        validate_results = []
        all_passed = True

        if self.validate_configs:
            console.print("[dim]Running outer validation (from repo.yaml)...[/dim]")
            val_start = time.time()
            results = run_validation_suite(self.validate_configs, self.repo_path, fail_fast=True)
            val_duration = time.time() - val_start

            all_passed = all(r.status == "pass" for r in results)
            validate_results = [r.to_dict() for r in results]

            if all_passed:
                console.print(f"[bold green]All validations passed![/bold green] ({val_duration:.1f}s)")
            else:
                failed_names = [r.name for r in results if r.status != "pass"]
                console.print(f"[bold red]Validation failed:[/bold red] {', '.join(failed_names)}")
        else:
            console.print("[dim]No outer validation configs — trusting agent's self-validation.[/dim]")

        if all_passed:
            lesson = "Changes validated successfully."
            outcome = "advanced"
        else:
            failed_output = "\n".join(
                f"--- {r['name']} ---\n{r['output'][:2000]}"
                for r in validate_results if r["status"] != "pass"
            )
            lesson = f"Failed validations: {', '.join(r['name'] for r in validate_results if r['status'] != 'pass')}.\n{failed_output}"
            outcome = "reverted"
            self._git_revert(snapshot_sha)
            console.print("[dim]Changes reverted.[/dim]")

        # Log iteration
        self.db.log_iteration(Iteration(
            agent_id=self.agent_id,
            sub_objective_id=None,
            iteration_num=iteration_num,
            hypothesis=hypothesis,
            files_changed=files_changed,
            patch_sha=patch_sha,
            validate_results=validate_results if validate_results else None,
            outcome=outcome,
            lesson=lesson,
        ))

        # Check if objective is fully met
        if all_passed:
            return "objective_met"

        return outcome

    def _run_agent_turn(self, user_message: str) -> tuple[str, list[str]]:
        """Run one agent turn with tool use. Returns (hypothesis, files_changed)."""
        messages = [{"role": "user", "content": user_message}]
        files_changed = set()
        hypothesis = ""

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8096,
                system=self.system_prompt,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            # Collect text and tool uses
            tool_uses = []
            text_parts = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if text_parts:
                hypothesis = "\n".join(text_parts)

            # If no tool use, agent is done
            if response.stop_reason == "end_turn" or not tool_uses:
                break

            # Execute tools and build tool results
            assistant_content = response.content
            tool_results = []

            for tool_use in tool_uses:
                console.print(f"  [dim]→ {tool_use.name}({_summarize_input(tool_use.input)})[/dim]")
                result = execute_tool(tool_use.name, tool_use.input, self.repo_path)

                # Track file changes
                if tool_use.name in ("write_file", "edit_file"):
                    files_changed.add(tool_use.input.get("path", ""))

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result[:10000],  # cap tool output
                })

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        return hypothesis, sorted(files_changed)

    def _build_iteration_prompt(self, iteration_num: int, journal_context: str) -> str:
        discovery_note = ""
        if iteration_num == 1 or not journal_context:
            discovery_note = """
## Discovery (IMPORTANT — first iteration)
Before making any changes, discover how this repo works:
1. Read README.md, CONTRIBUTING.md, CLAUDE.md (if they exist)
2. Check build tooling: Makefile, package.json, pyproject.toml, Cargo.toml, go.mod
3. Check CI configs: .github/workflows/*.yml, .gitlab-ci.yml
4. Understand test commands and conventions
5. Use this knowledge to build, test, and validate your changes.
"""

        return f"""## Objective
{self.objective}

## Iteration
This is iteration {iteration_num} of {self.max_iterations}.

## Journal (past iterations)
{journal_context if journal_context else "No past iterations yet. This is your first attempt."}
{discovery_note}
## Instructions
1. Read the relevant code to understand the current state
2. Plan your change — form a clear hypothesis
3. Implement the change using the tools available
4. Run the repo's build/test commands to validate your changes (use run_command)
5. When done, explain what you changed and why

Remember: if outer validation tests exist, they will also run after you finish. If they fail, your changes will be reverted and you'll see the failure details in the next iteration."""

    def _build_journal_context(self) -> str:
        iterations = self.db.get_iterations(self.agent_id, limit=10)
        if not iterations:
            return ""

        lines = []
        for it in reversed(iterations):  # chronological order
            status_icon = "pass" if it["outcome"] == "advanced" else "FAIL"
            lines.append(
                f"### Iteration {it['iteration_num']} [{status_icon}]\n"
                f"Hypothesis: {it['hypothesis'][:500]}\n"
                f"Files: {it['files_changed']}\n"
                f"Outcome: {it['outcome']}\n"
                f"Lesson: {it['lesson'][:1000]}\n"
            )
        return "\n".join(lines)

    def _check_objective_met(self, results: list) -> bool:
        """Check if all validations passed."""
        return all(r.status == "pass" for r in results)

    def _git_snapshot(self) -> str:
        """Create a snapshot of current state. Returns commit SHA."""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=self.repo_path,
        )
        if result.returncode != 0:
            subprocess.run(["git", "init"], cwd=self.repo_path, capture_output=True)
            subprocess.run(["git", "add", "-A"], cwd=self.repo_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "tvastr: initial snapshot", "--allow-empty"],
                cwd=self.repo_path, capture_output=True,
            )
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, cwd=self.repo_path,
            )
        return result.stdout.strip()

    def _git_commit(self, iteration_num: int, hypothesis: str) -> str:
        """Commit current changes and return SHA."""
        subprocess.run(["git", "add", "-A"], cwd=self.repo_path, capture_output=True)
        msg = f"tvastr: iteration {iteration_num}\n\n{hypothesis[:500]}"
        subprocess.run(
            ["git", "commit", "-m", msg, "--allow-empty"],
            cwd=self.repo_path, capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=self.repo_path,
        )
        return result.stdout.strip()

    def _git_revert(self, snapshot_sha: str):
        """Revert to a previous snapshot."""
        subprocess.run(
            ["git", "reset", "--hard", snapshot_sha],
            cwd=self.repo_path, capture_output=True,
        )


def _summarize_input(inp: dict) -> str:
    """Short summary of tool input for logging."""
    if "path" in inp:
        extra = ""
        if "old_string" in inp:
            extra = f", edit"
        elif "content" in inp:
            extra = f", {len(inp['content'])} chars"
        return f"{inp['path']}{extra}"
    if "pattern" in inp:
        return inp["pattern"]
    if "command" in inp:
        cmd = inp["command"]
        return cmd if len(cmd) < 60 else cmd[:57] + "..."
    return str(inp)[:60]
