"""Validation framework — runs tests and parses results."""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ValidationResult:
    status: str  # "pass" | "fail" | "error" | "skip"
    name: str
    output: str
    duration_secs: float
    failed_tests: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "name": self.name,
            "output": self.output[:5000],  # truncate for journal
            "duration_secs": self.duration_secs,
            "failed_tests": self.failed_tests,
        }


@dataclass
class ValidationConfig:
    name: str
    command: str
    timeout: int = 300  # seconds


def run_validation(config: ValidationConfig, repo_path: Path) -> ValidationResult:
    """Run a single validation command and return structured results."""
    start = time.time()
    try:
        result = subprocess.run(
            config.command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=config.timeout,
        )
        duration = time.time() - start
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr

        if result.returncode == 0:
            return ValidationResult(
                status="pass",
                name=config.name,
                output=output,
                duration_secs=duration,
            )
        else:
            failed = _extract_failed_tests(output)
            return ValidationResult(
                status="fail",
                name=config.name,
                output=output,
                duration_secs=duration,
                failed_tests=failed,
            )

    except subprocess.TimeoutExpired:
        return ValidationResult(
            status="error",
            name=config.name,
            output=f"Timed out after {config.timeout}s",
            duration_secs=config.timeout,
        )
    except Exception as e:
        return ValidationResult(
            status="error",
            name=config.name,
            output=f"{type(e).__name__}: {e}",
            duration_secs=time.time() - start,
        )


def run_validation_suite(
    configs: list[ValidationConfig], repo_path: Path, fail_fast: bool = True
) -> list[ValidationResult]:
    """Run a suite of validations. If fail_fast, stop on first failure."""
    results = []
    for config in configs:
        result = run_validation(config, repo_path)
        results.append(result)
        if fail_fast and result.status != "pass":
            break
    return results


def _extract_failed_tests(output: str) -> list[str]:
    """Best-effort extraction of failed test names from pytest/go test output."""
    failed = []
    for line in output.split("\n"):
        # pytest: FAILED tests/test_foo.py::test_bar
        if line.strip().startswith("FAILED "):
            failed.append(line.strip().removeprefix("FAILED ").split(" ")[0])
        # go test: --- FAIL: TestFoo (0.00s)
        if line.strip().startswith("--- FAIL:"):
            parts = line.strip().split()
            if len(parts) >= 3:
                failed.append(parts[2])
    return failed or None
