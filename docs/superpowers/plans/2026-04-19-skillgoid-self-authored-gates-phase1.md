# Self-Authored Gates Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `/skillgoid:synthesize-gates <repo-url-or-path>` end-to-end with one grounding source (user-pointed analogue) and no oracle validation; gates labeled `validated: none`. Foundation for Phase 2 (context7 + templates + oracle validation + clarify change).

**Architecture:** Four-stage pipeline as scripts in `scripts/synthesize/`, orchestrated by `skills/synthesize-gates/SKILL.md`. Stage 1 (ground) reads analogue repo's tests + manifests and emits typed observations. Stage 2 (synthesize) is a subagent dispatch from the skill prose; the script `synthesize.py` parses + validates the subagent's stdout JSON. Stage 4 (write) renders `criteria.yaml` conforming to `schemas/criteria.schema.json`, with provenance comments per gate. Stage 3 (validate) is intentionally absent in Phase 1 — all gates ship with `validated: none`.

**Tech Stack:** Python 3.11+, pyyaml, jsonschema, pytest, ruff. Reuses existing Skillgoid plugin conventions: script-driven skills (logic in scripts/, prose in SKILL.md), `.skillgoid/` state directory, `sys.path.insert(0, _ROOT)` cross-script import bootstrap, ruff line length 100, no `print` outside CLI entry points.

**Spec:** `docs/superpowers/specs/2026-04-19-skillgoid-self-authored-gates-design.md`

**Critical schema constraint discovered during planning:** `schemas/criteria.schema.json` requires every gate to have a `type` field from the enum `[pytest, ruff, mypy, import-clean, cli-command-runs, run-command, coverage]` — NOT a free-form `command` string as the spec's example showed. Synthesized gates must map observed commands into one of these seven gate types. Any gate emitted with a `type` not in this enum gets rejected at parse time. The plan reflects this.

**Phase 1 deliverable journey:**

```
$ /skillgoid:clarify
(unchanged from current behavior — produces goal.md AND criteria.yaml)

$ /skillgoid:synthesize-gates https://github.com/pallets/flask
(clones flask, reads its tests, dispatches synthesis subagent, writes criteria.yaml.proposed
 with provenance comments and validated: none labels)

$ diff .skillgoid/criteria.yaml .skillgoid/criteria.yaml.proposed
(user reviews, merges manually)

$ /skillgoid:build
(unchanged)
```

