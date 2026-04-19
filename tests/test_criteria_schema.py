"""Tests for schemas/criteria.schema.json gate-type shape constraints."""
import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "criteria.schema.json"
_SCHEMA = json.loads(SCHEMA_PATH.read_text())
_VALIDATOR = Draft202012Validator(_SCHEMA)


def _validate(criteria: dict) -> None:
    _VALIDATOR.validate(criteria)


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


def test_coverage_gate_accepts_min_percent_zero():
    _validate(_coverage_gate(min_percent=0))


def test_coverage_gate_accepts_min_percent_hundred():
    _validate(_coverage_gate(min_percent=100))


def test_coverage_gate_negative_min_percent_rejected():
    with pytest.raises(jsonschema.ValidationError):
        _validate(_coverage_gate(min_percent=-1))


def test_integration_coverage_gate_rejects_args():
    criteria = {
        "gates": [],
        "integration_gates": [
            {"id": "cov", "type": "coverage", "min_percent": 80, "args": ["report"]}
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        _validate(criteria)
