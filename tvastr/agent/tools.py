"""Tool definitions for the forge agent. These are exposed to Claude via tool_use."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Use this to understand existing code before making changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace a specific string in a file. Use this for targeted edits instead of rewriting the whole file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root"},
                "old_string": {"type": "string", "description": "The exact string to find and replace"},
                "new_string": {"type": "string", "description": "The replacement string"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory, optionally filtered by glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path relative to repo root", "default": "."},
                "pattern": {"type": "string", "description": "Glob pattern like '*.py' or '**/*.py'", "default": "*"},
            },
        },
    },
    {
        "name": "search_code",
        "description": "Search for a pattern in the codebase using grep. Returns matching lines with file paths and line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory to search in, relative to repo root", "default": "."},
                "file_glob": {"type": "string", "description": "File glob to filter, e.g. '*.py'"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command in the repo directory. Use for git operations, running tests, building, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 120},
            },
            "required": ["command"],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict, repo_path: Path) -> str:
    """Execute a tool and return the result as a string."""
    try:
        if tool_name == "read_file":
            return _read_file(repo_path, tool_input["path"])
        elif tool_name == "write_file":
            return _write_file(repo_path, tool_input["path"], tool_input["content"])
        elif tool_name == "edit_file":
            return _edit_file(repo_path, tool_input["path"], tool_input["old_string"], tool_input["new_string"])
        elif tool_name == "list_files":
            return _list_files(repo_path, tool_input.get("path", "."), tool_input.get("pattern", "*"))
        elif tool_name == "search_code":
            return _search_code(repo_path, tool_input["pattern"], tool_input.get("path", "."), tool_input.get("file_glob"))
        elif tool_name == "run_command":
            return _run_command(repo_path, tool_input["command"], tool_input.get("timeout", 120))
        else:
            return f"Error: Unknown tool '{tool_name}'"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


def _read_file(repo_path: Path, rel_path: str) -> str:
    fp = (repo_path / rel_path).resolve()
    if not str(fp).startswith(str(repo_path.resolve())):
        return "Error: Path traversal detected"
    if not fp.exists():
        return f"Error: File not found: {rel_path}"
    content = fp.read_text()
    lines = content.split("\n")
    numbered = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
    return "\n".join(numbered)


def _write_file(repo_path: Path, rel_path: str, content: str) -> str:
    fp = (repo_path / rel_path).resolve()
    if not str(fp).startswith(str(repo_path.resolve())):
        return "Error: Path traversal detected"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content)
    return f"Written {len(content)} bytes to {rel_path}"


def _edit_file(repo_path: Path, rel_path: str, old_string: str, new_string: str) -> str:
    fp = (repo_path / rel_path).resolve()
    if not str(fp).startswith(str(repo_path.resolve())):
        return "Error: Path traversal detected"
    if not fp.exists():
        return f"Error: File not found: {rel_path}"
    content = fp.read_text()
    count = content.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {rel_path}"
    if count > 1:
        return f"Error: old_string found {count} times in {rel_path}. Be more specific."
    new_content = content.replace(old_string, new_string, 1)
    fp.write_text(new_content)
    return f"Edited {rel_path}: replaced 1 occurrence"


def _list_files(repo_path: Path, rel_path: str, pattern: str) -> str:
    dp = (repo_path / rel_path).resolve()
    if not str(dp).startswith(str(repo_path.resolve())):
        return "Error: Path traversal detected"
    if not dp.exists():
        return f"Error: Directory not found: {rel_path}"
    files = sorted(dp.glob(pattern))
    # Limit output
    results = []
    for f in files[:200]:
        try:
            rel = f.relative_to(repo_path)
        except ValueError:
            rel = f
        suffix = "/" if f.is_dir() else ""
        results.append(f"{rel}{suffix}")
    output = "\n".join(results)
    if len(files) > 200:
        output += f"\n... and {len(files) - 200} more"
    return output or "(empty directory)"


def _search_code(repo_path: Path, pattern: str, rel_path: str, file_glob: str | None) -> str:
    cmd = ["grep", "-rn", "--include", file_glob or "*", pattern, rel_path]
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=repo_path, timeout=30,
    )
    output = result.stdout.strip()
    if not output:
        return "No matches found"
    lines = output.split("\n")
    if len(lines) > 100:
        return "\n".join(lines[:100]) + f"\n... and {len(lines) - 100} more matches"
    return output


def _run_command(repo_path: Path, command: str, timeout: int) -> str:
    # Block dangerous commands
    dangerous = ["rm -rf /", "rm -rf ~", "mkfs", "dd if=", "> /dev/"]
    for d in dangerous:
        if d in command:
            return f"Error: Blocked dangerous command pattern: {d}"

    result = subprocess.run(
        command, shell=True, capture_output=True, text=True,
        cwd=repo_path, timeout=min(timeout, 600),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
    if result.returncode != 0:
        output += f"\n(exit code: {result.returncode})"
    return output.strip() or "(no output)"
