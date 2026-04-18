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


# ----- v0.2 additions -----

def test_criteria_with_integration_gates_passes():
    data = {
        "gates": [{"id": "p", "type": "pytest"}],
        "integration_gates": [
            {"id": "smoke", "type": "cli-command-runs", "command": ["myapp", "--help"]},
        ],
        "integration_retries": 2,
    }
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert errors == []


def test_criteria_integration_gates_enforces_enum():
    data = {
        "gates": [{"id": "p", "type": "pytest"}],
        "integration_gates": [{"id": "x", "type": "nonsense"}],
    }
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any(e.validator == "enum" for e in errors)


def test_criteria_loop_skip_git_is_boolean():
    data = {"gates": [{"id": "p", "type": "pytest"}], "loop": {"skip_git": "yes"}}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any("boolean" in str(e.message) or e.validator == "type" for e in errors)


def test_criteria_integration_retries_must_be_non_negative():
    data = {"gates": [{"id": "p", "type": "pytest"}], "integration_retries": -1}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any(e.validator == "minimum" for e in errors)


def test_iterations_schema_validates_complete_record():
    record = {
        "iteration": 3,
        "chunk_id": "core-api",
        "gate_report": {
            "passed": False,
            "results": [
                {"gate_id": "pytest", "passed": False, "stdout": "", "stderr": "E", "hint": "fix"},
            ],
        },
        "failure_signature": "0123456789abcdef",
        "exit_reason": "in_progress",
    }
    errors = list(_validator("iterations.schema.json").iter_errors(record))
    assert errors == []


def test_iterations_schema_rejects_bad_signature_format():
    record = {
        "iteration": 1,
        "chunk_id": "x",
        "gate_report": {"passed": True, "results": []},
        "failure_signature": "NOT-HEX",
    }
    errors = list(_validator("iterations.schema.json").iter_errors(record))
    assert any(e.validator == "pattern" for e in errors)


def test_iterations_schema_rejects_unknown_exit_reason():
    record = {
        "iteration": 1,
        "chunk_id": "x",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "exploded",
    }
    errors = list(_validator("iterations.schema.json").iter_errors(record))
    assert any(e.validator == "enum" for e in errors)


def test_criteria_gate_timeout_is_integer():
    data = {"gates": [{"id": "p", "type": "pytest", "timeout": 60}]}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert errors == []


def test_criteria_gate_timeout_must_be_positive():
    data = {"gates": [{"id": "p", "type": "pytest", "timeout": 0}]}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any(e.validator == "minimum" for e in errors)
