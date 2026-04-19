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
    assert "Phase 1: oracle validation deferred" in text

    # Both gates rendered
    assert "id: pytest_main" in text
    assert "id: ruff_check" in text

    # Internal fields stripped
    for gate in parsed["gates"]:
        assert "provenance" not in gate
        assert "rationale" not in gate


def test_pipeline_stops_when_no_observations(tmp_path):
    """Empty analogue -> grounding has 0 observations -> synthesize must NOT be invoked.

    This test verifies the precondition Stage 2 enforces. The skill prose is
    expected to bail out before dispatch when grounding is empty; here we
    simulate the edge by checking that synthesize.py rejects empty grounding
    correctly when the subagent (hypothetically) returned drafts anyway.
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
