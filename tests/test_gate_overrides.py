"""Tests for per-chunk gate_overrides merging logic.

This logic lives in the loop skill prose — the test asserts the EXPECTED shape
of the criteria subset after merging, so future code helpers can reference it
and stay compliant."""


def _apply_gate_overrides(chunk: dict, gates: list[dict]) -> list[dict]:
    """Simulate the loop skill's override-merging behavior.
    For each gate, if the chunk has gate_overrides[gate.id], replace the gate's
    `args` with the override's `args`. All other gate fields unchanged."""
    overrides = chunk.get("gate_overrides") or {}
    result = []
    for gate in gates:
        g = dict(gate)
        ov = overrides.get(g["id"])
        if ov and "args" in ov:
            g["args"] = list(ov["args"])
        result.append(g)
    return result


def test_override_replaces_args():
    chunk = {"id": "py_db", "gate_overrides": {"pytest_chunk": {"args": ["tests/test_py_db.py"]}}}
    gates = [{"id": "pytest_chunk", "type": "pytest", "args": ["tests/"], "env": {"PYTHONPATH": "src"}}]
    result = _apply_gate_overrides(chunk, gates)
    assert result[0]["args"] == ["tests/test_py_db.py"]
    assert result[0]["env"] == {"PYTHONPATH": "src"}  # preserved
    assert result[0]["type"] == "pytest"  # preserved


def test_override_absent_falls_through():
    chunk = {"id": "py_db"}  # no overrides
    gates = [{"id": "pytest_chunk", "type": "pytest", "args": ["tests/"]}]
    result = _apply_gate_overrides(chunk, gates)
    assert result[0]["args"] == ["tests/"]


def test_override_only_affects_matching_gate():
    chunk = {"id": "py_db", "gate_overrides": {"pytest_chunk": {"args": ["tests/test_py_db.py"]}}}
    gates = [
        {"id": "lint", "type": "ruff", "args": ["check", "."]},
        {"id": "pytest_chunk", "type": "pytest", "args": ["tests/"]},
    ]
    result = _apply_gate_overrides(chunk, gates)
    assert result[0]["args"] == ["check", "."]  # lint unchanged
    assert result[1]["args"] == ["tests/test_py_db.py"]  # pytest overridden


def test_multiple_overrides():
    chunk = {
        "id": "py_db",
        "gate_overrides": {
            "pytest_chunk": {"args": ["tests/test_py_db.py"]},
            "lint": {"args": ["check", "src/taskbridge/db.py"]},
        },
    }
    gates = [
        {"id": "lint", "type": "ruff", "args": ["check", "."]},
        {"id": "pytest_chunk", "type": "pytest", "args": ["tests/"]},
    ]
    result = _apply_gate_overrides(chunk, gates)
    assert result[0]["args"] == ["check", "src/taskbridge/db.py"]
    assert result[1]["args"] == ["tests/test_py_db.py"]
