"""Tests for scripts/synthesize/validate.py — Stage 3 oracle validation."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from scripts.synthesize.validate import run_validate


def _make_sg(tmp_path: Path, drafts: list[dict], analogues: dict[str, str]) -> Path:
    sg = tmp_path / ".skillgoid"
    synthesis = sg / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / "drafts.json").write_text(json.dumps({"drafts": drafts}))
    (synthesis / "grounding.json").write_text(json.dumps({
        "language_detected": "python",
        "framework_detected": None,
        "analogues": analogues,
        "observations": [],
    }))
    return sg


def test_skip_validation_emits_none_for_every_gate(tmp_path):
    drafts = [
        {"id": "pytest_main", "type": "pytest", "args": ["tests"], "provenance": {
            "source": "analogue", "ref": "demo/pyproject.toml"}},
        {"id": "lint", "type": "ruff", "args": ["check", "."], "provenance": {
            "source": "analogue", "ref": "demo/pyproject.toml"}},
    ]
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(tmp_path)})

    out = run_validate(sg, skip=True)

    payload = json.loads(out.read_text())
    assert out == sg / "synthesis" / "validated.json"
    assert len(payload["gates"]) == 2
    for entry in payload["gates"]:
        assert entry["validated"] == "none"
        assert entry["warn"] == "validation skipped by --skip-validation"
        assert entry["oracle_run"] is None


def _gate_result(passed: bool, stdout: str = "", stderr: str = "", hint: str = "") -> dict:
    return {"gate_id": "irrelevant", "passed": passed, "stdout": stdout,
            "stderr": stderr, "hint": hint}


def _adapter_stub(seq):
    """Return a stub for measure_python.run_gates that yields results in order.

    seq is a list of (passed, stdout_hint) tuples — one per call.
    """
    calls = iter(seq)

    def _run_gates(criteria, project):
        passed, stdout = next(calls)
        return {"passed": passed,
                "results": [_gate_result(passed=passed, stdout=stdout)]}
    return _run_gates


def test_classify_pass_fail_labels_oracle(tmp_path):
    drafts = [{"id": "pytest_main", "type": "pytest",
               "args": ["tests"], "provenance": {
                   "source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    with mock.patch("scripts.synthesize.validate.run_gates",
                    _adapter_stub([(True, ""), (False, "")])):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "oracle"
    assert payload["gates"][0]["warn"] is None


def test_classify_pass_pass_labels_smoke_only(tmp_path):
    drafts = [{"id": "pytest_main", "type": "pytest", "args": ["tests"],
               "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    with mock.patch("scripts.synthesize.validate.run_gates",
                    _adapter_stub([(True, ""), (True, "")])):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "smoke-only"
    assert "scaffold also passes" in payload["gates"][0]["warn"]


def test_classify_fail_on_should_pass_labels_none(tmp_path):
    drafts = [{"id": "pytest_main", "type": "pytest", "args": ["tests"],
               "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    def _run_gates(criteria, project):
        return {"passed": False, "results": [_gate_result(
            passed=False, stderr="ModuleNotFoundError: flask")]}

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "none"
    assert "should-pass failed" in payload["gates"][0]["warn"]
    assert "ModuleNotFoundError" in payload["gates"][0]["warn"]


def test_coverage_oracle_pass_when_analogue_produced_number(tmp_path):
    drafts = [{"id": "cov", "type": "coverage", "min_percent": 100,
               "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    def _run_gates(criteria, project):
        if project == analogue:
            return {"passed": False,  # failed because 93.8 < 100
                    "results": [_gate_result(passed=False, stdout="coverage: 93.8%")]}
        return {"passed": False,
                "results": [_gate_result(passed=False,
                    hint="coverage report not generated — is pytest-cov installed?")]}

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "oracle"


def test_coverage_oracle_none_when_pytest_cov_unavailable(tmp_path):
    drafts = [{"id": "cov", "type": "coverage", "min_percent": 80,
               "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    def _run_gates(criteria, project):
        return {"passed": False,
                "results": [_gate_result(passed=False, stdout="",
                    hint="coverage report not generated — is pytest-cov installed?")]}

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "none"
    assert "coverage tooling not exerciseable" in payload["gates"][0]["warn"]


def test_stage_timeout_short_circuits_remaining_gates(tmp_path):
    drafts = [
        {"id": "g1", "type": "pytest", "args": ["tests"],
         "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}},
        {"id": "g2", "type": "pytest", "args": ["tests"],
         "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}},
        {"id": "g3", "type": "pytest", "args": ["tests"],
         "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}},
    ]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    call_count = {"n": 0}

    def _run_gates(criteria, project):
        call_count["n"] += 1
        return {"passed": True,
                "results": [_gate_result(passed=True)]}

    times = iter([0.0, 1.0, 700.0, 700.0, 700.0, 700.0])

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates), \
         mock.patch("scripts.synthesize.validate.monotonic",
                    side_effect=lambda: next(times)):
        out = run_validate(sg, skip=False, stage_timeout_sec=600)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] != "none"
    assert payload["gates"][1]["validated"] == "none"
    assert "stage-timeout exceeded" in payload["gates"][1]["warn"]
    assert payload["gates"][2]["validated"] == "none"
    assert "stage-timeout exceeded" in payload["gates"][2]["warn"]


def test_missing_grounding_json_errors_clearly(tmp_path):
    sg = tmp_path / ".skillgoid"
    synthesis = sg / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / "drafts.json").write_text(json.dumps({"drafts": [
        {"id": "g", "type": "pytest", "args": ["tests"],
         "provenance": {"source": "analogue", "ref": "demo/x"}}
    ]}))
    # NOTE: no grounding.json

    with pytest.raises(FileNotFoundError, match="grounding.json"):
        run_validate(sg, skip=False)


def test_unknown_slug_warns_clearly(tmp_path):
    drafts = [{"id": "g", "type": "pytest", "args": ["tests"],
               "provenance": {"source": "analogue", "ref": "other/pyproject.toml"}}]
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(tmp_path)})

    out = run_validate(sg, skip=False)
    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "none"
    assert "analogue slug 'other' not in grounding.json" in payload["gates"][0]["warn"]


def test_multi_ref_first_slug_is_picked(tmp_path):
    drafts = [{"id": "cov", "type": "coverage", "min_percent": 90,
               "provenance": {"source": "analogue", "ref": [
                   "primary/pyproject.toml", "secondary/ci.yml"]}}]
    primary = tmp_path / "primary"
    primary.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={
        "primary": str(primary), "secondary": str(tmp_path / "secondary")})

    captured = {"project": None}

    def _run_gates(criteria, project):
        if captured["project"] is None:
            captured["project"] = project
        return {"passed": True, "results": [_gate_result(
            passed=True, stdout="coverage: 95.0%")]}

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates):
        run_validate(sg, skip=False)

    assert captured["project"] == primary
