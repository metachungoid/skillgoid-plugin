"""Tests for scripts/synthesize/write_criteria.py — Stage 4."""
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import yaml

from scripts.synthesize._common import save_json, synthesis_path
from scripts.synthesize.write_criteria import (
    render_criteria_yaml,
    run_write_criteria,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "criteria.schema.json"
CLI = [sys.executable, str(ROOT / "scripts" / "synthesize" / "write_criteria.py")]


def _drafts_payload() -> dict:
    return {
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
                "rationale": "Declared test command.",
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
                "rationale": "CI step.",
            },
        ]
    }


def test_render_criteria_yaml_includes_provenance_comments():
    out = render_criteria_yaml(_drafts_payload(), language="python")
    assert "# source: analogue, ref: mini-flask-demo/pyproject.toml" in out
    assert "# validated: none" in out
    assert "# warn: validation artifact missing" in out
    assert "id: pytest_main" in out


def test_render_criteria_yaml_starts_with_header():
    out = render_criteria_yaml(_drafts_payload(), language="python")
    assert out.startswith("# Skillgoid criteria — synthesized")


def test_render_criteria_yaml_strips_internal_fields():
    out = render_criteria_yaml(_drafts_payload(), language="python")
    # `provenance` and `rationale` are NOT part of the criteria schema;
    # they appear only as comments. The serialized YAML keys must omit them.
    parsed = yaml.safe_load(out)
    assert "language" in parsed
    assert "gates" in parsed
    for gate in parsed["gates"]:
        assert "provenance" not in gate
        assert "rationale" not in gate


def test_render_criteria_yaml_validates_against_schema():
    schema = json.loads(SCHEMA_PATH.read_text())
    out = render_criteria_yaml(_drafts_payload(), language="python")
    parsed = yaml.safe_load(out)
    # Will raise if invalid — explicit assertion afterward
    jsonschema.validate(parsed, schema)


def test_render_criteria_yaml_with_empty_drafts():
    out = render_criteria_yaml({"drafts": []}, language="unknown")
    parsed = yaml.safe_load(out)
    assert parsed["gates"] == []


def test_render_criteria_yaml_round_trips_through_safe_load_back():
    """Regression: ensure the 2-space indent splice survives round-trip.

    The per-gate splice loop assumes `safe_dump(indent=2)` so that prefixing
    each line with 2 spaces yields valid YAML under `gates:`. If that
    assumption ever drifts, `yaml.safe_load` would produce malformed gates
    (e.g. merged keys or broken nesting). This test parses the rendered
    output and confirms every gate dict round-trips key-for-key against the
    input drafts (minus the stripped internal fields).
    """
    payload = _drafts_payload()
    out = render_criteria_yaml(payload, language="python")
    parsed = yaml.safe_load(out)
    assert len(parsed["gates"]) == len(payload["drafts"])
    for rendered_gate, original_draft in zip(parsed["gates"], payload["drafts"]):
        expected = {
            k: v for k, v in original_draft.items()
            if k not in ("provenance", "rationale")
        }
        assert rendered_gate == expected


def test_run_write_criteria_writes_proposed_file(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "synthesis").mkdir()
    save_json(synthesis_path(sg, "drafts.json"), _drafts_payload())
    save_json(synthesis_path(sg, "grounding.json"), {
        "language_detected": "python", "framework_detected": None,
        "observations": [],
    })

    out_path = run_write_criteria(sg)

    assert out_path == sg / "criteria.yaml.proposed"
    assert out_path.exists()
    parsed = yaml.safe_load(out_path.read_text())
    assert parsed["language"] == "python"


