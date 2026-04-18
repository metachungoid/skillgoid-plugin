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
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

DEFAULT_GATE_TIMEOUT = 300
_COVERAGE_RE = re.compile(r"coverage:\s*([0-9.]+)%", re.IGNORECASE)


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    stdout: str
    stderr: str
    hint: str


def _run(cmd: list[str], cwd: Path, timeout: int | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return 124, out, err  # 124 = conventional timeout exit code
    return proc.returncode, proc.stdout, proc.stderr


def _merge_env(project: Path, gate_env: dict) -> dict:
    """Merge gate env: overrides onto os.environ. Relative paths in known
    path-like vars (PYTHONPATH, PATH) are resolved against project dir.

    Always exports SKILLGOID_PYTHON=sys.executable so shell command strings
    (e.g., ["bash", "-c", "$SKILLGOID_PYTHON -m myproj"]) can reference a
    guaranteed python binary without worrying about whether `python` is on PATH.
    User-provided gate env: CAN override SKILLGOID_PYTHON if needed (e.g., to
    test against a different interpreter).
    """
    merged = {**os.environ, "SKILLGOID_PYTHON": sys.executable}
    for k, v in (gate_env or {}).items():
        if k in ("PYTHONPATH", "PATH"):
            parts = []
            for part in str(v).split(os.pathsep):
                if part and not os.path.isabs(part):
                    part = str((project / part).resolve())
                parts.append(part)
            merged[k] = os.pathsep.join(parts)
        else:
            merged[k] = str(v)
    return merged


def _resolve_python(cmd: list[str], env: dict) -> list[str]:
    """Replace bare 'python' with sys.executable unless opt-out is set.

    Other command names (python3, absolute paths, any other executable)
    pass through unchanged. Opt-out: set env SKILLGOID_PYTHON_NO_RESOLVE=1
    if the user genuinely wants bare 'python' from PATH.
    """
    if not cmd:
        return cmd
    if env.get("SKILLGOID_PYTHON_NO_RESOLVE") == "1":
        return cmd
    if cmd[0] == "python":
        return [sys.executable, *cmd[1:]]
    return cmd


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
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    env = _merge_env(project, gate.get("env") or {})
    cmd = _resolve_python(cmd, env)
    try:
        proc = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True, check=False, timeout=timeout)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return GateResult(gate["id"], False, out, err,
                          f"gate timed out after {timeout}s — check for infinite loops or hung I/O")
    passed = code == expect_exit
    hint = "" if passed else f"exit={code}, expected {expect_exit}"
    return GateResult(gate["id"], passed, out, err, hint)


def _gate_pytest(gate: dict, project: Path) -> GateResult:
    args = gate.get("args") or []
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    gate_env = gate.get("env") or {}
    env = _merge_env(project, gate_env)
    if "PYTHONPATH" not in gate_env:
        env_path = str(project / "src")
        existing = os.environ.get("PYTHONPATH", "")
        env["PYTHONPATH"] = env_path + (os.pathsep + existing if existing else "")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *args],
            cwd=project,
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return GateResult(gate["id"], False, out, err,
                          f"gate timed out after {timeout}s — check for infinite loops or hung I/O")
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
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    try:
        proc = subprocess.run(
            [str(ruff_bin), *args],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return GateResult(gate["id"], False, out, err,
                          f"gate timed out after {timeout}s — check for infinite loops or hung I/O")
    passed = proc.returncode == 0
    hint = "" if passed else "ruff flagged lint issues — fix or add to ignore config"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)


def _gate_mypy(gate: dict, project: Path) -> GateResult:
    mypy_bin = _resolve_tool("mypy")
    if mypy_bin is None:
        return GateResult(
            gate["id"], False, "", "",
            "mypy not found next to python interpreter or on PATH — install with `pip install mypy`",
        )
    args = gate.get("args") or ["."]
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    try:
        proc = subprocess.run(
            [str(mypy_bin), *args],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return GateResult(gate["id"], False, out, err,
                          f"gate timed out after {timeout}s — check for infinite loops or hung I/O")
    passed = proc.returncode == 0
    hint = "" if passed else "mypy reported type errors — read stdout"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)


def _gate_import_clean(gate: dict, project: Path) -> GateResult:
    module = gate.get("module")
    if not module:
        return GateResult(gate["id"], False, "", "", "missing `module` field; add `module: <name>`")
    gate_env = gate.get("env") or {}
    env = _merge_env(project, gate_env)
    if "PYTHONPATH" not in gate_env:
        env_path = str(project / "src")
        existing = os.environ.get("PYTHONPATH", "")
        env["PYTHONPATH"] = env_path + (os.pathsep + existing if existing else "")
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            cwd=project,
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return GateResult(gate["id"], False, out, err,
                          f"gate timed out after {timeout}s — check for infinite loops or hung I/O")
    passed = proc.returncode == 0
    hint = "" if passed else f"import failed: {proc.stderr.strip()[:200]}"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)


