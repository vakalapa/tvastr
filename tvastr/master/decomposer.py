"""Decompose an objective into independent sub-objectives using Claude."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import anthropic


@dataclass
class SubObjective:
    """A single sub-objective extracted from the main objective."""

    description: str
    acceptance_criteria: list[str]
    priority: int  # lower = higher priority
    depends_on: list[int]  # indices of other sub-objectives this depends on
    suggested_files: list[str]  # file patterns the agent should focus on


DECOMPOSE_PROMPT = """\
You are a technical project decomposer. Given a software objective, break it down \
into independent sub-objectives that can be worked on in parallel by separate agents.

Rules:
1. Each sub-objective should be independently achievable and testable.
2. Minimize dependencies between sub-objectives. If B depends on A, mark it.
3. Each sub-objective should have clear acceptance criteria.
4. Suggest which files/directories each agent should focus on (to minimize conflicts).
5. Order by priority (0 = highest).
6. Aim for 2-5 sub-objectives. Don't over-decompose.

Respond with ONLY a JSON array. Each element:
{
  "description": "What to do",
  "acceptance_criteria": ["criterion 1", "criterion 2"],
  "priority": 0,
  "depends_on": [],
  "suggested_files": ["path/pattern"]
}
"""


async def decompose_objective(
    objective_text: str,
    repo_context: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[SubObjective]:
    """Use Claude to decompose an objective into sub-objectives.

    Args:
        objective_text: The full objective markdown text.
        repo_context: Optional context about the repo (file listing, README snippet).
        model: Claude model to use for decomposition.

    Returns:
        List of SubObjective instances.
    """
    user_message = f"# Objective\n\n{objective_text}"
    if repo_context:
        user_message += f"\n\n# Repo Context\n\n{repo_context}"

    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=DECOMPOSE_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    text = response.content[0].text
    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r"\[.*\]", text, re.DOTALL)
    if not json_match:
        raise ValueError(f"Failed to parse decomposition response: {text[:500]}")

    raw = json.loads(json_match.group())
    return [
        SubObjective(
            description=item["description"],
            acceptance_criteria=item.get("acceptance_criteria", []),
            priority=item.get("priority", 0),
            depends_on=item.get("depends_on", []),
            suggested_files=item.get("suggested_files", []),
        )
        for item in raw
    ]


def decompose_from_checklist(objective_text: str) -> list[SubObjective] | None:
    """Try to extract sub-objectives from markdown checklist items.

    If the objective has a clear "Sub-objectives" section with checkboxes,
    parse them directly without calling the LLM. Returns None if no
    checklist found.
    """
    lines = objective_text.split("\n")
    in_section = False
    items: list[str] = []

    for line in lines:
        stripped = line.strip()
        if re.match(r"#+\s*(sub.?objectives|tasks|deliverables)", stripped, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("#"):
                break  # next section
            checkbox = re.match(r"- \[[ x]\]\s+(.*)", stripped)
            if checkbox:
                items.append(checkbox.group(1))

    if not items:
        return None

    return [
        SubObjective(
            description=item,
            acceptance_criteria=[],
            priority=i,
            depends_on=[],
            suggested_files=[],
        )
        for i, item in enumerate(items)
    ]
