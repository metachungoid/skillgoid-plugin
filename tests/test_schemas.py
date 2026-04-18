import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def _validator(schema_name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / schema_name).read_text())
    return Draft202012Validator(schema)


def _load_yaml(fixture: str) -> dict:
    return yaml.safe_load((ROOT / "tests" / "fixtures" / fixture).read_text())


def test_valid_criteria_passes_schema():
    data = _load_yaml("valid_criteria.yaml")
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert errors == []


def test_valid_chunks_passes_schema():
    data = _load_yaml("valid_chunks.yaml")
    errors = list(_validator("chunks.schema.json").iter_errors(data))
    assert errors == []


def test_criteria_missing_gates_fails():
    errors = list(_validator("criteria.schema.json").iter_errors({}))
    assert any("gates" in str(e.message) for e in errors)


def test_chunk_missing_id_fails():
    bad = {"chunks": [{"description": "no id here"}]}
    errors = list(_validator("chunks.schema.json").iter_errors(bad))
    assert any("id" in str(e.message) for e in errors)


def test_unknown_gate_type_fails():
    bad = {"gates": [{"id": "x", "type": "unknown-gate"}]}
    errors = list(_validator("criteria.schema.json").iter_errors(bad))
    assert any(e.validator == "enum" for e in errors)


def test_chunk_missing_gate_ids_fails():
    bad = {"chunks": [{"id": "x", "description": "no gates"}]}
    errors = list(_validator("chunks.schema.json").iter_errors(bad))
    assert any(e.validator == "required" and "gate_ids" in str(e.message) for e in errors)


def test_chunk_empty_gate_ids_fails():
    bad = {"chunks": [{"id": "x", "description": "y", "gate_ids": []}]}
    errors = list(_validator("chunks.schema.json").iter_errors(bad))
    assert any(e.validator == "minItems" for e in errors)
