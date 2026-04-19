"""Tests for scripts/synthesize/synthesize.py.

Stage 2 parses + validates the synthesis subagent's stdout JSON. No live
LLM call is made — tests feed fixed JSON strings.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.synthesize._common import save_json, synthesis_path
from scripts.synthesize.synthesize import (
    SUPPORTED_GATE_TYPES,
    DraftValidationError,
    parse_subagent_output,
    run_synthesize,
)

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "synthesize" / "synthesize.py")]


def test_supported_gate_types_matches_schema_enum():
    """Fail loudly if criteria.schema.json adds a gate type the parser doesn't know."""
    schema_path = ROOT / "schemas" / "criteria.schema.json"
    schema = json.loads(schema_path.read_text())
    schema_enum = schema["properties"]["gates"]["items"]["properties"]["type"]["enum"]
    assert SUPPORTED_GATE_TYPES == set(schema_enum), (
        f"SUPPORTED_GATE_TYPES drifted from schema enum. "
        f"Script: {sorted(SUPPORTED_GATE_TYPES)}, Schema: {sorted(schema_enum)}"
    )


def _grounding_payload() -> dict:
    return {
        "language_detected": "python",
        "framework_detected": "flask",
        "observations": [
            {
                "source": "analogue",
                "ref": "mini-flask-demo/pyproject.toml",
                "command": "pytest tests",
                "context": "declared test command",
                "observed_type": "pytest",
            },
            {
                "source": "analogue",
                "ref": "mini-flask-demo/.github/workflows/test.yml",
                "command": "ruff check .",
                "context": "CI workflow step",
                "observed_type": "ruff",
            },
        ],
    }


def _well_formed_subagent_output() -> str:
    return json.dumps({
        "drafts": [
            {
                "id": "pytest_main",
                "type": "pytest",
                "args": ["tests"],
                "timeout": 60,
                "provenance": {
                    "source": "analogue",
                    "ref": "mini-flask-demo/pyproject.toml",
                },
                "rationale": "Repo declares pytest with testpaths=tests.",
            },
            {
                "id": "ruff_lint",
                "type": "ruff",
                "args": ["check", "."],
                "timeout": 30,
                "provenance": {
                    "source": "analogue",
                    "ref": "mini-flask-demo/.github/workflows/test.yml",
                },
                "rationale": "CI workflow runs ruff check.",
            },
        ]
    })


def test_parse_subagent_output_accepts_well_formed_json():
    grounding = _grounding_payload()
    drafts = parse_subagent_output(_well_formed_subagent_output(), grounding)
    assert len(drafts) == 2
    assert drafts[0]["id"] == "pytest_main"
    assert drafts[0]["type"] == "pytest"


def test_parse_subagent_output_rejects_invalid_json():
    grounding = _grounding_payload()
    with pytest.raises(DraftValidationError, match="not valid JSON"):
        parse_subagent_output("not json at all", grounding)


def test_parse_subagent_output_rejects_missing_drafts_key():
    grounding = _grounding_payload()
    with pytest.raises(DraftValidationError, match="must contain 'drafts'"):
        parse_subagent_output('{"other": []}', grounding)


def test_parse_subagent_output_rejects_draft_missing_provenance():
    grounding = _grounding_payload()
    bad = json.dumps({
        "drafts": [{
            "id": "x", "type": "pytest", "args": [],
        }]
    })
    with pytest.raises(DraftValidationError, match="missing 'provenance'"):
        parse_subagent_output(bad, grounding)


def test_parse_subagent_output_rejects_provenance_ref_not_in_grounding():
    grounding = _grounding_payload()
    bad = json.dumps({
        "drafts": [{
            "id": "x", "type": "pytest", "args": [],
            "provenance": {"source": "analogue", "ref": "fake/path.py"},
        }]
    })
    with pytest.raises(DraftValidationError, match="provenance ref not found"):
        parse_subagent_output(bad, grounding)


def test_parse_subagent_output_rejects_unsupported_gate_type():
    grounding = _grounding_payload()
    bad = json.dumps({
        "drafts": [{
            "id": "x", "type": "magic-gate", "args": [],
            "provenance": {"source": "analogue", "ref": "mini-flask-demo/pyproject.toml"},
        }]
    })
    with pytest.raises(DraftValidationError, match="unsupported gate type"):
        parse_subagent_output(bad, grounding)


def test_parse_subagent_output_rejects_duplicate_gate_ids():
    grounding = _grounding_payload()
    bad = json.dumps({
        "drafts": [
            {
                "id": "dup", "type": "pytest", "args": [],
                "provenance": {"source": "analogue", "ref": "mini-flask-demo/pyproject.toml"},
            },
            {
                "id": "dup", "type": "ruff", "args": ["check"],
                "provenance": {"source": "analogue", "ref": "mini-flask-demo/.github/workflows/test.yml"},
            },
        ]
    })
    with pytest.raises(DraftValidationError, match="duplicate gate id"):
        parse_subagent_output(bad, grounding)


