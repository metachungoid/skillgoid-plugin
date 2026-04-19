"""Tests for scripts/synthesize/validate.py — Stage 3 oracle validation."""
from __future__ import annotations

import json
from pathlib import Path

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
