"""End-to-end Phase 1 pipeline test.

Mocks the subagent dispatch by feeding a hand-crafted `drafts` JSON to
synthesize.py directly. Asserts that the resulting criteria.yaml.proposed
is schema-valid and carries expected provenance comments.
"""
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthesize" / "mini-flask-demo"
SCHEMA_PATH = ROOT / "schemas" / "criteria.schema.json"
SCRIPTS = ROOT / "scripts" / "synthesize"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("timeout", 30)
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def test_full_pipeline_with_mocked_subagent(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()

    # Stage 1: ground
    result = _run([
        sys.executable, str(SCRIPTS / "ground.py"),
        "--skillgoid-dir", str(sg), str(FIXTURE),
    ])
    assert result.returncode == 0, result.stderr
    grounding = json.loads((sg / "synthesis" / "grounding.json").read_text())
    assert grounding["language_detected"] == "python"
    assert len(grounding["observations"]) >= 2

    # Phase 1.5: tool-section and wrapper-follow observations
    observed_types = {o["observed_type"] for o in grounding["observations"]}
    assert "ruff" in observed_types, "pyproject [tool.ruff] should produce ruff observation"
    assert "mypy" in observed_types, "pyproject [tool.mypy] should produce mypy observation"
    refs = {o["ref"] for o in grounding["observations"]}
    assert any("pyproject.toml#tool." in r for r in refs), "expected at least one pyproject tool-section ref"
    assert any(r.endswith("scripts/test") for r in refs), "expected at least one wrapper-script ref"

    # Stage 2: simulate subagent output by hand-picking refs from grounding
    # The subagent's output must cite refs that exist in grounding.json.
    pytest_obs = next(o for o in grounding["observations"] if o["observed_type"] == "pytest")
    ruff_obs = next(o for o in grounding["observations"] if o["observed_type"] == "ruff")
    fake_subagent_output = json.dumps({
        "drafts": [
            {
                "id": "pytest_main",
                "type": "pytest",
                "args": ["tests"],
                "timeout": 60,
                "provenance": {
                    "source": pytest_obs["source"],
                    "ref": pytest_obs["ref"],
                },
                "rationale": "Repo declares pytest with testpaths=tests.",
            },
            {
                "id": "ruff_check",
                "type": "ruff",
                "args": ["check", "."],
                "timeout": 30,
                "provenance": {
                    "source": ruff_obs["source"],
                    "ref": ruff_obs["ref"],
                },
                "rationale": "CI workflow runs ruff check.",
            },
        ]
    })
    result = _run([
        sys.executable, str(SCRIPTS / "synthesize.py"),
        "--skillgoid-dir", str(sg),
    ], input=fake_subagent_output)
    assert result.returncode == 0, result.stderr

    # Stage 4: write
    result = _run([
        sys.executable, str(SCRIPTS / "write_criteria.py"),
        "--skillgoid-dir", str(sg),
    ])
    assert result.returncode == 0, result.stderr

    # Verify output
    proposed = sg / "criteria.yaml.proposed"
    assert proposed.exists()
    text = proposed.read_text()

    # Schema-valid
    schema = json.loads(SCHEMA_PATH.read_text())
    parsed = yaml.safe_load(text)
    jsonschema.validate(parsed, schema)

    # Provenance comments present
    assert "# source: analogue" in text
    assert "# validated: none" in text

    # Both gates rendered
    assert "id: pytest_main" in text
    assert "id: ruff_check" in text

    # Internal fields stripped
    for gate in parsed["gates"]:
        assert "provenance" not in gate
        assert "rationale" not in gate


def test_synthesize_rejects_draft_with_nonexistent_provenance_ref(tmp_path):
    """When the subagent invents a draft citing a ref not in grounding.json,
    synthesize.py exits 1 with 'provenance ref not found' in stderr.

    The empty-repo setup ensures the only valid refs are zero, but the same
    rejection applies regardless of grounding size.
    """
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    empty_repo = tmp_path / "empty-repo"
    empty_repo.mkdir()

    result = _run([
        sys.executable, str(SCRIPTS / "ground.py"),
        "--skillgoid-dir", str(sg), str(empty_repo),
    ])
    assert result.returncode == 0
    grounding = json.loads((sg / "synthesis" / "grounding.json").read_text())
    assert grounding["observations"] == []

    # Now: if subagent invented a gate citing a fake ref, synthesize must reject it
    fake = json.dumps({"drafts": [{
        "id": "x", "type": "pytest", "args": [],
        "provenance": {"source": "analogue", "ref": "nonexistent/ref.py"},
    }]})
    result = _run([
        sys.executable, str(SCRIPTS / "synthesize.py"),
        "--skillgoid-dir", str(sg),
    ], input=fake)
    assert result.returncode == 1
    assert "provenance ref not found" in result.stderr


def test_e2e_canonical_coverage_gate(tmp_path):
    """Running the full pipeline with a subagent draft that cites coverage_threshold
    observations produces a criteria.yaml.proposed where the coverage gate has
    min_percent set and no args.
    """
    import json as _json
    from scripts.synthesize.ground import run_ground
    from scripts.synthesize.synthesize import run_synthesize
    from scripts.synthesize.write_criteria import run_write_criteria

    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "goal.md").write_text("Build a mini flask demo with coverage >= 95.\n")

    # Stage 1: ground from the updated fixture
    fixture = Path(__file__).resolve().parents[0] / "fixtures" / "synthesize" / "mini-flask-demo"
    run_ground(sg, [fixture])
    grounding = _json.loads((sg / "synthesis" / "grounding.json").read_text())

    # Assert both coverage_threshold observations present (100 from pyproject, 95 from CI)
    thresholds = [o for o in grounding["observations"] if o["observed_type"] == "coverage_threshold"]
    values = sorted(int(t["command"].split("=")[1]) for t in thresholds)
    assert values == [95, 100]

    # Stage 2: hand-craft a subagent output that cites the CI threshold (95 per prompt policy)
    subagent_output = _json.dumps({
        "drafts": [
            {
                "id": "coverage_main",
                "type": "coverage",
                "min_percent": 95,
                "provenance": {
                    "source": "analogue",
                    "ref": "mini-flask-demo/.github/workflows/test.yml",
                },
                "rationale": "coverage_threshold=95 from CI step --fail-under",
            }
        ]
    })
    run_synthesize(sg, subagent_output)

    # Stage 4: write
    out = run_write_criteria(sg)
    text = out.read_text()
    # Canonical shape: min_percent present, no args line
    assert "min_percent: 95" in text
    # Source ref is cited in the comment block
    assert "mini-flask-demo/.github/workflows/test.yml" in text
    # No args line anywhere in the output (the coverage gate is the only gate)
    assert "args:" not in text