def test_run_synthesize_writes_drafts_json(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    save_json(synthesis_path(sg, "grounding.json"), _grounding_payload())

    out_path = run_synthesize(sg, _well_formed_subagent_output())

    assert out_path == synthesis_path(sg, "drafts.json")
    payload = json.loads(out_path.read_text())
    assert len(payload["drafts"]) == 2


def test_cli_reads_subagent_output_from_stdin(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    save_json(synthesis_path(sg, "grounding.json"), _grounding_payload())

    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg)],
        input=_well_formed_subagent_output(),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (sg / "synthesis" / "drafts.json").exists()


def test_cli_validation_failure_exits_one(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    save_json(synthesis_path(sg, "grounding.json"), _grounding_payload())

    bad = json.dumps({"drafts": [
        {"id": "x", "type": "magic", "args": [],
         "provenance": {"source": "analogue", "ref": "fake.py"}},
    ]})
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg)],
        input=bad,
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "DraftValidationError" in result.stderr or "unsupported" in result.stderr


def test_parse_rejects_coverage_with_args():
    grounding = _grounding_payload()
    raw = json.dumps({
        "drafts": [
            {
                "id": "cov",
                "type": "coverage",
                "args": ["report", "--fail-under=100"],
                "min_percent": 100,
                "provenance": {
                    "source": "analogue",
                    "ref": "mini-flask-demo/pyproject.toml",
                },
                "rationale": "x",
            }
        ]
    })
    with pytest.raises(DraftValidationError, match=r"draft 'cov' \(coverage\): must not have args"):
        parse_subagent_output(raw, grounding)


def test_parse_rejects_coverage_without_min_percent():
    grounding = _grounding_payload()
    raw = json.dumps({
        "drafts": [
            {
                "id": "cov",
                "type": "coverage",
                "provenance": {
                    "source": "analogue",
                    "ref": "mini-flask-demo/pyproject.toml",
                },
                "rationale": "x",
            }
        ]
    })
    with pytest.raises(DraftValidationError, match=r"draft 'cov' \(coverage\): must have min_percent"):
        parse_subagent_output(raw, grounding)


def test_parse_rejects_coverage_min_percent_out_of_range():
    grounding = _grounding_payload()
    raw = json.dumps({
        "drafts": [
            {
                "id": "cov",
                "type": "coverage",
                "min_percent": 150,
                "provenance": {
                    "source": "analogue",
                    "ref": "mini-flask-demo/pyproject.toml",
                },
                "rationale": "x",
            }
        ]
    })
    with pytest.raises(DraftValidationError, match=r"draft 'cov' \(coverage\): min_percent must be 0-100"):
        parse_subagent_output(raw, grounding)


def test_parse_accepts_coverage_with_min_percent_only():
    grounding = _grounding_payload()
    raw = json.dumps({
        "drafts": [
            {
                "id": "cov",
                "type": "coverage",
                "min_percent": 80,
                "provenance": {
                    "source": "analogue",
                    "ref": "mini-flask-demo/pyproject.toml",
                },
                "rationale": "x",
            }
        ]
    })
    drafts = parse_subagent_output(raw, grounding)
    assert drafts[0]["type"] == "coverage"
    assert drafts[0]["min_percent"] == 80
    assert "args" not in drafts[0]


def test_parse_accepts_provenance_ref_as_list():
    grounding = _grounding_payload()
    raw = json.dumps({
        "drafts": [
            {
                "id": "cov",
                "type": "coverage",
                "min_percent": 80,
                "provenance": {
                    "source": "analogue",
                    "ref": [
                        "mini-flask-demo/pyproject.toml",
                        "mini-flask-demo/.github/workflows/test.yml",
                    ],
                },
                "rationale": "x",
            }
        ]
    })
    drafts = parse_subagent_output(raw, grounding)
    assert isinstance(drafts[0]["provenance"]["ref"], list)


def test_parse_rejects_list_ref_containing_unknown():
    grounding = _grounding_payload()
    raw = json.dumps({
        "drafts": [
            {
                "id": "cov",
                "type": "coverage",
                "min_percent": 80,
                "provenance": {
                    "source": "analogue",
                    "ref": ["mini-flask-demo/pyproject.toml", "does/not/exist"],
                },
                "rationale": "x",
            }
        ]
    })
    with pytest.raises(DraftValidationError, match="provenance ref not found"):
        parse_subagent_output(raw, grounding)