Phase 1 does NOT modify `clarify` (that's Phase 2). The new skill writes to `.skillgoid/criteria.yaml.proposed` so existing hand-authored `criteria.yaml` is never overwritten.

---

## File Structure

**New files (Phase 1):**

```
skills/synthesize-gates/
├── SKILL.md                              # skill prose: orchestrates stages, dispatches synthesis subagent
└── prompts/
    └── synthesize.md                     # subagent prompt template

scripts/synthesize/
├── __init__.py                           # empty package marker
├── _common.py                            # JSON IO helpers shared by all stage scripts
├── ground_analogue.py                    # Stage 1a: reads observations from a checked-out repo
├── ground.py                             # Stage 1 orchestrator (Phase 1: only calls ground_analogue)
├── synthesize.py                         # Stage 2: parses + validates subagent stdout JSON
└── write_criteria.py                     # Stage 4: renders criteria.yaml.proposed with provenance

tests/
├── test_synthesize_common.py
├── test_ground_analogue.py
├── test_ground.py
├── test_synthesize.py
├── test_write_criteria.py
├── test_synthesize_e2e.py                # integration: full pipeline w/ subagent mocked
└── fixtures/
    └── synthesize/
        └── mini-flask-demo/              # vendored tiny project for grounding + integration tests
            ├── pyproject.toml
            ├── src/
            │   └── miniflask/
            │       ├── __init__.py
            │       └── app.py
            └── tests/
                └── test_app.py
```

**Modified files:** none (Phase 1 is purely additive). Plugin manifest `.claude-plugin/plugin.json` does not list skills explicitly — they're auto-discovered by directory presence.

---

## Tasks

### Task 1: Synthesis package skeleton + JSON IO helpers

Create the package directory and the shared JSON IO module. Every stage script reads/writes under `.skillgoid/synthesis/`; centralize the path conventions and IO so individual stages stay focused.

**Files:**
- Create: `scripts/synthesize/__init__.py`
- Create: `scripts/synthesize/_common.py`
- Test: `tests/test_synthesize_common.py`

- [ ] **Step 1: Write failing tests for `_common.py`**

Create `tests/test_synthesize_common.py`:

```python
"""Tests for scripts/synthesize/_common.py — JSON IO helpers."""
import json
from pathlib import Path

import pytest

from scripts.synthesize._common import (
    SYNTHESIS_SUBDIR,
    ensure_synthesis_dir,
    load_json,
    save_json,
    synthesis_path,
)


def test_synthesis_subdir_constant():
    assert SYNTHESIS_SUBDIR == "synthesis"


def test_synthesis_path_joins_under_skillgoid(tmp_path):
    sg = tmp_path / ".skillgoid"
    out = synthesis_path(sg, "grounding.json")
    assert out == sg / "synthesis" / "grounding.json"


def test_ensure_synthesis_dir_creates_when_missing(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    out = ensure_synthesis_dir(sg)
    assert out.exists() and out.is_dir()
    assert out == sg / "synthesis"


def test_ensure_synthesis_dir_idempotent(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    ensure_synthesis_dir(sg)
    # Second call must not raise
    ensure_synthesis_dir(sg)


def test_save_json_then_load_json_round_trip(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    ensure_synthesis_dir(sg)
    target = synthesis_path(sg, "drafts.json")
    payload = {"drafts": [{"id": "x", "type": "pytest"}]}
    save_json(target, payload)
    assert load_json(target) == payload


def test_load_json_missing_file_raises_filenotfound(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    target = synthesis_path(sg, "missing.json")
    with pytest.raises(FileNotFoundError):
        load_json(target)


def test_save_json_pretty_prints_with_trailing_newline(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    ensure_synthesis_dir(sg)
    target = synthesis_path(sg, "x.json")
    save_json(target, {"a": 1})
    text = target.read_text()
    # Pretty-printed (indent=2) and ends with newline
    assert text == '{\n  "a": 1\n}\n'
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
pytest tests/test_synthesize_common.py -v
```

Expected: ImportError / ModuleNotFoundError on `scripts.synthesize._common`.

- [ ] **Step 3: Create empty package marker**

Create `scripts/synthesize/__init__.py`:

```python
"""Self-authored gates synthesis stages."""
```

- [ ] **Step 4: Implement `_common.py`**

Create `scripts/synthesize/_common.py`:

```python
"""Shared helpers for synthesize-gates stage scripts.

All stages read/write under `<.skillgoid>/synthesis/`. Centralize the path
conventions and JSON IO here so each stage script stays focused on its
own logic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SYNTHESIS_SUBDIR = "synthesis"


def synthesis_path(sg: Path, filename: str) -> Path:
    """Return the canonical path for a synthesis artifact under sg/synthesis/."""
    return sg / SYNTHESIS_SUBDIR / filename


def ensure_synthesis_dir(sg: Path) -> Path:
    """Create sg/synthesis/ if missing. Returns the directory path."""
    target = sg / SYNTHESIS_SUBDIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def load_json(path: Path) -> Any:
    """Load JSON from path. Raises FileNotFoundError if missing."""
    return json.loads(path.read_text())


def save_json(path: Path, payload: Any) -> None:
    """Pretty-print payload to path (indent=2, trailing newline)."""
    path.write_text(json.dumps(payload, indent=2) + "\n")
```

- [ ] **Step 5: Run test, verify PASS**

```bash
pytest tests/test_synthesize_common.py -v
```

Expected: 7 PASSED.

- [ ] **Step 6: Lint**

```bash
ruff check scripts/synthesize/ tests/test_synthesize_common.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add scripts/synthesize/__init__.py scripts/synthesize/_common.py tests/test_synthesize_common.py
git commit -m "$(cat <<'EOF'
synthesize: package skeleton + JSON IO helpers

Phase 1 of self-authored gates. Establishes scripts/synthesize/ package
and the _common module shared by all stage scripts.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Vendored fixture analogue repo

Create the small Flask-shaped project that all subsequent grounding + integration tests will use as a stand-in for a real user-pointed analogue. Vendoring keeps tests offline and deterministic.

**Files:**
- Create: `tests/fixtures/synthesize/mini-flask-demo/pyproject.toml`
- Create: `tests/fixtures/synthesize/mini-flask-demo/src/miniflask/__init__.py`
- Create: `tests/fixtures/synthesize/mini-flask-demo/src/miniflask/app.py`
- Create: `tests/fixtures/synthesize/mini-flask-demo/tests/test_app.py`
- Create: `tests/fixtures/synthesize/mini-flask-demo/.github/workflows/test.yml`

- [ ] **Step 1: Create fixture pyproject.toml**

```bash
mkdir -p tests/fixtures/synthesize/mini-flask-demo/src/miniflask
mkdir -p tests/fixtures/synthesize/mini-flask-demo/tests
mkdir -p tests/fixtures/synthesize/mini-flask-demo/.github/workflows
```

Create `tests/fixtures/synthesize/mini-flask-demo/pyproject.toml`:

```toml
[project]
name = "miniflask"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["flask"]

[project.optional-dependencies]
dev = ["pytest", "ruff"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: Create fixture source files**

Create `tests/fixtures/synthesize/mini-flask-demo/src/miniflask/__init__.py`:

```python
"""Minimal Flask demo used as a synthesis-test analogue fixture."""
from miniflask.app import create_app

__all__ = ["create_app"]
```

Create `tests/fixtures/synthesize/mini-flask-demo/src/miniflask/app.py`:

```python
"""Tiny Flask factory + one redirect route for synthesis tests."""
from flask import Flask, redirect


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/r/<slug>")
    def redirect_slug(slug: str):
        return redirect(f"https://example.test/{slug}", code=302)

    return app
```

- [ ] **Step 3: Create fixture test file**

Create `tests/fixtures/synthesize/mini-flask-demo/tests/test_app.py`:

```python
"""Pytest tests for miniflask — used as observation source by ground_analogue."""
import pytest

from miniflask import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_create_app_returns_flask_instance():
    app = create_app()
    assert app is not None


def test_redirect_returns_302(client):
    response = client.get("/r/abc")
    assert response.status_code == 302
    assert response.location == "https://example.test/abc"
```

- [ ] **Step 4: Create fixture CI config**

Create `tests/fixtures/synthesize/mini-flask-demo/.github/workflows/test.yml`:

```yaml
name: test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -v
```

- [ ] **Step 5: Verify pyproject.toml excludes fixtures from test collection**

Read `pyproject.toml` and confirm `testpaths = ["tests"]` plus that `tests/fixtures/` is excluded. The repo CLAUDE.md states fixtures are "deliberately excluded from collection" — verify this is still the case:

```bash
grep -A2 'testpaths\|fixtures' pyproject.toml
```

Expected: `testpaths = ["tests"]` and either an explicit exclusion of `tests/fixtures/` or pytest's default behavior (it WILL collect under `tests/fixtures/` unless excluded). If not excluded, add:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
norecursedirs = ["tests/fixtures"]
```

- [ ] **Step 6: Verify pytest does not collect the fixture**

```bash
pytest --collect-only tests/fixtures/synthesize/ 2>&1 | head -5
```

Expected: empty collection (no test items collected from fixtures/).

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/synthesize/mini-flask-demo/ pyproject.toml
git commit -m "$(cat <<'EOF'
synthesize: vendor mini-flask-demo fixture for analogue grounding tests

Tiny Flask app + tests + CI config used as the analogue-repo stand-in
by ground_analogue and integration tests. Excluded from pytest collection.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Analogue grounding script

Read observations from a checked-out analogue repo. Output is a list of `{source, ref, command, context, observed_type}` dicts emitted as a JSON list to stdout (and consumed by `ground.py`).

**Files:**
- Create: `scripts/synthesize/ground_analogue.py`
- Test: `tests/test_ground_analogue.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ground_analogue.py`:

```python
"""Tests for scripts/synthesize/ground_analogue.py.

Reads vendored mini-flask-demo fixture and asserts observation extraction.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.synthesize.ground_analogue import (
    Observation,
    detect_language,
    extract_observations,
    parse_pyproject_test_command,
    parse_workflow_steps,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthesize" / "mini-flask-demo"
CLI = [sys.executable, str(ROOT / "scripts" / "synthesize" / "ground_analogue.py")]


def test_detect_language_python_from_pyproject():
    assert detect_language(FIXTURE) == "python"


def test_detect_language_unknown_when_no_manifest(tmp_path):
    assert detect_language(tmp_path) == "unknown"


def test_parse_pyproject_test_command_returns_pytest_for_miniflask():
    cmd = parse_pyproject_test_command(FIXTURE / "pyproject.toml")
    # pyproject declares testpaths = ["tests"], pytest is the implied runner
    assert cmd == ["pytest", "tests"]


def test_parse_workflow_steps_extracts_run_lines():
    steps = parse_workflow_steps(FIXTURE / ".github" / "workflows" / "test.yml")
    # Workflow has: pip install, ruff check ., pytest -v
    assert "ruff check ." in steps
    assert "pytest -v" in steps


def test_extract_observations_returns_typed_observations():
    obs = extract_observations(FIXTURE)
    # Must include at least: pytest from pyproject, ruff from workflow,
    # pytest variant from workflow
    types_seen = {o.observed_type for o in obs}
    assert "pytest" in types_seen
    assert "ruff" in types_seen


def test_extract_observations_each_carries_source_ref():
    obs = extract_observations(FIXTURE)
    for o in obs:
        assert o.source == "analogue"
        assert o.ref.startswith(str(FIXTURE.name))  # ref is relative-ish to the repo
        assert o.command  # never empty


def test_observation_to_dict_round_trip():
    o = Observation(
        source="analogue",
        ref="mini-flask-demo/pyproject.toml",
        command="pytest tests",
        context="declared test command",
        observed_type="pytest",
    )
    d = o.to_dict()
    assert d == {
        "source": "analogue",
        "ref": "mini-flask-demo/pyproject.toml",
        "command": "pytest tests",
        "context": "declared test command",
        "observed_type": "pytest",
    }


def test_cli_emits_json_list_to_stdout():
    result = subprocess.run(
        CLI + [str(FIXTURE)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) >= 2
    for entry in payload:
        assert entry["source"] == "analogue"


def test_cli_exits_one_on_missing_repo(tmp_path):
    result = subprocess.run(
        CLI + [str(tmp_path / "nope")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "does not exist" in result.stderr
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
pytest tests/test_ground_analogue.py -v
```

Expected: ImportError on `scripts.synthesize.ground_analogue`.

- [ ] **Step 3: Implement `ground_analogue.py`**

Create `scripts/synthesize/ground_analogue.py`:

```python
#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 1a: analogue grounding.

Reads a checked-out analogue repo and extracts observations: declared
test commands, lint commands, and CI workflow steps. Emits a JSON list
to stdout.

Contract:
    extract_observations(repo: Path) -> list[Observation]

CLI:
    python scripts/synthesize/ground_analogue.py <repo-path>
    -> stdout: JSON list of Observation dicts
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import yaml

# Allow cross-script import when invoked directly
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@dataclasses.dataclass(frozen=True)
class Observation:
    """One observed gate-shaped fact from an analogue repo."""

    source: str  # always "analogue" for this stage
    ref: str  # relative path within the repo (or repo-name-prefixed)
    command: str  # the observed command string
    context: str  # human-readable note about where this was observed
    observed_type: str  # one of pytest|ruff|mypy|cli-command-runs|run-command|coverage

    def to_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


def detect_language(repo: Path) -> str:
    """Return language tag based on top-level manifest files."""
    if (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
        return "python"
    if (repo / "package.json").exists():
        return "node"
    if (repo / "go.mod").exists():
        return "go"
    if (repo / "Cargo.toml").exists():
        return "rust"
    return "unknown"


def parse_pyproject_test_command(pyproject: Path) -> list[str] | None:
    """If pyproject.toml declares pytest testpaths, return the implied command.

    Returns None if not parseable or no testpaths declared.
    """
    if not pyproject.exists():
        return None
    try:
        import tomllib
    except ImportError:  # pragma: no cover — Python <3.11 not supported
        return None
    data = tomllib.loads(pyproject.read_text())
    pytest_cfg = (
        data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    )
    testpaths = pytest_cfg.get("testpaths")
    if not testpaths:
        return None
    if isinstance(testpaths, str):
        testpaths = [testpaths]
    return ["pytest", *testpaths]


def parse_workflow_steps(workflow_yml: Path) -> list[str]:
    """Extract every `run:` step's command string from a GitHub Actions YAML."""
    if not workflow_yml.exists():
        return []
    try:
        data = yaml.safe_load(workflow_yml.read_text()) or {}
    except yaml.YAMLError:
        return []
    out: list[str] = []
    for job in (data.get("jobs") or {}).values():
        for step in (job.get("steps") or []):
            run = step.get("run")
            if isinstance(run, str):
                out.append(run.strip())
            elif isinstance(run, list):
                out.extend(s.strip() for s in run if isinstance(s, str))
    return out


def _classify_command(cmd: str) -> str | None:
    """Map an observed command string to a criteria.yaml gate type."""
    head = cmd.strip().split()[0] if cmd.strip() else ""
    if head == "pytest":
        return "pytest"
    if head == "ruff":
        return "ruff"
    if head == "mypy":
        return "mypy"
    if head in {"coverage"}:
        return "coverage"
    # Anything else we treat as a generic run-command gate. cli-command-runs
    # is reserved for explicit single-binary smoke tests; we conservatively
    # default to run-command which is more permissive.
    return "run-command"


def extract_observations(repo: Path) -> list[Observation]:
    """Walk the repo, return all observations as a deduplicated list."""
    if not repo.exists():
        raise FileNotFoundError(f"analogue repo path does not exist: {repo}")

    repo_name = repo.name
    observations: list[Observation] = []

    # Source 1: pyproject.toml declared test command
    pyproject_cmd = parse_pyproject_test_command(repo / "pyproject.toml")
    if pyproject_cmd:
        cmd_str = " ".join(pyproject_cmd)
        observations.append(Observation(
            source="analogue",
            ref=f"{repo_name}/pyproject.toml",
            command=cmd_str,
            context="declared test command",
            observed_type="pytest",
        ))

    # Source 2: GitHub Actions workflow run-steps
    workflows_dir = repo / ".github" / "workflows"
    if workflows_dir.exists():
        for wf in sorted(workflows_dir.glob("*.yml")):
            for step_cmd in parse_workflow_steps(wf):
                otype = _classify_command(step_cmd)
                if otype is None:
                    continue
                observations.append(Observation(
                    source="analogue",
                    ref=f"{repo_name}/.github/workflows/{wf.name}",
                    command=step_cmd,
                    context="CI workflow step",
                    observed_type=otype,
                ))

    # Dedup by (command, observed_type) — keep first occurrence
    seen: set[tuple[str, str]] = set()
    deduped: list[Observation] = []
    for o in observations:
        key = (o.command, o.observed_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(o)
    return deduped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 1a: analogue grounding")
    parser.add_argument("repo", type=Path, help="path to a checked-out analogue repo")
    args = parser.parse_args(argv)

    try:
        observations = extract_observations(args.repo)
    except FileNotFoundError as exc:
        sys.stderr.write(f"ground_analogue: {exc}\n")
        return 1

    sys.stdout.write(json.dumps([o.to_dict() for o in observations], indent=2))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test, verify PASS**

```bash
pytest tests/test_ground_analogue.py -v
```

Expected: 9 PASSED.

- [ ] **Step 5: Lint**

```bash
ruff check scripts/synthesize/ground_analogue.py tests/test_ground_analogue.py
```

Expected: no errors. Note: `print` is forbidden by T201, but we use `sys.stdout.write` / `sys.stderr.write` only.

- [ ] **Step 6: Commit**

```bash
git add scripts/synthesize/ground_analogue.py tests/test_ground_analogue.py
git commit -m "$(cat <<'EOF'
synthesize: Stage 1a — analogue grounding

Reads a checked-out repo's pyproject.toml + GitHub workflows, extracts
typed observations (pytest, ruff, mypy, run-command). CLI emits JSON
list to stdout. Dedup by (command, type) to avoid noise.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Grounding orchestrator

Wraps the per-source grounding scripts and writes the unified `grounding.json` artifact under `.skillgoid/synthesis/`. In Phase 1 this only calls `ground_analogue`; the orchestrator interface is set up so Phase 2 can add `ground_context7` and `ground_template` without changing the skill prose.

**Files:**
- Create: `scripts/synthesize/ground.py`
- Test: `tests/test_ground.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ground.py`:

```python
"""Tests for scripts/synthesize/ground.py — Stage 1 orchestrator."""
import json
import subprocess
import sys
from pathlib import Path

from scripts.synthesize._common import synthesis_path
from scripts.synthesize.ground import run_ground

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthesize" / "mini-flask-demo"
CLI = [sys.executable, str(ROOT / "scripts" / "synthesize" / "ground.py")]


def test_run_ground_writes_grounding_json(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()

    out_path = run_ground(sg, analogues=[FIXTURE])

    assert out_path == synthesis_path(sg, "grounding.json")
    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert payload["language_detected"] == "python"
    assert isinstance(payload["observations"], list)
    assert len(payload["observations"]) >= 2


def test_run_ground_with_no_analogues_writes_empty_observations(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()

    out_path = run_ground(sg, analogues=[])

    payload = json.loads(out_path.read_text())
    assert payload["language_detected"] == "unknown"
    assert payload["observations"] == []


def test_run_ground_multiple_analogues_unions_observations(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()

    # Use the same fixture twice — second copy gets a different repo_name
    # by symlinking
    second = tmp_path / "fixture-copy"
    second.symlink_to(FIXTURE)

    out_path = run_ground(sg, analogues=[FIXTURE, second])
    payload = json.loads(out_path.read_text())
    # Observations from BOTH analogues are preserved (refs differ)
    refs = {o["ref"] for o in payload["observations"]}
    assert any("mini-flask-demo" in r for r in refs)
    assert any("fixture-copy" in r for r in refs)


def test_cli_with_analogue_arg_writes_grounding(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg), str(FIXTURE)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (sg / "synthesis" / "grounding.json").exists()


def test_cli_no_analogues_still_writes_empty_grounding(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((sg / "synthesis" / "grounding.json").read_text())
    assert payload["observations"] == []


def test_cli_missing_skillgoid_dir_exits_one(tmp_path):
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(tmp_path / "nope")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "not a Skillgoid project" in result.stderr
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
pytest tests/test_ground.py -v
```

Expected: ImportError on `scripts.synthesize.ground`.

- [ ] **Step 3: Implement `ground.py`**

Create `scripts/synthesize/ground.py`:

```python
#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 1: grounding orchestrator.

Phase 1: only invokes ground_analogue. Phase 2 will add ground_context7
and ground_template; keep the contract here so the skill prose does not
change between phases.

Contract:
    run_ground(sg: Path, analogues: list[Path]) -> Path
        Writes <sg>/synthesis/grounding.json and returns its path.

CLI:
    python scripts/synthesize/ground.py [--skillgoid-dir .skillgoid] <repo> [<repo> ...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow cross-script import
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.synthesize._common import (  # noqa: E402
    ensure_synthesis_dir,
    save_json,
    synthesis_path,
)
from scripts.synthesize.ground_analogue import (  # noqa: E402
    detect_language,
    extract_observations,
)


def run_ground(sg: Path, analogues: list[Path]) -> Path:
    """Run all available grounding sources, write grounding.json, return path."""
    ensure_synthesis_dir(sg)

    observations: list[dict] = []
    language = "unknown"

    for repo in analogues:
        repo_lang = detect_language(repo)
        if language == "unknown" and repo_lang != "unknown":
            language = repo_lang
        for obs in extract_observations(repo):
            observations.append(obs.to_dict())

    payload = {
        "language_detected": language,
        "framework_detected": None,  # Phase 2: populated by ground_context7
        "observations": observations,
    }

    out_path = synthesis_path(sg, "grounding.json")
    save_json(out_path, payload)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 1: grounding orchestrator")
    parser.add_argument(
        "--skillgoid-dir",
        type=Path,
        default=Path(".skillgoid"),
        help="Path to .skillgoid directory (default ./.skillgoid)",
    )
    parser.add_argument(
        "analogues",
        nargs="*",
        type=Path,
        help="Zero or more analogue repo paths",
    )
    args = parser.parse_args(argv)

    if not args.skillgoid_dir.exists() or not args.skillgoid_dir.is_dir():
        sys.stderr.write(f"ground: not a Skillgoid project: {args.skillgoid_dir}\n")
        return 1

    out_path = run_ground(args.skillgoid_dir, args.analogues)
    sys.stdout.write(f"grounding written: {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test, verify PASS**

```bash
pytest tests/test_ground.py -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Lint**

```bash
ruff check scripts/synthesize/ground.py tests/test_ground.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/synthesize/ground.py tests/test_ground.py
git commit -m "$(cat <<'EOF'
synthesize: Stage 1 — grounding orchestrator

Phase 1 only calls ground_analogue; the orchestrator contract is set up
so Phase 2 can plug in context7 + template sources without changing the
skill prose. Writes .skillgoid/synthesis/grounding.json.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Synthesis output parser

The skill prose dispatches the synthesis subagent with the synthesize prompt. The subagent's stdout JSON arrives as raw text; this script parses it, validates that every draft cites a `provenance.ref` traceable to `grounding.json`, and writes `drafts.json`. Pure function, no LLM call.

**Files:**
- Create: `scripts/synthesize/synthesize.py`
- Test: `tests/test_synthesize.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_synthesize.py`:

```python
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
    DraftValidationError,
    parse_subagent_output,
    run_synthesize,
)

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "synthesize" / "synthesize.py")]


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
    sg_synth = sg / "synthesis"
    sg_synth.mkdir(exist_ok=True)

    out_path = run_synthesize(sg, _well_formed_subagent_output())

    assert out_path == synthesis_path(sg, "drafts.json")
    payload = json.loads(out_path.read_text())
    assert len(payload["drafts"]) == 2


def test_cli_reads_subagent_output_from_stdin(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    save_json(synthesis_path(sg, "grounding.json"), _grounding_payload())
    (sg / "synthesis").mkdir(exist_ok=True)

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
    (sg / "synthesis").mkdir(exist_ok=True)

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
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
pytest tests/test_synthesize.py -v
```

Expected: ImportError on `scripts.synthesize.synthesize`.

- [ ] **Step 3: Implement `synthesize.py`**

Create `scripts/synthesize/synthesize.py`:

```python
#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 2: parse + validate subagent output.

The skill prose dispatches the synthesis subagent (with grounding.json +
goal.md as context) and pipes the subagent's stdout into this script.
This script parses the JSON, enforces the provenance contract (every
draft must cite a ref that exists in grounding.json), and writes
drafts.json.

NO LLM call is made here. The script is pure parsing + validation.

Contract:
    parse_subagent_output(raw: str, grounding: dict) -> list[dict]
        Returns validated draft dicts. Raises DraftValidationError on failure.

    run_synthesize(sg: Path, raw: str) -> Path
        Loads grounding.json, parses, writes drafts.json. Returns its path.

CLI:
    python scripts/synthesize/synthesize.py --skillgoid-dir .skillgoid
        (reads subagent output from stdin)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.synthesize._common import (  # noqa: E402
    ensure_synthesis_dir,
    load_json,
    save_json,
    synthesis_path,
)

# Mirror schemas/criteria.schema.json gate type enum exactly
SUPPORTED_GATE_TYPES = frozenset({
    "pytest", "ruff", "mypy", "import-clean",
    "cli-command-runs", "run-command", "coverage",
})


class DraftValidationError(ValueError):
    """Raised when subagent output violates the draft contract."""


def parse_subagent_output(raw: str, grounding: dict) -> list[dict]:
    """Parse subagent stdout JSON and validate each draft.

    Validation rules:
      1. Top-level must be a JSON object with key 'drafts' = list.
      2. Each draft must have id, type, provenance.{source, ref}.
      3. type must be in SUPPORTED_GATE_TYPES.
      4. provenance.ref must match an observation ref in grounding['observations'].
      5. ids must be unique across all drafts.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DraftValidationError(f"subagent output is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict) or "drafts" not in payload:
        raise DraftValidationError("subagent output must contain 'drafts' key")

    drafts = payload["drafts"]
    if not isinstance(drafts, list):
        raise DraftValidationError("'drafts' must be a list")

    valid_refs = {o.get("ref") for o in grounding.get("observations", [])}
    seen_ids: set[str] = set()

    for idx, draft in enumerate(drafts):
        if not isinstance(draft, dict):
            raise DraftValidationError(f"draft[{idx}] is not an object")

        gate_id = draft.get("id")
        if not gate_id:
            raise DraftValidationError(f"draft[{idx}] missing 'id'")
        if gate_id in seen_ids:
            raise DraftValidationError(f"duplicate gate id: {gate_id}")
        seen_ids.add(gate_id)

        gate_type = draft.get("type")
        if gate_type not in SUPPORTED_GATE_TYPES:
            raise DraftValidationError(
                f"draft '{gate_id}': unsupported gate type '{gate_type}' "
                f"(allowed: {sorted(SUPPORTED_GATE_TYPES)})"
            )

        provenance = draft.get("provenance")
        if not isinstance(provenance, dict):
            raise DraftValidationError(f"draft '{gate_id}' missing 'provenance' object")
        ref = provenance.get("ref")
        if not ref:
            raise DraftValidationError(f"draft '{gate_id}' provenance missing 'ref'")
        if ref not in valid_refs:
            raise DraftValidationError(
                f"draft '{gate_id}' provenance ref not found in grounding: {ref}"
            )

    return drafts


def run_synthesize(sg: Path, raw: str) -> Path:
    """Load grounding.json, parse raw subagent output, write drafts.json."""
    ensure_synthesis_dir(sg)
    grounding_path = synthesis_path(sg, "grounding.json")
    grounding = load_json(grounding_path)

    drafts = parse_subagent_output(raw, grounding)

    out_path = synthesis_path(sg, "drafts.json")
    save_json(out_path, {"drafts": drafts})
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 2: synthesis output parser")
    parser.add_argument(
        "--skillgoid-dir",
        type=Path,
        default=Path(".skillgoid"),
        help="Path to .skillgoid directory (default ./.skillgoid)",
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read()
    try:
        out_path = run_synthesize(args.skillgoid_dir, raw)
    except (DraftValidationError, FileNotFoundError) as exc:
        sys.stderr.write(f"synthesize: {type(exc).__name__}: {exc}\n")
        return 1

    sys.stdout.write(f"drafts written: {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test, verify PASS**

```bash
pytest tests/test_synthesize.py -v
```

Expected: 10 PASSED.

- [ ] **Step 5: Lint**

```bash
ruff check scripts/synthesize/synthesize.py tests/test_synthesize.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/synthesize/synthesize.py tests/test_synthesize.py
git commit -m "$(cat <<'EOF'
synthesize: Stage 2 — output parser + provenance enforcement

Parses subagent stdout JSON, validates each draft cites a provenance
ref traceable to grounding.json, rejects unsupported gate types and
duplicate ids. No LLM call — pure parser. The skill prose dispatches
the subagent and pipes output here.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Write criteria

Renders `criteria.yaml.proposed` from `drafts.json`. Each gate gets a comment header above it noting source, ref, and validation label (Phase 1: always `validated: none`). The output must conform to `schemas/criteria.schema.json`.

**Files:**
- Create: `scripts/synthesize/write_criteria.py`
- Test: `tests/test_write_criteria.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_write_criteria.py`:

```python
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
    assert "# validated: none (Phase 1: oracle validation deferred)" in out
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
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
pytest tests/test_write_criteria.py -v
```

Expected: ImportError on `scripts.synthesize.write_criteria`.

- [ ] **Step 3: Implement `write_criteria.py`**

Create `scripts/synthesize/write_criteria.py`:

```python
#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 4: render criteria.yaml.proposed.

Reads drafts.json and (optionally) grounding.json; produces criteria.yaml
.proposed with provenance comment headers per gate. Output conforms to
schemas/criteria.schema.json.

Phase 1: every gate is labeled `validated: none (Phase 1: oracle
validation deferred)`. Phase 2 will replace this with real oracle labels.

NEVER overwrites an existing criteria.yaml. Always writes to
.skillgoid/criteria.yaml.proposed.

Contract:
    render_criteria_yaml(drafts: dict, language: str) -> str
    run_write_criteria(sg: Path) -> Path

CLI:
    python scripts/synthesize/write_criteria.py --skillgoid-dir .skillgoid
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.synthesize._common import load_json, synthesis_path  # noqa: E402

# Phase 1 validation label (Phase 2 will switch this per-gate)
PHASE1_VALIDATION_LABEL = "validated: none (Phase 1: oracle validation deferred)"

# Internal-only fields stripped before YAML emission (not in criteria schema)
INTERNAL_FIELDS = frozenset({"provenance", "rationale"})


def _gate_to_schema_dict(draft: dict) -> dict:
    """Strip internal fields from a draft to produce a schema-conformant gate."""
    return {k: v for k, v in draft.items() if k not in INTERNAL_FIELDS}


def _gate_comment_block(draft: dict) -> str:
    """Build the comment lines that precede a gate in the rendered YAML."""
    prov = draft.get("provenance") or {}
    source = prov.get("source", "unknown")
    ref = prov.get("ref", "unknown")
    lines = [
        f"  # source: {source}, ref: {ref}",
        f"  # {PHASE1_VALIDATION_LABEL}",
    ]
    rationale = draft.get("rationale")
    if rationale:
        lines.append(f"  # rationale: {rationale}")
    return "\n".join(lines)


def render_criteria_yaml(drafts_payload: dict, language: str) -> str:
    """Render drafts to a criteria.yaml string with provenance comments.

    The output is valid YAML and conforms to schemas/criteria.schema.json.
    """
    drafts = drafts_payload.get("drafts", [])
    today = dt.date.today().isoformat()

    header_lines = [
        f"# Skillgoid criteria — synthesized {today} from:",
    ]
    sources_seen = sorted({(d.get("provenance") or {}).get("source", "unknown") for d in drafts})
    for src in sources_seen:
        # List one ref per source for the header (first encountered)
        for d in drafts:
            if (d.get("provenance") or {}).get("source") == src:
                ref = (d.get("provenance") or {}).get("ref", "unknown")
                header_lines.append(f"#   {src}: {ref}")
                break
    header_lines.append("# Review each gate below. Delete or edit as needed before running build.")
    header_lines.append("")

    body_dict: dict = {"language": language, "gates": []}
    body_dict["gates"] = [_gate_to_schema_dict(d) for d in drafts]
    body_yaml = yaml.safe_dump(body_dict, sort_keys=False, default_flow_style=False)

    if not drafts:
        # Empty gates list — emit header + body without per-gate comments
        return "\n".join(header_lines) + body_yaml

    # Splice per-gate comments above each gate entry. We re-render gates one
    # at a time so each gets its provenance comment block.
    out_lines: list[str] = list(header_lines)
    out_lines.append(f"language: {language}")
    out_lines.append("gates:")
    for draft in drafts:
        out_lines.append(_gate_comment_block(draft))
        gate_dict = _gate_to_schema_dict(draft)
        gate_yaml = yaml.safe_dump(
            [gate_dict], sort_keys=False, default_flow_style=False,
        )
        # safe_dump with a list emits "- key: val" lines; indent each by 2 spaces
        for line in gate_yaml.splitlines():
            out_lines.append(f"  {line}")
    return "\n".join(out_lines) + "\n"


def run_write_criteria(sg: Path) -> Path:
    """Load drafts.json + grounding.json, write criteria.yaml.proposed."""
    drafts_payload = load_json(synthesis_path(sg, "drafts.json"))
    try:
        grounding = load_json(synthesis_path(sg, "grounding.json"))
        language = grounding.get("language_detected", "unknown")
    except FileNotFoundError:
        language = "unknown"

    rendered = render_criteria_yaml(drafts_payload, language=language)
    out_path = sg / "criteria.yaml.proposed"
    out_path.write_text(rendered)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 4: write criteria.yaml.proposed")
    parser.add_argument(
        "--skillgoid-dir",
        type=Path,
        default=Path(".skillgoid"),
        help="Path to .skillgoid directory (default ./.skillgoid)",
    )
    args = parser.parse_args(argv)

    try:
        out_path = run_write_criteria(args.skillgoid_dir)
    except FileNotFoundError as exc:
        sys.stderr.write(f"write_criteria: {exc}\n")
        return 1

    sys.stdout.write(f"wrote: {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test, verify PASS**

```bash
pytest tests/test_write_criteria.py -v
```

Expected: 8 PASSED.

- [ ] **Step 5: Lint**

```bash
ruff check scripts/synthesize/write_criteria.py tests/test_write_criteria.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/synthesize/write_criteria.py tests/test_write_criteria.py
git commit -m "$(cat <<'EOF'
synthesize: Stage 4 — render criteria.yaml.proposed

Renders drafts.json to criteria.yaml.proposed with per-gate provenance
comment headers (source, ref, validation label) and a top-level header
listing observed sources. Output conforms to criteria.schema.json.
Never overwrites existing criteria.yaml.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Synthesis subagent prompt template

Documents the subagent's contract: input is `grounding.json` + `goal.md`; output is JSON to stdout matching the shape `synthesize.py` parses. Ships in `skills/synthesize-gates/prompts/synthesize.md` so the skill prose can read it and inject it into the dispatched agent prompt.

**Files:**
- Create: `skills/synthesize-gates/prompts/synthesize.md`

- [ ] **Step 1: Create the prompt template**

```bash
mkdir -p skills/synthesize-gates/prompts
```

Create `skills/synthesize-gates/prompts/synthesize.md`:

````markdown
# Synthesis Subagent Prompt

You are dispatched as a one-shot synthesis subagent. Your job: read the grounding observations and the project goal, then propose a list of `criteria.yaml` gates that capture what "done" should mean for this project.

## Inputs

You will receive two attachments:

1. **`grounding.json`** — observed gate-shaped facts from one or more analogue repos. Schema:
   ```json
   {
     "language_detected": "python",
     "framework_detected": null,
     "observations": [
       {
         "source": "analogue",
         "ref": "<repo-name>/<path-within-repo>",
         "command": "<observed command string>",
         "context": "<short note>",
         "observed_type": "pytest|ruff|mypy|run-command|coverage|cli-command-runs"
       }
     ]
   }
   ```

2. **`goal.md`** — the user's refined goal statement, scope, non-goals, and success signals.

## Output

Emit ONLY a single JSON object to stdout. No prose, no markdown code fences, no narration. The shape is:

```json
{
  "drafts": [
    {
      "id": "<short-snake-case-id>",
      "type": "pytest|ruff|mypy|import-clean|cli-command-runs|run-command|coverage",
      "args": ["..."],
      "timeout": 60,
      "provenance": {
        "source": "analogue",
        "ref": "<MUST exactly match a ref from grounding.json observations>"
      },
      "rationale": "<one sentence: why this gate, grounded in observation + goal>"
    }
  ]
}
```

## Hard rules

- **Every draft MUST cite a `provenance.ref` that exists exactly in `grounding.json`'s observations list.** Drafts without a real ref are rejected at parse time. Do not invent refs.
- **`type` MUST be one of the seven values in the enum above.** Anything else is rejected.
- **All gate `id`s MUST be unique** across the drafts list.
- **Do not output anything other than the JSON object.** No markdown, no commentary, no preamble.
- **Be conservative.** Only propose gates you can ground in observations + goal text. If observations don't support a gate idea, omit it. Quality over quantity.

## Guidance

- A pytest gate's `args` is the list of paths/expressions passed to pytest (e.g., `["tests"]` or `["-x", "tests/unit"]`).
- A ruff gate's `args` is typically `["check", "."]` or `["check", "src"]`.
- Use `mypy` only if observed in grounding.
- Use `run-command` for any test-runner-shaped command not covered by the typed enums (e.g., `npm test`, `go test ./...`). The `command` field for `run-command` gates is a list (e.g., `["npm", "test"]`).
- Default `timeout`: 60 for pytest, 30 for ruff/mypy, 120 for `run-command`. Adjust if the observation context suggests otherwise.

## Common pitfalls

- Citing a ref like `"shlink/tests/test_redirect.py:42"` when the observation has `"shlink/tests/test_redirect.py"` (without line number) — these don't match. Copy the ref string verbatim.
- Emitting markdown fences around the JSON. The parser strictly does `json.loads(stdout)`. Anything other than the JSON object causes failure.
- Inventing gate types like `"smoke"` or `"e2e"` — those aren't in the enum.
````

- [ ] **Step 2: No tests for this file**

The prompt is a static markdown document consumed by the skill prose. It is verified end-to-end by the integration test in Task 9.

- [ ] **Step 3: Commit**

```bash
git add skills/synthesize-gates/prompts/synthesize.md
git commit -m "$(cat <<'EOF'
synthesize: Stage 2 subagent prompt template

Documents the contract the synthesis subagent must follow: input is
grounding.json + goal.md, output is a single JSON object matching the
drafts shape that synthesize.py validates. Hard rules enforce
provenance + gate-type enum.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Skill SKILL.md — orchestrate the four stages

The skill prose drives the four-stage pipeline: parse args → run grounding → dispatch synthesis subagent → parse output → write criteria. Includes the auto-discovered slash command `/skillgoid:synthesize-gates`.

**Files:**
- Create: `skills/synthesize-gates/SKILL.md`

- [ ] **Step 1: Create the skill prose**

Create `skills/synthesize-gates/SKILL.md`:

```markdown
---
name: synthesize-gates
description: Use when the user wants to author `.skillgoid/criteria.yaml` from observation rather than from scratch. Given one or more analogue reference repos, the skill grounds observations, dispatches a synthesis subagent, validates the proposed gates against the criteria schema, and writes `.skillgoid/criteria.yaml.proposed` with per-gate provenance comments. Phase 1: user-pointed analogues only, no oracle validation, all gates labeled `validated: none`. Invokable as `/skillgoid:synthesize-gates <repo-url-or-path> [<repo2> ...]`.
---

# synthesize-gates

## What this skill does

Produces a draft `criteria.yaml` from observation of one or more analogue reference repositories. Each proposed gate carries a provenance comment so the user can trace it back to a real source. Output goes to `.skillgoid/criteria.yaml.proposed` — never overwrites existing `criteria.yaml`.

## When to use

- The user has a project goal in `.skillgoid/goal.md` and points to one or more reference repos as inspiration.
- The user explicitly invokes `/skillgoid:synthesize-gates <repo-url-or-path>`.
- After a `/skillgoid:clarify` run, when the user prefers synthesized gates over hand-authored.

**NOT** for:

- Projects with no analogue at all (Phase 1 requires at least one — Phase 2 will add context7 + curated templates as fallbacks).
- Modifying an existing committed `criteria.yaml` directly (always writes to `.proposed` for the user to merge).
- Validation of the gates' actual behavior (Phase 1 emits `validated: none`; Phase 2 adds oracle validation).

## Inputs

- One or more analogue repo references, each either:
  - A git URL — the skill clones it (shallow, depth=1) into `.skillgoid/synthesis/analogues/<slug>/`.
  - A local filesystem path — symlinked or referenced directly.
- `.skillgoid/goal.md` — must already exist (run `/skillgoid:clarify` first if absent).

If no analogues are provided as args, the skill interactively prompts for at least one. Phase 1 has no fallback to context7 / templates — at least one analogue is required.

## Procedure

1. **Verify `.skillgoid/goal.md` exists.** If not, error: `"goal.md missing — run /skillgoid:clarify first."` Do not proceed.

2. **Resolve analogue paths.**
   - For each git URL arg: shallow-clone into `.skillgoid/synthesis/analogues/<slug>/` where `<slug>` is the URL's owner+repo (e.g., `pallets-flask` for `github.com/pallets/flask`). Skip clone if directory already exists.
   - For each local path arg: verify the directory exists. Use the path as-is.
   - If zero analogues given on CLI, prompt the user: `"No analogue repo provided. Please give a URL or local path to a reference project: "`. Read one line, treat as a single analogue.

3. **Run Stage 1 (grounding).** Shell out:
   ```bash
   python <plugin-root>/scripts/synthesize/ground.py \
     --skillgoid-dir .skillgoid \
     <analogue1-path> [<analogue2-path> ...]
   ```
   On non-zero exit, surface stderr to the user and stop.

4. **Verify grounding has at least one observation.** Read `.skillgoid/synthesis/grounding.json`. If `observations` is empty, error: `"No observations could be extracted from the analogue repo(s). Phase 1 requires at least one observable test or CI command."` Do not dispatch the subagent.

5. **Dispatch the synthesis subagent.** Use the Agent tool with:
   - `description`: `"Synthesize gates"`
   - `prompt`: contents of `skills/synthesize-gates/prompts/synthesize.md`, followed by two `<attachment>` blocks containing `grounding.json` and `goal.md` verbatim.
   - `subagent_type`: `"general-purpose"`
   - Model: default (sonnet).

   Capture the subagent's final text output as `subagent_stdout`.

6. **Run Stage 2 (parse + validate).** Shell out:
   ```bash
   echo "$subagent_stdout" | python <plugin-root>/scripts/synthesize/synthesize.py \
     --skillgoid-dir .skillgoid
   ```
   If the parser exits non-zero, surface its stderr (which names the violated rule) and STOP. Do not retry the subagent in Phase 1 — surface the failure so the user can re-run or hand-author. Phase 2 will add a single auto-retry.

7. **Run Stage 4 (write).** Shell out:
   ```bash
   python <plugin-root>/scripts/synthesize/write_criteria.py \
     --skillgoid-dir .skillgoid
   ```

8. **Print the next-step summary** to the user:
   ```
   synthesize-gates: wrote .skillgoid/criteria.yaml.proposed

   Next:
     diff .skillgoid/criteria.yaml .skillgoid/criteria.yaml.proposed
     (or open .skillgoid/criteria.yaml.proposed in your editor)

   When you're happy with the gates, replace criteria.yaml with the .proposed
   version and run /skillgoid:build.
   ```

## Output

On success: `.skillgoid/criteria.yaml.proposed` is written. Existing `.skillgoid/criteria.yaml` is untouched. Per-stage artifacts are visible under `.skillgoid/synthesis/` (`grounding.json`, `drafts.json`) for debugging.

On failure: a single error line on stderr naming the failed stage. Partial artifacts under `.skillgoid/synthesis/` may remain — these are safe to inspect or delete.

## Phase 1 limitations (called out for users)

- All gates are labeled `validated: none (Phase 1: oracle validation deferred)`. The user is the only validator.
- No context7 grounding — only user-pointed analogues.
- No curated template fallback for cold-start projects.
- No retry on subagent output validation failure — re-run the skill if needed.

Phase 2 (planned) addresses all four.

## Risks

- Synthesis quality is bounded by the analogue quality. A poorly-tested analogue produces poorly-grounded gates.
- The `criteria.yaml.proposed` may include gate types the user's project doesn't need. The user is expected to delete unwanted gates during review.
- If two analogue repos use conflicting conventions (e.g., one uses pytest, the other uses unittest), the synthesis subagent picks one — the rationale field should explain why.
```

- [ ] **Step 2: Verify the skill is auto-discovered**

```bash
ls skills/synthesize-gates/
```

Expected: `SKILL.md` and `prompts/synthesize.md` listed. Plugin auto-discovers skills by directory presence; no manifest update needed.

- [ ] **Step 3: Commit**

```bash
git add skills/synthesize-gates/SKILL.md
git commit -m "$(cat <<'EOF'
synthesize: skill orchestration for the four-stage pipeline

skills/synthesize-gates/SKILL.md drives Phase 1: parse args, ground
analogues, dispatch synthesis subagent, parse + validate output,
write criteria.yaml.proposed. Phase 1 limitations called out
explicitly (no context7, no templates, no oracle validation).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: End-to-end integration test

Exercise the full script-level pipeline (everything except the actual subagent dispatch — that is mocked by feeding fixed JSON to `synthesize.py`). Verifies that grounding → synthesize → write produces a schema-valid `criteria.yaml.proposed` with the expected provenance labels when fed the mini-flask-demo fixture.

**Files:**
- Create: `tests/test_synthesize_e2e.py`

- [ ] **Step 1: Write the integration test**

Create `tests/test_synthesize_e2e.py`:

```python
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
    """Empty analogue → grounding has 0 observations → synthesize must NOT be invoked.

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
```

- [ ] **Step 2: Run integration test, verify PASS**

```bash
pytest tests/test_synthesize_e2e.py -v
```

Expected: 2 PASSED.

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
pytest -q
```

Expected: all previous tests still pass + the 2 new e2e tests. Total should be the previous count + the synthesize tests added across Tasks 1-9.

- [ ] **Step 4: Lint everything**

```bash
ruff check scripts/synthesize/ tests/test_synthesize*.py tests/test_ground*.py tests/test_write_criteria.py
```

Expected: no errors.

- [ ] **Step 5: Smoke-test the CLI end-to-end manually**

```bash
cd /tmp && rm -rf skillgoid-synth-smoke && mkdir skillgoid-synth-smoke && cd skillgoid-synth-smoke
mkdir .skillgoid
echo "# Goal" > .skillgoid/goal.md

python /home/flip/Development/skillgoid/skillgoid-plugin/scripts/synthesize/ground.py \
  --skillgoid-dir .skillgoid \
  /home/flip/Development/skillgoid/skillgoid-plugin/tests/fixtures/synthesize/mini-flask-demo

cat .skillgoid/synthesis/grounding.json
```

Expected: `grounding.json` exists with `language_detected: python` and at least 2 observations from the mini-flask fixture.

- [ ] **Step 6: Commit**

```bash
git add tests/test_synthesize_e2e.py
git commit -m "$(cat <<'EOF'
synthesize: end-to-end pipeline integration test

Mocks the subagent dispatch by feeding hand-crafted drafts JSON whose
provenance refs are picked from the actual grounding.json. Verifies
schema validity, provenance comments, and that internal fields (provenance,
rationale) are stripped before YAML emission.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review (post-write checklist)

**1. Spec coverage:** Walking through the spec section-by-section against this plan:

- §Architecture (4-stage pipeline, scripts in `scripts/synthesize/`) → Tasks 1, 3, 4, 5, 6 cover Stages 1, 2, 4 + helpers. Stage 3 (validate) is explicitly deferred to Phase 2 (called out in plan header + skill prose).
- §Stage 1: Ground →
  - 1a (analogue) → Task 3.
  - 1b (context7) → **Phase 2.**
  - 1c (templates) → **Phase 2.**
  - Orchestrator → Task 4.
- §Stage 2: Synthesize → Task 5 (parser); Task 7 (prompt template); Task 8 (skill drives dispatch).
- §Stage 3: Validate → **Phase 2 — explicit deferral with `validated: none` label.**
- §Stage 4: Write → Task 6.
- §Clean-split change to `clarify` → **Phase 2.** Phase 1 writes to `.proposed` so existing flow is untouched.
- §Testing strategy → Tasks 1, 3, 4, 5, 6 each have unit tests; Task 9 is the integration test. No live-LLM tests (subagent dispatch mocked at the script boundary).
- §Risks (hallucination, install failures, context7 unavailability, breakage of clarify) → Phase 1 covers hallucination via Task 5's provenance enforcement. Other risks belong to Phase 2.
- §Success criteria → Phase 1 success is `synthesize-gates <repo-url>` produces a schema-valid `criteria.yaml.proposed` end-to-end; Task 9 verifies this with a mocked subagent and Task 8 step 2 manually verifies skill discovery.

**2. Placeholder scan:** No `TBD`, `TODO`, `implement later`, "add appropriate validation", or skipped code blocks. Every step has either complete code or an exact command + expected output.

**3. Type consistency:** Cross-task references checked:
- `Observation` dataclass (Task 3) is imported by `ground.py` (Task 4) — both use `to_dict()` and same field names.
- `_common.py` helpers (`load_json`, `save_json`, `synthesis_path`, `ensure_synthesis_dir`) (Task 1) are imported consistently by Tasks 4, 5, 6.
- `DraftValidationError` (Task 5) — only raised inside `synthesize.py`, no external consumers.
- `SUPPORTED_GATE_TYPES` (Task 5) — single source of truth, mirrored from `schemas/criteria.schema.json` enum.
- `INTERNAL_FIELDS` / `PHASE1_VALIDATION_LABEL` (Task 6) — used only inside `write_criteria.py`.
- Subagent prompt (Task 7) and parser (Task 5) agree on output shape: `{"drafts": [{"id", "type", "provenance": {"source", "ref"}, ...}]}`. Both call out the seven supported gate types and the provenance-ref enforcement.

No drift detected.

---

## Phase 2 (out of scope for this plan, recorded for context)

Phase 2 will add:
- `scripts/synthesize/ground_context7.py` (Stage 1b)
- `scripts/synthesize/ground_template.py` (Stage 1c) + `templates/gate-library/*.yaml` (5 templates) + `templates/fixture-repos/*` (Python/Node/Go fixtures)
- `scripts/synthesize/validate.py` (Stage 3 oracle validation with graceful degradation)
- Update `scripts/synthesize/write_criteria.py` to consume `validated.json` instead of `drafts.json` and render real per-gate validation labels
- Update `scripts/synthesize/ground.py` orchestrator to call all three sources
- `clarify` skill change: stop producing `criteria.yaml`; print next-step pointer to `synthesize-gates`
- Single auto-retry for synthesis subagent on validation failure
- Integration tests against fixture-repos for Stage 3

Phase 2 plan will be written separately after Phase 1 ships and we have real-world synthesis output to inform the next iteration.