def test_run_write_criteria_does_not_overwrite_existing_criteria(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("# user's existing criteria\ngates: []\n")
    (sg / "synthesis").mkdir()
    save_json(synthesis_path(sg, "drafts.json"), _drafts_payload())
    save_json(synthesis_path(sg, "grounding.json"), {
        "language_detected": "python", "framework_detected": None,
        "observations": [],
    })

    out_path = run_write_criteria(sg)

    # Always writes to .proposed, never overwrites existing criteria.yaml
    assert out_path.name == "criteria.yaml.proposed"
    assert (sg / "criteria.yaml").read_text() == "# user's existing criteria\ngates: []\n"


def test_cli_writes_proposed_and_prints_path(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "synthesis").mkdir()
    save_json(synthesis_path(sg, "drafts.json"), _drafts_payload())
    save_json(synthesis_path(sg, "grounding.json"), {
        "language_detected": "python", "framework_detected": None,
        "observations": [],
    })

    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (sg / "criteria.yaml.proposed").exists()
    assert "criteria.yaml.proposed" in result.stdout


def test_gate_comment_block_renders_single_ref_as_inline():
    from scripts.synthesize.write_criteria import _gate_comment_block
    draft = {
        "id": "cov",
        "type": "coverage",
        "min_percent": 80,
        "provenance": {"source": "analogue", "ref": "mini/pyproject.toml"},
    }
    block = _gate_comment_block(draft, None)
    assert "source: analogue, ref: mini/pyproject.toml" in block
    assert "refs:" not in block


def test_gate_comment_block_renders_list_ref_as_block():
    from scripts.synthesize.write_criteria import _gate_comment_block
    draft = {
        "id": "cov",
        "type": "coverage",
        "min_percent": 80,
        "provenance": {
            "source": "analogue",
            "ref": ["mini/pyproject.toml", "mini/.github/workflows/ci.yml"],
        },
    }
    block = _gate_comment_block(draft, None)
    assert "source: analogue" in block
    assert "refs:" in block
    assert "- mini/pyproject.toml" in block
    assert "- mini/.github/workflows/ci.yml" in block


def test_write_renders_validated_oracle(tmp_path):
    """When validated.json marks a gate as 'oracle', the yaml carries it."""
    import json as _json
    from scripts.synthesize.write_criteria import run_write_criteria

    sg = tmp_path / ".skillgoid"
    synthesis = sg / "synthesis"
    synthesis.mkdir(parents=True)

    (synthesis / "grounding.json").write_text(_json.dumps({
        "language_detected": "python", "framework_detected": None,
        "analogues": {"demo": str(tmp_path)}, "observations": [],
    }))
    (synthesis / "drafts.json").write_text(_json.dumps({"drafts": [
        {"id": "ruff_check", "type": "ruff", "args": ["check", "."],
         "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}}
    ]}))
    (synthesis / "validated.json").write_text(_json.dumps({
        "schema_version": 1,
        "gates": [{"id": "ruff_check", "validated": "oracle",
                   "warn": None, "oracle_run": None}],
    }))

    out = run_write_criteria(sg)
    text = out.read_text()
    assert "# validated: oracle" in text
    assert "# warn:" not in text


def test_write_renders_warn_line_when_present(tmp_path):
    import json as _json
    from scripts.synthesize.write_criteria import run_write_criteria

    sg = tmp_path / ".skillgoid"
    synthesis = sg / "synthesis"
    synthesis.mkdir(parents=True)

    (synthesis / "grounding.json").write_text(_json.dumps({
        "language_detected": "python", "framework_detected": None,
        "analogues": {"demo": str(tmp_path)}, "observations": [],
    }))
    (synthesis / "drafts.json").write_text(_json.dumps({"drafts": [
        {"id": "cov", "type": "coverage", "min_percent": 95,
         "provenance": {"source": "analogue", "ref": "demo/x"}}
    ]}))
    (synthesis / "validated.json").write_text(_json.dumps({
        "schema_version": 1,
        "gates": [{"id": "cov", "validated": "none",
                   "warn": "coverage tooling not exerciseable on analogue",
                   "oracle_run": None}],
    }))

    out = run_write_criteria(sg)
    text = out.read_text()
    assert "# validated: none" in text
    assert "# warn: coverage tooling not exerciseable" in text


def test_write_without_validated_json_defaults_all_to_none(tmp_path):
    import json as _json
    from scripts.synthesize.write_criteria import run_write_criteria

    sg = tmp_path / ".skillgoid"
    synthesis = sg / "synthesis"
    synthesis.mkdir(parents=True)

    (synthesis / "grounding.json").write_text(_json.dumps({
        "language_detected": "python", "framework_detected": None,
        "analogues": {}, "observations": [],
    }))
    (synthesis / "drafts.json").write_text(_json.dumps({"drafts": [
        {"id": "g", "type": "pytest", "args": ["tests"],
         "provenance": {"source": "analogue", "ref": "x/y"}}
    ]}))
    # No validated.json

    out = run_write_criteria(sg)
    text = out.read_text()
    assert "# validated: none" in text
    assert "# warn: validation artifact missing" in text
