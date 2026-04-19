"""Tests for schemas/criteria.schema.json gate-type shape constraints."""
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "criteria.schema.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _validate(criteria: dict) -> None:
    jsonschema.validate(instance=criteria, schema=_load_schema())


def _coverage_gate(**extra) -> dict:
    return {"gates": [{"id": "cov", "type": "coverage", **extra}]}


def test_coverage_gate_rejects_args():
    with pytest.raises(jsonschema.ValidationError):
        _validate(_coverage_gate(min_percent=80, args=["report"]))


def test_coverage_gate_requires_min_percent():
    with pytest.raises(jsonschema.ValidationError):
        _validate(_coverage_gate())


def test_coverage_gate_accepts_min_percent_only():
    _validate(_coverage_gate(min_percent=90))


def test_coverage_gate_min_percent_out_of_range_rejected():
    with pytest.raises(jsonschema.ValidationError):
        _validate(_coverage_gate(min_percent=150))


def test_non_coverage_gate_still_accepts_args():
    _validate({"gates": [{"id": "lint", "type": "ruff", "args": ["check", "."]}]})
