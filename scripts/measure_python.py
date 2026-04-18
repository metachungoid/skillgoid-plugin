#!/usr/bin/env python3
"""Skillgoid Python gate adapter.

Reads a subset of criteria.yaml (the gates to run) and a project path;
runs each gate; emits a structured JSON report on stdout.

Contract: stdout is always valid JSON. Stderr carries debug noise. Exit
code 0 if all gates passed, 1 if any failed, 2 on internal error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    stdout: str
    stderr: str
    hint: str


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _resolve_tool(name: str) -> Path | None:
    """Find a tool binary — first next to the running Python interpreter
    (i.e. in the same venv), then on PATH. Returns None if missing."""
    venv_candidate = Path(sys.executable).parent / name
    if venv_candidate.exists():
        return venv_candidate
    found = shutil.which(name)
    return Path(found) if found else None


def _gate_run_command(gate: dict, project: Path) -> GateResult:
    cmd = gate.get("command") or []
    if not cmd:
        return GateResult(gate["id"], False, "", "", "no command specified; add `command:` to gate")
    expect_exit = gate.get("expect_exit", 0)
    code, out, err = _run(cmd, project)
    passed = code == expect_exit
    hint = "" if passed else f"exit={code}, expected {expect_exit}"
    return GateResult(gate["id"], passed, out, err, hint)


def _gate_pytest(gate: dict, project: Path) -> GateResult:
    args = gate.get("args") or []
    env_path = str(project / "src")
    existing = os.environ.get("PYTHONPATH", "")
    env = {**os.environ, "PYTHONPATH": env_path + (os.pathsep + existing if existing else "")}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    passed = proc.returncode == 0
    hint = "" if passed else "pytest exited nonzero — read stdout for failing test names"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)


def _gate_ruff(gate: dict, project: Path) -> GateResult:
    ruff_bin = _resolve_tool("ruff")
    if ruff_bin is None:
        return GateResult(
            gate["id"], False, "", "",
            "ruff not found next to the python interpreter or on PATH — install with `pip install ruff`",
        )
    args = gate.get("args") or ["check", "."]
    proc = subprocess.run(
        [str(ruff_bin), *args],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    passed = proc.returncode == 0
    hint = "" if passed else "ruff flagged lint issues — fix or add to ignore config"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)


GATE_DISPATCH = {
    "run-command": _gate_run_command,
    "pytest": _gate_pytest,
    "ruff": _gate_ruff,
}


def run_gates(criteria: dict, project: Path) -> dict[str, Any]:
    results: list[GateResult] = []
    for gate in criteria.get("gates", []):
        gate_id = gate.get("id", "<unknown>")
        gate_type = gate.get("type")
        if gate_type is None:
            results.append(GateResult(gate_id, False, "", "", "gate missing `type` field"))
            continue
        handler = GATE_DISPATCH.get(gate_type)
        if handler is None:
            results.append(GateResult(gate_id, False, "", "", f"unsupported gate type: {gate_type} — add adapter support"))
            continue
        results.append(handler(gate, project))
    return {
        "passed": all(r.passed for r in results),
        "results": [asdict(r) for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid Python gate adapter")
    ap.add_argument("--project", required=True, type=Path)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--criteria-file", type=Path, help="Path to a criteria.yaml subset")
    src.add_argument("--criteria-stdin", action="store_true", help="Read criteria YAML from stdin")
    args = ap.parse_args(argv)

    try:
        if args.criteria_stdin:
            criteria = yaml.safe_load(sys.stdin.read())
        else:
            criteria = yaml.safe_load(args.criteria_file.read_text())
        report = run_gates(criteria or {}, args.project.resolve())
    except Exception as exc:
        sys.stderr.write(f"measure_python: {exc}\n")
        json.dump({"passed": False, "results": [], "error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 2

    json.dump(report, sys.stdout)
    sys.stdout.write("\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