def _gate_cli_command_runs(gate: dict, project: Path) -> GateResult:
    cmd = gate.get("command") or []
    expect_exit = gate.get("expect_exit", 0)
    expect_match = gate.get("expect_stdout_match")
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    if not cmd:
        return GateResult(gate["id"], False, "", "", "no command specified; add `command:` to gate")
    env = _merge_env(project, gate.get("env") or {})
    cmd = _resolve_python(cmd, env)
    try:
        proc = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True, check=False, timeout=timeout)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return GateResult(gate["id"], False, out, err,
                          f"gate timed out after {timeout}s — check for infinite loops or hung I/O")
    hint_parts: list[str] = []
    passed = code == expect_exit
    if not passed:
        hint_parts.append(f"exit={code}, expected {expect_exit}")
    if expect_match and not re.search(expect_match, out):
        passed = False
        hint_parts.append(f"stdout did not match /{expect_match}/")
    return GateResult(gate["id"], passed, out, err, "; ".join(hint_parts))


def _find_prior_coverage(project: Path, gate_id: str) -> float | None:
    """Find the most recent prior iteration's coverage gate result.
    Returns the percent as float, or None if no prior record."""
    iters_dir = project / ".skillgoid" / "iterations"
    if not iters_dir.is_dir():
        return None
    iter_files = sorted(iters_dir.glob("*.json"), reverse=True)
    for path in iter_files:
        try:
            rec = json.loads(path.read_text())
        except Exception:
            continue
        for r in (rec.get("gate_report", {}).get("results") or []):
            if r.get("gate_id") == gate_id and r.get("passed"):
                match = _COVERAGE_RE.search(r.get("stdout") or "")
                if match:
                    return float(match.group(1))
    return None


def _gate_coverage(gate: dict, project: Path) -> GateResult:
    target = gate.get("target") or "."
    min_percent = gate.get("min_percent", 80)
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)

    gate_env = gate.get("env") or {}
    env = _merge_env(project, gate_env)
    if "PYTHONPATH" not in gate_env:
        env_path = str(project / "src")
        existing = os.environ.get("PYTHONPATH", "")
        env["PYTHONPATH"] = env_path + (os.pathsep + existing if existing else "")

    # Write coverage JSON to system tempdir (not project dir) so a killed gate
    # never leaves a stray file in the project tree that `git add -A` could
    # pick up. The finally-block cleanup still applies.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=tempfile.gettempdir()
    ) as tf:
        cov_path = Path(tf.name)

    try:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest",
                 f"--cov={target}",
                 f"--cov-report=json:{cov_path}",
                 "--cov-report=",  # suppress terminal report
                 "-q"],
                cwd=project,
                capture_output=True,
                text=True,
                env=env,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return GateResult(gate["id"], False, out, err,
                              f"gate timed out after {timeout}s — check for infinite loops or hung I/O")

        if not cov_path.exists() or cov_path.stat().st_size == 0:
            return GateResult(
                gate["id"], False, proc.stdout, proc.stderr,
                "coverage report not generated — is pytest-cov installed in the target project?",
            )

        try:
            cov_data = json.loads(cov_path.read_text())
            percent = float(cov_data["totals"]["percent_covered"])
        except Exception as exc:
            return GateResult(gate["id"], False, proc.stdout, proc.stderr,
                              f"failed to parse coverage.json: {exc}")

        stdout_summary = f"coverage: {percent:.1f}%"
        if percent < min_percent:
            return GateResult(
                gate["id"], False, stdout_summary, proc.stderr,
                f"coverage {percent:.1f}% below floor {min_percent}%",
            )
        if gate.get("compare_to_baseline", False):
            baseline = _find_prior_coverage(project, gate["id"])
            if baseline is not None and percent < baseline - 0.5:
                return GateResult(
                    gate["id"], False, stdout_summary, proc.stderr,
                    f"coverage regressed from {baseline:.1f}% to {percent:.1f}%",
                )
        return GateResult(gate["id"], True, stdout_summary, proc.stderr, "")
    finally:
        try:
            cov_path.unlink()
        except FileNotFoundError:
            pass


GATE_DISPATCH = {
    "run-command": _gate_run_command,
    "pytest": _gate_pytest,
    "ruff": _gate_ruff,
    "mypy": _gate_mypy,
    "import-clean": _gate_import_clean,
    "cli-command-runs": _gate_cli_command_runs,
    "coverage": _gate_coverage,
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
