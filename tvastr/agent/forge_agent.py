"""Forge Agent — the core iteration loop.

PLAN → PATCH → VALIDATE → keep/revert → repeat
"""

import json
import subprocess
import time
from pathlib import Path

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

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
        validate_configs: list[ValidationConfig],
        max_iterations: int = 50,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.agent_id = agent_id
        self.repo_path = repo_path.resolve()
        self.objective = objective
        self.db = db
        self.validate_configs = validate_configs
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
            f"Max iterations: {self.max_iterations}",
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

        # Run the agent (plan + patch phase)
        console.print("[dim]Agent is planning and patching...[/dim]")
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

        # Validate
        console.print("[dim]Running validation...[/dim]")
        val_start = time.time()
        results = run_validation_suite(self.validate_configs, self.repo_path, fail_fast=True)
        val_duration = time.time() - val_start

        all_passed = all(r.status == "pass" for r in results)

        # Build validation dicts
        functional_result = None
        regression_result = None
        for r in results:
            d = r.to_dict()
            if "regression" in r.name.lower() or "existing" in r.name.lower():
                regression_result = d
            else:
                functional_result = d

        if all_passed:
            console.print(f"[bold green]All validations passed![/bold green] ({val_duration:.1f}s)")
            lesson = "Changes validated successfully."
            outcome = "advanced"
        else:
            failed_names = [r.name for r in results if r.status != "pass"]
            failed_output = "\n".join(
                f"--- {r.name} ---\n{r.output[:2000]}" for r in results if r.status != "pass"
            )
            console.print(f"[bold red]Validation failed:[/bold red] {', '.join(failed_names)}")
            lesson = f"Failed validations: {', '.join(failed_names)}.\n{failed_output}"
            outcome = "reverted"
            # Revert
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
            build_status="pass",  # In P1, if code runs it "built"
            validate_functional=functional_result,
            validate_regression=regression_result,
            outcome=outcome,
            lesson=lesson,
        ))

        # Check if objective is fully met (all validations pass including any objective-specific ones)
        if all_passed and self._check_objective_met(results):
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
        return f"""## Objective
{self.objective}

## Iteration
This is iteration {iteration_num} of {self.max_iterations}.

## Journal (past iterations)
{journal_context if journal_context else "No past iterations yet. This is your first attempt."}

## Instructions
1. Read the relevant code to understand the current state
2. Plan your change — form a clear hypothesis
3. Implement the change using the tools available
4. When done, explain what you changed and why

Remember: after you finish, the system will run validation tests. If they fail, your changes will be reverted and you'll see the failure details in the next iteration."""

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
        """Check if all validations passed. In P1, passing all tests = objective met."""
        return all(r.status == "pass" for r in results)

    def _git_snapshot(self) -> str:
        """Create a snapshot of current state. Returns commit SHA or stash ref."""
        # Ensure we're in a git repo
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=self.repo_path,
        )
        if result.returncode != 0:
            # Init git if needed
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
