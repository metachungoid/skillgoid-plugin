#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 1a: analogue grounding.

Reads a checked-out analogue repo and extracts observations: declared
test commands, lint commands, and CI workflow steps. Emits a JSON list
to stdout.

Contract:
    extract_observations(repo: Path) -> list[Observation]

CLI:
    python scripts/synthesize/ground_analogue.py <repo-path>
    -> stdout: JSON list of Observation dicts
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import yaml

# Allow cross-script import when invoked directly
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@dataclasses.dataclass(frozen=True)
class Observation:
    """One observed gate-shaped fact from an analogue repo."""

    source: str  # always "analogue" for this stage
    ref: str  # relative path within the repo (or repo-name-prefixed)
    command: str  # the observed command string
    context: str  # human-readable note about where this was observed
    observed_type: str  # one of pytest|ruff|mypy|cli-command-runs|run-command|coverage

    def to_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


def detect_language(repo: Path) -> str:
    """Return language tag based on top-level manifest files."""
    if (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
        return "python"
    if (repo / "package.json").exists():
        return "node"
    if (repo / "go.mod").exists():
        return "go"
    if (repo / "Cargo.toml").exists():
        return "rust"
    return "unknown"


def parse_pyproject_test_command(pyproject: Path) -> list[str] | None:
    """If pyproject.toml declares pytest testpaths, return the implied command.

    Returns None if not parseable or no testpaths declared.
    """
    if not pyproject.exists():
        return None
    try:
        import tomllib
    except ImportError:  # pragma: no cover — Python <3.11 not supported
        return None
    data = tomllib.loads(pyproject.read_text())
    pytest_cfg = (
        data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    )
    testpaths = pytest_cfg.get("testpaths")
    if not testpaths:
        return None
    if isinstance(testpaths, str):
        testpaths = [testpaths]
    return ["pytest", *testpaths]


# Ordered: pytest, ruff, mypy, coverage. The tuple is (section-keys-to-check,
# tool-name, inferred-command). We check the first matching section key and
# stop — `tool.ruff.lint` wins over a bare `tool.ruff` when both exist, but
# either alone is enough.
_PYPROJECT_TOOL_SPECS: list[tuple[tuple[str, ...], str, str]] = [
    (("tool", "pytest", "ini_options"), "pytest", "pytest"),
    (("tool", "ruff", "lint"), "ruff", "ruff check ."),
    (("tool", "ruff"), "ruff", "ruff check ."),
    (("tool", "mypy"), "mypy", "mypy ."),
    (("tool", "coverage", "run"), "coverage", "coverage run -m pytest"),
]


def parse_pyproject_tool_sections(
    pyproject: Path,
) -> list[tuple[str, str, str]]:
    """Return (tool, inferred_command, section_name) for each recognized
    [tool.*] section found in pyproject.toml.

    One entry per tool (deduped at call site even if multiple section keys match).
    Result order: pytest, ruff, mypy, coverage. Returns [] if pyproject missing
    or malformed.
    """
    if not pyproject.exists():
        return []
    try:
        import tomllib
    except ImportError:  # pragma: no cover — Python <3.11 not supported
        return []
    try:
        data = tomllib.loads(pyproject.read_text())
    except tomllib.TOMLDecodeError:
        return []

    found: list[tuple[str, str, str]] = []
    seen_tools: set[str] = set()
    for keys, tool, command in _PYPROJECT_TOOL_SPECS:
        if tool in seen_tools:
            continue
        cursor: object = data
        for key in keys:
            if not isinstance(cursor, dict) or key not in cursor:
                cursor = None
                break
            cursor = cursor[key]
        if cursor is None:
            continue
        section_name = ".".join(keys)
        found.append((tool, command, section_name))
        seen_tools.add(tool)
    return found


def parse_workflow_steps(workflow_yml: Path) -> list[str]:
    """Extract every `run:` step's command string from a GitHub Actions YAML."""
    if not workflow_yml.exists():
        return []
    try:
        data = yaml.safe_load(workflow_yml.read_text()) or {}
    except yaml.YAMLError:
        return []
    out: list[str] = []
    for job in (data.get("jobs") or {}).values():
        for step in (job.get("steps") or []):
            run = step.get("run")
            if isinstance(run, str):
                out.append(run.strip())
            elif isinstance(run, list):
                out.extend(s.strip() for s in run if isinstance(s, str))
    return out


def _classify_command(cmd: str) -> str | None:
    """Map an observed command string to a criteria.yaml gate type."""
    head = cmd.strip().split()[0] if cmd.strip() else ""
    if head == "pytest":
        return "pytest"
    if head == "ruff":
        return "ruff"
    if head == "mypy":
        return "mypy"
    if head == "coverage":
        return "coverage"
    # Anything else we treat as a generic run-command gate. cli-command-runs
    # is reserved for explicit single-binary smoke tests; we conservatively
    # default to run-command which is more permissive.
    return "run-command"


def extract_observations(repo: Path) -> list[Observation]:
    """Walk the repo, return all observations as a deduplicated list."""
    if not repo.exists():
        raise FileNotFoundError(f"analogue repo path does not exist: {repo}")

    repo_name = repo.name
    observations: list[Observation] = []

    # Source 1: pyproject.toml declared test command
    pyproject_cmd = parse_pyproject_test_command(repo / "pyproject.toml")
    if pyproject_cmd:
        cmd_str = " ".join(pyproject_cmd)
        observations.append(Observation(
            source="analogue",
            ref=f"{repo_name}/pyproject.toml",
            command=cmd_str,
            context="declared test command",
            observed_type="pytest",
        ))

    # Source 1b: pyproject.toml tool sections (pytest-testpaths-independent).
    # Intentionally emitted BEFORE Source 2 so a config-grounded observation
    # wins on (command, observed_type) dedup over a workflow-step observation
    # with the same command+type.
    for tool, command, section in parse_pyproject_tool_sections(
        repo / "pyproject.toml"
    ):
        observations.append(Observation(
            source="analogue",
            ref=f"{repo_name}/pyproject.toml#{section}",
            command=command,
            context=f"pyproject.toml [{section}] section declares {tool} configured",
            observed_type=tool,
        ))

    # Source 2: GitHub Actions workflow run-steps
    workflows_dir = repo / ".github" / "workflows"
    if workflows_dir.exists():
        workflow_files = list(workflows_dir.glob("*.yml")) + list(
            workflows_dir.glob("*.yaml")
        )
        for wf in sorted(workflow_files):
            for step_cmd in parse_workflow_steps(wf):
                otype = _classify_command(step_cmd)
                if otype is None:
                    continue
                observations.append(Observation(
                    source="analogue",
                    ref=f"{repo_name}/.github/workflows/{wf.name}",
                    command=step_cmd,
                    context="CI workflow step",
                    observed_type=otype,
                ))

    # Dedup by (command, observed_type) — keep first occurrence
    seen: set[tuple[str, str]] = set()
    deduped: list[Observation] = []
    for o in observations:
        key = (o.command, o.observed_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(o)
    return deduped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 1a: analogue grounding")
    parser.add_argument("repo", type=Path, help="path to a checked-out analogue repo")
    args = parser.parse_args(argv)

    try:
        observations = extract_observations(args.repo)
    except FileNotFoundError as exc:
        sys.stderr.write(f"ground_analogue: {exc}\n")
        return 1

    sys.stdout.write(json.dumps([o.to_dict() for o in observations], indent=2))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
