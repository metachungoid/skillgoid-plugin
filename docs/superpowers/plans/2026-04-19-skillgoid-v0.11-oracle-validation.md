# Skillgoid v0.11 — Oracle Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every synthesized gate lands in `criteria.yaml.proposed` carrying a `validated: oracle | smoke-only | none` label derived from real adapter runs against the analogue and an empty scaffold.

**Architecture:** Insert a new Stage 3 (`validate.py`) between synthesize and write. Reuse the existing `measure_python` adapter — no duplicate gate-execution logic. Per-gate: run adapter in the analogue's cache-dir (should-pass), then in a type-driven tmpdir scaffold (should-fail), classify, accumulate. Rendering gains a `# validated:` line plus optional `# warn:` line per gate. Two new flags: `--skip-validation` (bypass stage 3) and `--validate-only` (re-run stage 3 + 4 against an existing drafts.json).

**Tech Stack:** Python ≥ 3.11; existing `measure_python.run_gates(criteria, project)` as the oracle executor; `tempfile.TemporaryDirectory` for scaffolds; `time.monotonic()` for the 10-minute stage cap.

**Spec:** [`docs/superpowers/specs/2026-04-19-skillgoid-v0.11-oracle-validation.md`](../specs/2026-04-19-skillgoid-v0.11-oracle-validation.md)

---

## File structure overview

Files this plan touches, with one-line responsibility each:

- **Create:** `scripts/synthesize/_scaffold.py` — per-gate-type tmpdir scaffold factory. Pure builder; no adapter interaction.
- **Create:** `scripts/synthesize/validate.py` — Stage 3 orchestrator. Reads drafts.json + grounding.json, runs oracle per draft, writes validated.json.
- **Modify:** `scripts/synthesize/ground.py` — add `analogues: {slug -> absolute_path}` to grounding.json so validate.py can resolve refs to on-disk checkouts.
- **Modify:** `scripts/synthesize/write_criteria.py` — replace the fixed Phase 1 label with per-gate labels read from validated.json; render optional `# warn:` lines.
- **Modify:** `skills/synthesize-gates/SKILL.md` — add Stage 3 step, forward `--skip-validation`, add `--validate-only` short-circuit, update Phase 2 limitations block.
- **Modify:** `tests/test_synthesize_e2e.py` — extend canonical-coverage e2e to assert `# validated:` lines.
- **Create:** `tests/test_scaffold.py` — per-gate-type scaffold contents.
- **Create:** `tests/test_validate.py` — classification, timeout, skip flag, missing-analogue, per-ref slug pick.
- **Modify:** `.claude-plugin/plugin.json` — version bump 0.10.0 → 0.11.0.
- **Modify:** `CHANGELOG.md` — 0.11.0 entry at top.

---

## Phase A — Grounding contract: slug → path map

### Task 1: Expose analogue paths in grounding.json

**Context:** validate.py needs to resolve a draft's `provenance.ref` (e.g., `mini-flask-demo/pyproject.toml`) to an on-disk checkout path. Today the slug-to-path mapping lives only in `run_ground()`'s loop variables. We need to persist it. The `analogues` map is a flat `{slug: absolute_path}` dict appended to grounding.json. Readers that ignore unknown fields (including the schema, which isn't published for grounding.json) are unaffected.

**Files:**
- Modify: `scripts/synthesize/ground.py` — `run_ground()` body.
- Modify: `tests/test_ground.py` — add an assertion for the new field.

- [ ] **Step 1.1: Add the failing test**

Append to `tests/test_ground.py`:

```python
def test_grounding_includes_analogues_map(tmp_path):
    """grounding.json exposes a {slug: absolute_path} map for oracle validation."""
    import json as _json
    from scripts.synthesize.ground import run_ground

    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    fixture = Path(__file__).resolve().parents[0] / "fixtures" / "synthesize" / "mini-flask-demo"

    run_ground(sg, [fixture])
    payload = _json.loads((sg / "synthesis" / "grounding.json").read_text())

    assert "analogues" in payload
    assert payload["analogues"]["mini-flask-demo"] == str(fixture.resolve())
```

- [ ] **Step 1.2: Run it to confirm failure**

Run: `.venv/bin/pytest tests/test_ground.py::test_grounding_includes_analogues_map -v`
Expected: FAIL with KeyError on `"analogues"`.

- [ ] **Step 1.3: Implement**

In `scripts/synthesize/ground.py`, find `run_ground()`. Replace the block that builds `payload` (roughly lines 156–160) with:

```python
    analogues_map: dict[str, str] = {}
    # Re-walk args to capture slug→absolute-path (keeping existing URL/local classification)
    for arg in analogues:
        arg_str = str(arg)
        if _is_url(arg_str):
            slug = _slug_for_url(arg_str)
            repo_path = _cache_dir() / slug
        else:
            p = Path(arg_str)
            slug = p.name
            repo_path = p
        if repo_path.exists():
            analogues_map[slug] = str(repo_path.resolve())

    payload = {
        "language_detected": language,
        "framework_detected": None,  # Phase 2: populated by ground_context7
        "analogues": analogues_map,
        "observations": observations,
    }
```

Keep the prior per-arg clone/migrate loop above this block untouched — this second loop only computes the map.

- [ ] **Step 1.4: Run the failing test to verify**

Run: `.venv/bin/pytest tests/test_ground.py::test_grounding_includes_analogues_map -v`
Expected: PASS.

- [ ] **Step 1.5: Run full suite to verify no regression**

Run: `.venv/bin/pytest -q`
Expected: all existing tests still pass (322 + 1 new = 323).

- [ ] **Step 1.6: Commit**

```bash
git add scripts/synthesize/ground.py tests/test_ground.py
git commit -m "feat(ground): publish {slug: absolute_path} analogues map for oracle validation"
```

---

## Phase B — Scaffold factory

### Task 2: Per-gate-type scaffold builder

**Context:** Oracle's should-fail run needs a tmpdir populated just enough to let the adapter execute without a setup error (so the gate fails for *content* reasons, not *structural* reasons). Each gate type has different minimums. This task encodes spec table D4 as a data-driven factory and wraps it in a context manager.

**Files:**
- Create: `scripts/synthesize/_scaffold.py`
- Create: `tests/test_scaffold.py`

- [ ] **Step 2.1: Write the failing test**

Create `tests/test_scaffold.py`:

```python
"""Tests for scripts/synthesize/_scaffold.py — per-gate-type should-fail scaffolds."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.synthesize._scaffold import build_scaffold


def _read_pyproject(path: Path) -> str:
    return (path / "pyproject.toml").read_text() if (path / "pyproject.toml").exists() else ""


def test_scaffold_pytest_creates_empty_tests_dir(tmp_path):
    gate = {"id": "pytest_main", "type": "pytest", "args": ["tests"]}
    with build_scaffold("pytest", gate, analogue_cache_dir=None) as scaffold:
        assert (scaffold / "tests").is_dir()
        assert list((scaffold / "tests").iterdir()) == []


def test_scaffold_ruff_creates_empty_src_and_copies_ruff_config(tmp_path):
    analogue = tmp_path / "analogue"
    analogue.mkdir()
    (analogue / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[tool.ruff]\nline-length = 120\n'
    )
    gate = {"id": "lint", "type": "ruff", "args": ["check", "."]}
    with build_scaffold("ruff", gate, analogue_cache_dir=analogue) as scaffold:
        assert (scaffold / "src" / "__init__.py").exists()
        assert (scaffold / "src" / "__init__.py").read_text() == ""
        pyproject = _read_pyproject(scaffold)
        assert "[tool.ruff]" in pyproject
        assert "line-length = 120" in pyproject


def test_scaffold_mypy_creates_empty_src_and_copies_mypy_config(tmp_path):
    analogue = tmp_path / "analogue"
    analogue.mkdir()
    (analogue / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[tool.mypy]\nstrict = true\n'
    )
    gate = {"id": "typecheck", "type": "mypy", "args": ["src"]}
    with build_scaffold("mypy", gate, analogue_cache_dir=analogue) as scaffold:
        assert (scaffold / "src" / "__init__.py").exists()
        pyproject = _read_pyproject(scaffold)
        assert "[tool.mypy]" in pyproject
        assert "strict = true" in pyproject


def test_scaffold_coverage_creates_tests_and_src(tmp_path):
    gate = {"id": "cov", "type": "coverage", "min_percent": 80}
    with build_scaffold("coverage", gate, analogue_cache_dir=None) as scaffold:
        assert (scaffold / "tests").is_dir()
        assert (scaffold / "src").is_dir()
        pyproject = _read_pyproject(scaffold)
        assert "testpaths" in pyproject
        assert '["tests"]' in pyproject


def test_scaffold_cli_command_runs_emits_failing_entry_point(tmp_path):
    gate = {"id": "cli", "type": "cli-command-runs", "args": ["mycli", "--help"]}
    with build_scaffold("cli-command-runs", gate, analogue_cache_dir=None) as scaffold:
        app = scaffold / "src" / "app.py"
        assert app.exists()
        assert "raise SystemExit(1)" in app.read_text()
        pyproject = _read_pyproject(scaffold)
        assert "[project.scripts]" in pyproject


def test_scaffold_run_command_is_empty_tmpdir(tmp_path):
    gate = {"id": "run", "type": "run-command", "command": ["echo", "hi"]}
    with build_scaffold("run-command", gate, analogue_cache_dir=None) as scaffold:
        assert list(scaffold.iterdir()) == []


def test_scaffold_import_clean_emits_failing_package(tmp_path):
    gate = {"id": "imp", "type": "import-clean", "args": ["mypackage"]}
    with build_scaffold("import-clean", gate, analogue_cache_dir=None) as scaffold:
        init = scaffold / "src" / "mypackage" / "__init__.py"
        assert init.exists()
        assert "raise ImportError" in init.read_text()


def test_scaffold_unknown_gate_type_errors(tmp_path):
    gate = {"id": "x", "type": "future-type"}
    with pytest.raises(ValueError, match="unsupported gate type"):
        with build_scaffold("future-type", gate, analogue_cache_dir=None):
            pass


def test_scaffold_cleans_up_on_exit(tmp_path):
    gate = {"id": "pytest_main", "type": "pytest"}
    with build_scaffold("pytest", gate, analogue_cache_dir=None) as scaffold:
        assert scaffold.exists()
        captured = scaffold
    assert not captured.exists()
```

- [ ] **Step 2.2: Run the failing test**

Run: `.venv/bin/pytest tests/test_scaffold.py -v`
Expected: FAIL with ModuleNotFoundError on `scripts.synthesize._scaffold`.

- [ ] **Step 2.3: Implement the scaffold module**

Create `scripts/synthesize/_scaffold.py`:

```python
"""Per-gate-type should-fail scaffold builder for oracle validation.

build_scaffold is a context manager that yields a tmpdir populated with the
minimum structure a gate type needs to execute without setup errors. The
goal is for the adapter to fail in the *content* layer (no tests found, no
real code imported) rather than the *structural* layer (missing pyproject,
missing src).

Per-type factory rules are encoded in _GATE_SCAFFOLDS. Adding a new gate
type = add one entry.
"""
from __future__ import annotations

import contextlib
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, Iterator

# Only parse the subset of pyproject TOML sections needed for scaffold copy.
# tomllib is stdlib on 3.11+.
import tomllib


def _copy_tool_section(analogue_cache_dir: Path | None, section: str, scaffold: Path) -> None:
    """If analogue pyproject.toml has [tool.<section>], copy that section.

    Writes to scaffold/pyproject.toml. No-op if analogue is None or has no
    pyproject or no matching section.
    """
    if analogue_cache_dir is None:
        return
    src = analogue_cache_dir / "pyproject.toml"
    if not src.exists():
        return
    try:
        data = tomllib.loads(src.read_text())
    except tomllib.TOMLDecodeError:
        return
    tool_data = data.get("tool", {}).get(section)
    if tool_data is None:
        return
    # Hand-render the section so we don't pull in tomli_w
    dst = scaffold / "pyproject.toml"
    lines = [f"[tool.{section}]"]
    for k, v in tool_data.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {str(v).lower()}")
        elif isinstance(v, int):
            lines.append(f"{k} = {v}")
        elif isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, list):
            items = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
            lines.append(f"{k} = [{items}]")
        # Nested tables skipped — v0.11 analogues don't need them. If a future
        # analogue does, extend here.
    dst.write_text("\n".join(lines) + "\n")


def _scaffold_pytest(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    (scaffold / "tests").mkdir()


def _scaffold_ruff(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    (scaffold / "src").mkdir()
    (scaffold / "src" / "__init__.py").write_text("")
    _copy_tool_section(analogue, "ruff", scaffold)


def _scaffold_mypy(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    (scaffold / "src").mkdir()
    (scaffold / "src" / "__init__.py").write_text("")
    _copy_tool_section(analogue, "mypy", scaffold)


def _scaffold_coverage(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    (scaffold / "tests").mkdir()
    (scaffold / "src").mkdir()
    (scaffold / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\n'
    )


def _scaffold_cli_command_runs(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    src_dir = scaffold / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("def main():\n    raise SystemExit(1)\n")
    (scaffold / "pyproject.toml").write_text(
        "[project]\n"
        'name = "scaffold"\n'
        'version = "0.0.0"\n'
        "[project.scripts]\n"
        'scaffold = "app:main"\n'
    )


def _scaffold_run_command(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    pass  # empty tmpdir — the gate's command is self-contained


def _scaffold_import_clean(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    args = gate.get("args") or ["mypackage"]
    pkg_name = args[0] if args else "mypackage"
    pkg_dir = scaffold / "src" / pkg_name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text('raise ImportError("scaffold")\n')


_GATE_SCAFFOLDS: dict[str, Callable[[Path, dict, Path | None], None]] = {
    "pytest": _scaffold_pytest,
    "ruff": _scaffold_ruff,
    "mypy": _scaffold_mypy,
    "coverage": _scaffold_coverage,
    "cli-command-runs": _scaffold_cli_command_runs,
    "run-command": _scaffold_run_command,
    "import-clean": _scaffold_import_clean,
}


@contextlib.contextmanager
def build_scaffold(
    gate_type: str,
    gate: dict,
    analogue_cache_dir: Path | None,
) -> Iterator[Path]:
    """Yield a freshly-created tmpdir populated per gate_type's scaffold rules.

    On exit the tmpdir and all contents are removed. Raises ValueError if
    gate_type has no scaffold rule (caller should catch and classify as
    `validated: none`).
    """
    factory = _GATE_SCAFFOLDS.get(gate_type)
    if factory is None:
        raise ValueError(
            f"unsupported gate type for scaffold: {gate_type} — "
            f"add a row to _GATE_SCAFFOLDS"
        )
    tmp = Path(tempfile.mkdtemp(prefix="skillgoid-scaffold-"))
    try:
        factory(tmp, gate, analogue_cache_dir)
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 2.4: Run the tests to verify pass**

Run: `.venv/bin/pytest tests/test_scaffold.py -v`
Expected: 9 PASS.

- [ ] **Step 2.5: Lint**

Run: `.venv/bin/ruff check scripts/synthesize/_scaffold.py tests/test_scaffold.py`
Expected: no violations.

- [ ] **Step 2.6: Commit**

```bash
git add scripts/synthesize/_scaffold.py tests/test_scaffold.py
git commit -m "feat(scaffold): per-gate-type should-fail tmpdir factory for oracle validation"
```

---

## Phase C — Validate.py orchestration

### Task 3: validate.py skeleton with `--skip-validation`

**Context:** Stand up the module, CLI, I/O, and the trivial skip path. No oracle execution yet — that comes in Task 4. This task is about proving the data-flow plumbing works before layering classification on top.

**Files:**
- Create: `scripts/synthesize/validate.py`
- Create: `tests/test_validate.py`

- [ ] **Step 3.1: Write the failing test**

Create `tests/test_validate.py`:

```python
"""Tests for scripts/synthesize/validate.py — Stage 3 oracle validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.synthesize.validate import run_validate


def _make_sg(tmp_path: Path, drafts: list[dict], analogues: dict[str, str]) -> Path:
    sg = tmp_path / ".skillgoid"
    synthesis = sg / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / "drafts.json").write_text(json.dumps({"drafts": drafts}))
    (synthesis / "grounding.json").write_text(json.dumps({
        "language_detected": "python",
        "framework_detected": None,
        "analogues": analogues,
        "observations": [],
    }))
    return sg


def test_skip_validation_emits_none_for_every_gate(tmp_path):
    drafts = [
        {"id": "pytest_main", "type": "pytest", "args": ["tests"], "provenance": {
            "source": "analogue", "ref": "demo/pyproject.toml"}},
        {"id": "lint", "type": "ruff", "args": ["check", "."], "provenance": {
            "source": "analogue", "ref": "demo/pyproject.toml"}},
    ]
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(tmp_path)})

    out = run_validate(sg, skip=True)

    payload = json.loads(out.read_text())
    assert out == sg / "synthesis" / "validated.json"
    assert len(payload["gates"]) == 2
    for entry in payload["gates"]:
        assert entry["validated"] == "none"
        assert entry["warn"] == "validation skipped by --skip-validation"
        assert entry["oracle_run"] is None
```

- [ ] **Step 3.2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_validate.py::test_skip_validation_emits_none_for_every_gate -v`
Expected: FAIL with ModuleNotFoundError on `scripts.synthesize.validate`.

- [ ] **Step 3.3: Implement validate.py skeleton**

Create `scripts/synthesize/validate.py`:

```python
#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 3: oracle validation.

For each draft gate, runs the measure_python adapter against:
  - should-pass: the analogue's cache-dir (resolved from draft's first ref)
  - should-fail: a type-driven tmpdir scaffold (scripts/synthesize/_scaffold)
and classifies the pair into {oracle, smoke-only, none} with optional warn.

Output: .skillgoid/synthesis/validated.json

CLI:
    python scripts/synthesize/validate.py --skillgoid-dir .skillgoid
    python scripts/synthesize/validate.py --skillgoid-dir .skillgoid --skip-validation
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.synthesize._common import load_json, save_json, synthesis_path  # noqa: E402


def _skip_payload(drafts: list[dict]) -> dict:
    """Produce a validated.json-shaped payload where every gate is skipped."""
    return {
        "schema_version": 1,
        "gates": [
            {
                "id": d["id"],
                "validated": "none",
                "warn": "validation skipped by --skip-validation",
                "oracle_run": None,
            }
            for d in drafts
        ],
    }


def run_validate(sg: Path, skip: bool = False, stage_timeout_sec: int = 600) -> Path:
    """Run Stage 3 oracle validation. Returns the path to validated.json."""
    drafts_payload = load_json(synthesis_path(sg, "drafts.json"))
    drafts = drafts_payload.get("drafts", [])

    if skip:
        payload = _skip_payload(drafts)
    else:
        # Task 4+ will replace this branch with real oracle execution.
        raise NotImplementedError("oracle execution lands in Task 4")

    out = synthesis_path(sg, "validated.json")
    save_json(out, payload)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 3: oracle validation")
    parser.add_argument("--skillgoid-dir", type=Path, default=Path(".skillgoid"))
    parser.add_argument("--skip-validation", action="store_true",
                        help="Emit validated: none for every gate without running oracle")
    parser.add_argument("--stage-timeout-sec", type=int, default=600,
                        help="Total wall-clock cap for Stage 3 (default 600)")
    args = parser.parse_args(argv)

    try:
        out_path = run_validate(args.skillgoid_dir, skip=args.skip_validation,
                                stage_timeout_sec=args.stage_timeout_sec)
    except FileNotFoundError as exc:
        sys.stderr.write(f"validate: {exc}\n")
        return 1

    sys.stdout.write(f"wrote: {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3.4: Run failing test to verify pass**

Run: `.venv/bin/pytest tests/test_validate.py::test_skip_validation_emits_none_for_every_gate -v`
Expected: PASS.

- [ ] **Step 3.5: Lint**

Run: `.venv/bin/ruff check scripts/synthesize/validate.py tests/test_validate.py`
Expected: no violations.

- [ ] **Step 3.6: Commit**

```bash
git add scripts/synthesize/validate.py tests/test_validate.py
git commit -m "feat(validate): Stage 3 skeleton with --skip-validation emitting uniform none"
```

---

### Task 4: Single-gate oracle runner and classification table

**Context:** Replace the `NotImplementedError` in `run_validate`'s else branch with real oracle execution. For each draft gate:

1. Resolve the analogue cache-dir from the draft's first ref.
2. Run `measure_python.run_gates({gates: [<one gate>]}, analogue_cache_dir)` — this is should-pass.
3. Build the scaffold tmpdir, run the same thing against it — should-fail.
4. Classify per spec table D4.

Classification result becomes one entry in `validated.json`. We're coding the non-coverage table rows here; coverage's custom semantics comes in Task 5.

**Files:**
- Modify: `scripts/synthesize/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 4.1: Add the failing tests**

Append to `tests/test_validate.py`:

```python
from unittest import mock


def _gate_result(passed: bool, stdout: str = "", stderr: str = "", hint: str = "") -> dict:
    return {"gate_id": "irrelevant", "passed": passed, "stdout": stdout,
            "stderr": stderr, "hint": hint}


def _adapter_stub(seq):
    """Return a stub for measure_python.run_gates that yields results in order.

    seq is a list of (passed, stdout_hint) tuples — one per call.
    """
    calls = iter(seq)

    def _run_gates(criteria, project):
        passed, stdout = next(calls)
        return {"passed": passed,
                "results": [_gate_result(passed=passed, stdout=stdout)]}
    return _run_gates


def test_classify_pass_fail_labels_oracle(tmp_path):
    drafts = [{"id": "pytest_main", "type": "pytest",
               "args": ["tests"], "provenance": {
                   "source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    with mock.patch("scripts.synthesize.validate.run_gates",
                    _adapter_stub([(True, ""), (False, "")])):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "oracle"
    assert payload["gates"][0]["warn"] is None


def test_classify_pass_pass_labels_smoke_only(tmp_path):
    drafts = [{"id": "pytest_main", "type": "pytest", "args": ["tests"],
               "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    with mock.patch("scripts.synthesize.validate.run_gates",
                    _adapter_stub([(True, ""), (True, "")])):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "smoke-only"
    assert "scaffold also passes" in payload["gates"][0]["warn"]


def test_classify_fail_on_should_pass_labels_none(tmp_path):
    drafts = [{"id": "pytest_main", "type": "pytest", "args": ["tests"],
               "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    def _run_gates(criteria, project):
        return {"passed": False, "results": [_gate_result(
            passed=False, stderr="ModuleNotFoundError: flask")]}

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "none"
    assert "should-pass failed" in payload["gates"][0]["warn"]
    assert "ModuleNotFoundError" in payload["gates"][0]["warn"]
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_validate.py -k "classify" -v`
Expected: FAIL with NotImplementedError.

- [ ] **Step 4.3: Implement oracle execution**

In `scripts/synthesize/validate.py`, at the top add the adapter import (so tests can monkey-patch via `scripts.synthesize.validate.run_gates`):

```python
from scripts.measure_python import run_gates  # noqa: E402
from scripts.synthesize._scaffold import build_scaffold  # noqa: E402
```

Then replace `run_validate` and add a `_classify` helper. Keep `_skip_payload` as-is:

```python
def _resolve_analogue_path(draft: dict, analogues_map: dict[str, str]) -> Path | None:
    """Derive the analogue cache-dir for a draft from its first ref.

    Returns None if the draft has no usable ref, the slug is missing from
    the analogues map, or the mapped path doesn't exist on disk.
    """
    prov = draft.get("provenance") or {}
    ref = prov.get("ref")
    if ref is None:
        return None
    first = ref[0] if isinstance(ref, list) else ref
    if not isinstance(first, str) or "/" not in first:
        return None
    slug = first.split("/", 1)[0]
    path_str = analogues_map.get(slug)
    if path_str is None:
        return None
    p = Path(path_str)
    return p if p.exists() else None


def _truncate(text: str, limit: int = 200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _classify(
    gate_id: str,
    should_pass: dict,
    should_fail: dict,
) -> dict:
    """Map (should_pass, should_fail) adapter results to a validated.json entry."""
    sp_passed = should_pass["results"][0]["passed"]
    sf_passed = should_fail["results"][0]["passed"]

    if sp_passed and not sf_passed:
        return {"id": gate_id, "validated": "oracle", "warn": None,
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": False}}}
    if sp_passed and sf_passed:
        return {"id": gate_id, "validated": "smoke-only",
                "warn": "scaffold also passes; consider tightening",
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": True}}}
    # should-pass failed: classify as none with the stderr excerpt
    sp_stderr = should_pass["results"][0].get("stderr", "")
    sp_hint = should_pass["results"][0].get("hint", "")
    excerpt = _truncate(sp_stderr or sp_hint, 200)
    return {"id": gate_id, "validated": "none",
            "warn": f"should-pass failed: {excerpt}" if excerpt else "should-pass failed",
            "oracle_run": {"should_pass": {"passed": False}, "should_fail": None}}


def _oracle_one_gate(draft: dict, analogues_map: dict[str, str]) -> dict:
    """Run oracle for a single draft; return the validated.json entry."""
    gate_id = draft["id"]
    gate_type = draft.get("type")

    analogue_path = _resolve_analogue_path(draft, analogues_map)
    if analogue_path is None:
        return {"id": gate_id, "validated": "none",
                "warn": "no analogue on disk for this gate's ref",
                "oracle_run": None}

    # Adapter expects a criteria-shaped dict with a gates list
    one_gate_criteria = {"gates": [{k: v for k, v in draft.items()
                                    if k not in ("provenance", "rationale")}]}

    try:
        should_pass = run_gates(one_gate_criteria, analogue_path)
    except Exception as exc:
        return {"id": gate_id, "validated": "none",
                "warn": f"adapter internal error: {_truncate(str(exc))}",
                "oracle_run": None}

    try:
        with build_scaffold(gate_type, draft, analogue_path) as scaffold:
            should_fail = run_gates(one_gate_criteria, scaffold)
    except ValueError as exc:
        # unsupported gate type for scaffold
        return {"id": gate_id, "validated": "none",
                "warn": f"scaffold unavailable: {exc}",
                "oracle_run": None}
    except Exception as exc:
        return {"id": gate_id, "validated": "none",
                "warn": f"should-fail internal error: {_truncate(str(exc))}",
                "oracle_run": None}

    return _classify(gate_id, should_pass, should_fail)


def run_validate(sg: Path, skip: bool = False, stage_timeout_sec: int = 600) -> Path:
    """Run Stage 3 oracle validation. Returns the path to validated.json."""
    drafts_payload = load_json(synthesis_path(sg, "drafts.json"))
    drafts = drafts_payload.get("drafts", [])

    if skip:
        payload = _skip_payload(drafts)
    else:
        grounding = load_json(synthesis_path(sg, "grounding.json"))
        analogues_map = grounding.get("analogues", {})
        entries = [_oracle_one_gate(d, analogues_map) for d in drafts]
        payload = {"schema_version": 1, "gates": entries}

    out = synthesis_path(sg, "validated.json")
    save_json(out, payload)
    return out
```

- [ ] **Step 4.4: Run the tests to verify pass**

Run: `.venv/bin/pytest tests/test_validate.py -k "classify" -v`
Expected: 3 PASS.

- [ ] **Step 4.5: Run full validate test file**

Run: `.venv/bin/pytest tests/test_validate.py -v`
Expected: 4 PASS (skip test from Task 3 + 3 new).

- [ ] **Step 4.6: Commit**

```bash
git add scripts/synthesize/validate.py tests/test_validate.py
git commit -m "feat(validate): single-gate oracle runner with pass/fail/none classification"
```

---

### Task 5: Coverage-gate oracle semantics

**Context:** `type: coverage` gates need a different oracle: "did the tool produce a number?" not "did it exit 0?". The adapter's `_gate_coverage` returns `passed=False` if `percent < min_percent`, but it also returns a `stdout` of the form `"coverage: 93.8%"` on successful execution. Oracle should detect that prefix and treat it as "produced a number" regardless of `passed`.

Spec: a coverage gate is `validated: oracle` if should-pass produced a number AND should-fail did not.

**Files:**
- Modify: `scripts/synthesize/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 5.1: Add the failing tests**

Append to `tests/test_validate.py`:

```python
def test_coverage_oracle_pass_when_analogue_produced_number(tmp_path):
    drafts = [{"id": "cov", "type": "coverage", "min_percent": 100,
               "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    def _run_gates(criteria, project):
        if project == analogue:
            return {"passed": False,  # failed because 93.8 < 100
                    "results": [_gate_result(passed=False, stdout="coverage: 93.8%")]}
        return {"passed": False,
                "results": [_gate_result(passed=False,
                    hint="coverage report not generated — is pytest-cov installed?")]}

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "oracle"


def test_coverage_oracle_none_when_pytest_cov_unavailable(tmp_path):
    drafts = [{"id": "cov", "type": "coverage", "min_percent": 80,
               "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}}]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    def _run_gates(criteria, project):
        return {"passed": False,
                "results": [_gate_result(passed=False, stdout="",
                    hint="coverage report not generated — is pytest-cov installed?")]}

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates):
        out = run_validate(sg, skip=False)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "none"
    assert "coverage tooling not exerciseable" in payload["gates"][0]["warn"]
```

- [ ] **Step 5.2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_validate.py -k "coverage_oracle" -v`
Expected: FAIL — test 1 lands `validated: none` under current logic (should-pass's `passed=False` triggers the fail branch).

- [ ] **Step 5.3: Implement coverage special-case**

In `scripts/synthesize/validate.py`, modify `_classify` to branch on gate type. Find `_classify` and replace with:

```python
def _coverage_produced_number(adapter_result: dict) -> bool:
    """True iff the adapter's stdout includes a coverage percentage.

    measure_python._gate_coverage writes `coverage: <pct>%` to stdout on
    any successful run (even one that failed the min_percent threshold).
    The stdout stays empty when pytest-cov isn't installed / errors early.
    """
    stdout = adapter_result["results"][0].get("stdout") or ""
    return "coverage:" in stdout and "%" in stdout


def _classify_coverage(gate_id: str, should_pass: dict, should_fail: dict) -> dict:
    sp_produced = _coverage_produced_number(should_pass)
    sf_produced = _coverage_produced_number(should_fail)

    if sp_produced and not sf_produced:
        return {"id": gate_id, "validated": "oracle", "warn": None,
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": False}}}
    if sp_produced and sf_produced:
        return {"id": gate_id, "validated": "smoke-only",
                "warn": "scaffold also produced coverage; scaffold may be leaking code",
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": True}}}
    # should-pass produced no number → coverage tooling not exerciseable
    return {"id": gate_id, "validated": "none",
            "warn": "coverage tooling not exerciseable on analogue",
            "oracle_run": {"should_pass": {"passed": False}, "should_fail": None}}


def _classify(
    gate_id: str,
    gate_type: str,
    should_pass: dict,
    should_fail: dict,
) -> dict:
    """Map (should_pass, should_fail) adapter results to a validated.json entry."""
    if gate_type == "coverage":
        return _classify_coverage(gate_id, should_pass, should_fail)

    sp_passed = should_pass["results"][0]["passed"]
    sf_passed = should_fail["results"][0]["passed"]

    if sp_passed and not sf_passed:
        return {"id": gate_id, "validated": "oracle", "warn": None,
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": False}}}
    if sp_passed and sf_passed:
        return {"id": gate_id, "validated": "smoke-only",
                "warn": "scaffold also passes; consider tightening",
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": True}}}
    sp_stderr = should_pass["results"][0].get("stderr", "")
    sp_hint = should_pass["results"][0].get("hint", "")
    excerpt = _truncate(sp_stderr or sp_hint, 200)
    return {"id": gate_id, "validated": "none",
            "warn": f"should-pass failed: {excerpt}" if excerpt else "should-pass failed",
            "oracle_run": {"should_pass": {"passed": False}, "should_fail": None}}
```

Update the single caller in `_oracle_one_gate` to pass `gate_type`:

```python
    return _classify(gate_id, gate_type, should_pass, should_fail)
```

- [ ] **Step 5.4: Run to verify**

Run: `.venv/bin/pytest tests/test_validate.py -k "coverage_oracle" -v`
Expected: 2 PASS.

- [ ] **Step 5.5: Regression check**

Run: `.venv/bin/pytest tests/test_validate.py -v`
Expected: 6 PASS (4 prior + 2 new).

- [ ] **Step 5.6: Commit**

```bash
git add scripts/synthesize/validate.py tests/test_validate.py
git commit -m "feat(validate): coverage oracle = 'produced a coverage number' not exit-0"
```

---

### Task 6: Stage-timeout cap

**Context:** Total Stage 3 wall-clock can't exceed `stage_timeout_sec` (default 600). When the budget is exhausted, remaining drafts get `validated: none, warn: Stage 3 stage-timeout exceeded` without attempting their oracle runs.

**Files:**
- Modify: `scripts/synthesize/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 6.1: Write the failing test**

Append to `tests/test_validate.py`:

```python
def test_stage_timeout_short_circuits_remaining_gates(tmp_path):
    drafts = [
        {"id": "g1", "type": "pytest", "args": ["tests"],
         "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}},
        {"id": "g2", "type": "pytest", "args": ["tests"],
         "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}},
        {"id": "g3", "type": "pytest", "args": ["tests"],
         "provenance": {"source": "analogue", "ref": "demo/pyproject.toml"}},
    ]
    analogue = tmp_path / "demo"
    analogue.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(analogue)})

    call_count = {"n": 0}

    def _run_gates(criteria, project):
        call_count["n"] += 1
        return {"passed": True,
                "results": [_gate_result(passed=True)]}

    # Patch monotonic so the second gate's invocation sees the budget exceeded
    times = iter([0.0, 1.0, 700.0, 700.0, 700.0, 700.0])

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates), \
         mock.patch("scripts.synthesize.validate.monotonic",
                    side_effect=lambda: next(times)):
        out = run_validate(sg, skip=False, stage_timeout_sec=600)

    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] != "none"
    assert payload["gates"][1]["validated"] == "none"
    assert "stage-timeout exceeded" in payload["gates"][1]["warn"]
    assert payload["gates"][2]["validated"] == "none"
    assert "stage-timeout exceeded" in payload["gates"][2]["warn"]
```

- [ ] **Step 6.2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_validate.py::test_stage_timeout_short_circuits_remaining_gates -v`
Expected: FAIL — second and third gates also run.

- [ ] **Step 6.3: Implement timeout accumulation**

In `scripts/synthesize/validate.py`:

Add at the top:

```python
from time import monotonic
```

Replace the non-skip branch of `run_validate` with a loop that checks the budget:

```python
def run_validate(sg: Path, skip: bool = False, stage_timeout_sec: int = 600) -> Path:
    """Run Stage 3 oracle validation. Returns the path to validated.json."""
    drafts_payload = load_json(synthesis_path(sg, "drafts.json"))
    drafts = drafts_payload.get("drafts", [])

    if skip:
        payload = _skip_payload(drafts)
    else:
        grounding = load_json(synthesis_path(sg, "grounding.json"))
        analogues_map = grounding.get("analogues", {})

        entries: list[dict] = []
        start = monotonic()
        for draft in drafts:
            if monotonic() - start >= stage_timeout_sec:
                entries.append({
                    "id": draft["id"], "validated": "none",
                    "warn": "Stage 3 stage-timeout exceeded",
                    "oracle_run": None,
                })
                continue
            entries.append(_oracle_one_gate(draft, analogues_map))

        payload = {"schema_version": 1, "gates": entries}

    out = synthesis_path(sg, "validated.json")
    save_json(out, payload)
    return out
```

- [ ] **Step 6.4: Run the test**

Run: `.venv/bin/pytest tests/test_validate.py::test_stage_timeout_short_circuits_remaining_gates -v`
Expected: PASS.

- [ ] **Step 6.5: Commit**

```bash
git add scripts/synthesize/validate.py tests/test_validate.py
git commit -m "feat(validate): stage-wide timeout short-circuits remaining gates"
```

---

### Task 7: Missing-analogue failure surface

**Context:** If a draft cites a slug not in the analogues map — or the mapped path has been deleted — oracle can't run. The `_oracle_one_gate` helper already handles this internally (returns `validated: none` with a short warn). This task adds an end-to-end check that `--validate-only` surfaces the right error when grounding.json is missing entirely, and tightens the per-gate warn text.

**Files:**
- Modify: `scripts/synthesize/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 7.1: Add failing tests**

Append to `tests/test_validate.py`:

```python
def test_missing_grounding_json_errors_clearly(tmp_path):
    sg = tmp_path / ".skillgoid"
    synthesis = sg / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / "drafts.json").write_text(json.dumps({"drafts": [
        {"id": "g", "type": "pytest", "args": ["tests"],
         "provenance": {"source": "analogue", "ref": "demo/x"}}
    ]}))
    # NOTE: no grounding.json

    with pytest.raises(FileNotFoundError, match="grounding.json"):
        run_validate(sg, skip=False)


def test_unknown_slug_warns_clearly(tmp_path):
    drafts = [{"id": "g", "type": "pytest", "args": ["tests"],
               "provenance": {"source": "analogue", "ref": "other/pyproject.toml"}}]
    sg = _make_sg(tmp_path, drafts, analogues={"demo": str(tmp_path)})

    out = run_validate(sg, skip=False)
    payload = json.loads(out.read_text())
    assert payload["gates"][0]["validated"] == "none"
    assert "analogue slug 'other' not in grounding.json" in payload["gates"][0]["warn"]


def test_multi_ref_first_slug_is_picked(tmp_path):
    drafts = [{"id": "cov", "type": "coverage", "min_percent": 90,
               "provenance": {"source": "analogue", "ref": [
                   "primary/pyproject.toml", "secondary/ci.yml"]}}]
    primary = tmp_path / "primary"
    primary.mkdir()
    sg = _make_sg(tmp_path, drafts, analogues={
        "primary": str(primary), "secondary": str(tmp_path / "secondary")})

    captured = {"project": None}

    def _run_gates(criteria, project):
        if captured["project"] is None:
            captured["project"] = project
        return {"passed": True, "results": [_gate_result(
            passed=True, stdout="coverage: 95.0%")]}

    with mock.patch("scripts.synthesize.validate.run_gates", _run_gates):
        run_validate(sg, skip=False)

    assert captured["project"] == primary
```

- [ ] **Step 7.2: Run to verify failures**

Run: `.venv/bin/pytest tests/test_validate.py -k "missing_grounding or unknown_slug or multi_ref" -v`
Expected: failures.

- [ ] **Step 7.3: Implement**

In `scripts/synthesize/validate.py`, update `_resolve_analogue_path` to distinguish the unknown-slug case from the valid-but-missing case. Replace it:

```python
def _resolve_analogue_path(
    draft: dict, analogues_map: dict[str, str]
) -> tuple[Path | None, str | None]:
    """Return (path, None) on success or (None, warn_text) on failure."""
    prov = draft.get("provenance") or {}
    ref = prov.get("ref")
    if ref is None:
        return None, "draft has no provenance.ref"
    first = ref[0] if isinstance(ref, list) else ref
    if not isinstance(first, str) or "/" not in first:
        return None, f"provenance.ref has no slug-prefix: {first!r}"
    slug = first.split("/", 1)[0]
    path_str = analogues_map.get(slug)
    if path_str is None:
        return None, f"analogue slug '{slug}' not in grounding.json"
    p = Path(path_str)
    if not p.exists():
        return None, f"analogue path missing on disk: {p}"
    return p, None
```

Update the caller in `_oracle_one_gate`:

```python
    analogue_path, resolve_warn = _resolve_analogue_path(draft, analogues_map)
    if analogue_path is None:
        return {"id": gate_id, "validated": "none",
                "warn": resolve_warn,
                "oracle_run": None}
```

The `run_validate` non-skip branch already calls `load_json(synthesis_path(sg, "grounding.json"))`, which raises `FileNotFoundError` naturally — that satisfies `test_missing_grounding_json_errors_clearly`. Add a wrapping message so the error text mentions `grounding.json` explicitly (it already will from the path string).

- [ ] **Step 7.4: Run tests**

Run: `.venv/bin/pytest tests/test_validate.py -v`
Expected: 10 PASS (6 prior + 4 new including the timeout test).

Wait — Task 6 added one test (`test_stage_timeout_short_circuits_remaining_gates`), and Task 7 adds three. Let me recount: Task 3 has 1, Task 4 has 3, Task 5 has 2, Task 6 has 1, Task 7 has 3. Total 10.

- [ ] **Step 7.5: Commit**

```bash
git add scripts/synthesize/validate.py tests/test_validate.py
git commit -m "feat(validate): precise warn text for missing slug / path; pick first multi-ref slug"
```

---

## Phase D — Write rendering

### Task 8: Render validated/warn comments in criteria.yaml.proposed

**Context:** `write_criteria.py` currently emits the fixed Phase 1 label for every gate. Replace with per-gate labels read from `validated.json`. If `validated.json` doesn't exist (skipped run, legacy pre-v0.11 state), fall back to emitting `validated: none` for every gate.

**Files:**
- Modify: `scripts/synthesize/write_criteria.py`
- Modify: `tests/test_write_criteria.py`

- [ ] **Step 8.1: Write the failing tests**

Append to `tests/test_write_criteria.py` (if it doesn't exist, create it with the imports; this task assumes it exists from Phase 1 — check by running `ls tests/test_write_criteria.py`):

```python
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
    assert "# warn:" not in text  # no warn line when warn is None


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
```

- [ ] **Step 8.2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_write_criteria.py -k "validated or warn" -v`
Expected: FAIL — emitter still uses fixed Phase 1 label.

- [ ] **Step 8.3: Modify write_criteria.py**

In `scripts/synthesize/write_criteria.py`:

- Remove the module-level `PHASE1_VALIDATION_LABEL` constant.
- Extend `_gate_comment_block` to accept a `validated_entry: dict | None`:

```python
def _gate_comment_block(draft: dict, validated_entry: dict | None) -> str:
    """Build the comment lines that precede a gate in the rendered YAML."""
    prov = draft.get("provenance") or {}
    source = prov.get("source", "unknown")
    ref = prov.get("ref", "unknown")
    lines: list[str] = []
    if isinstance(ref, list):
        lines.append(f"  # source: {source}, refs:")
        for r in ref:
            lines.append(f"  #   - {r}")
    else:
        lines.append(f"  # source: {source}, ref: {ref}")

    if validated_entry is None:
        label = "none"
        warn = "validation artifact missing"
    else:
        label = validated_entry.get("validated", "none")
        warn = validated_entry.get("warn")
    lines.append(f"  # validated: {label}")
    if warn:
        lines.append(f"  # warn: {warn}")

    rationale = draft.get("rationale")
    if rationale:
        lines.append(f"  # rationale: {rationale}")
    return "\n".join(lines)
```

- Extend `render_criteria_yaml` to accept an optional `validated_payload`:

```python
def render_criteria_yaml(
    drafts_payload: dict,
    language: str,
    validated_payload: dict | None = None,
) -> str:
    """Render drafts to a criteria.yaml string with provenance comments."""
    drafts = drafts_payload.get("drafts", [])
    today = dt.date.today().isoformat()

    validated_by_id: dict[str, dict] = {}
    if validated_payload:
        for entry in validated_payload.get("gates", []):
            validated_by_id[entry["id"]] = entry

    header_lines = [
        f"# Skillgoid criteria — synthesized {today} from:",
    ]
    sources_seen = sorted({(d.get("provenance") or {}).get("source", "unknown") for d in drafts})
    for src in sources_seen:
        for d in drafts:
            if (d.get("provenance") or {}).get("source") == src:
                ref = (d.get("provenance") or {}).get("ref", "unknown")
                if isinstance(ref, list):
                    ref = ref[0]
                header_lines.append(f"#   {src}: {ref}")
                break
    header_lines.append("# Review each gate below. Delete or edit as needed before running build.")
    header_lines.append("# A `validated: oracle` label means the gate discriminated the analogue from an empty scaffold; it is not proof of correctness.")
    header_lines.append("")

    out_lines: list[str] = list(header_lines)
    out_lines.append(f"language: {language}")
    if drafts:
        out_lines.append("gates:")
        for draft in drafts:
            entry = validated_by_id.get(draft["id"])
            out_lines.append(_gate_comment_block(draft, entry))
            gate_dict = _gate_to_schema_dict(draft)
            gate_yaml = yaml.safe_dump(
                [gate_dict], sort_keys=False, default_flow_style=False, indent=2,
            )
            for line in gate_yaml.splitlines():
                out_lines.append(f"  {line}")
    else:
        out_lines.append("gates: []")
    return "\n".join(out_lines) + "\n"
```

- Update `run_write_criteria` to load `validated.json` when present:

```python
def run_write_criteria(sg: Path) -> Path:
    """Load drafts.json + grounding.json + (optional) validated.json, write criteria.yaml.proposed."""
    drafts_payload = load_json(synthesis_path(sg, "drafts.json"))
    try:
        grounding = load_json(synthesis_path(sg, "grounding.json"))
        language = grounding.get("language_detected", "unknown")
    except FileNotFoundError:
        sys.stderr.write("write_criteria: grounding.json missing, defaulting language=unknown\n")
        language = "unknown"

    try:
        validated_payload = load_json(synthesis_path(sg, "validated.json"))
    except FileNotFoundError:
        validated_payload = None

    rendered = render_criteria_yaml(drafts_payload, language=language,
                                    validated_payload=validated_payload)
    out_path = sg / "criteria.yaml.proposed"
    out_path.write_text(rendered)
    return out_path
```

- [ ] **Step 8.4: Run the tests**

Run: `.venv/bin/pytest tests/test_write_criteria.py -v`
Expected: all PASS (existing tests + 3 new).

- [ ] **Step 8.5: Regression: full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 8.6: Commit**

```bash
git add scripts/synthesize/write_criteria.py tests/test_write_criteria.py
git commit -m "feat(write): render per-gate validated/warn from validated.json"
```

---

## Phase E — SKILL.md orchestration

### Task 9: Add Stage 3 to SKILL.md with flag forwarding

**Context:** `skills/synthesize-gates/SKILL.md` today jumps from Stage 2 (synthesize) directly to Stage 4 (write). Insert Stage 3. Plumb through `--skip-validation` and `--validate-only`. Update Phase 2 limitations block.

**Files:**
- Modify: `skills/synthesize-gates/SKILL.md`

This task has no test code — SKILL.md is prose consumed by an agent. The validation is that the file reads correctly and mentions the right scripts / flags. We still do it TDD-style by grepping.

- [ ] **Step 9.1: Add a grep-based sanity test**

Append to `tests/test_synthesize_gates_skill.py` (create if missing):

```python
"""Sanity assertions over skills/synthesize-gates/SKILL.md content."""
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "synthesize-gates" / "SKILL.md"


def test_skill_references_stage_3_validate_script():
    text = SKILL.read_text()
    assert "scripts/synthesize/validate.py" in text


def test_skill_documents_skip_validation_flag():
    text = SKILL.read_text()
    assert "--skip-validation" in text


def test_skill_documents_validate_only_flag():
    text = SKILL.read_text()
    assert "--validate-only" in text


def test_skill_phase2_limitations_reflect_v011_oracle():
    text = SKILL.read_text()
    # Phase 1/2 limitations block should mention oracle now exists in v0.11
    assert "v0.11" in text or "oracle validates" in text
```

- [ ] **Step 9.2: Run to verify failures**

Run: `.venv/bin/pytest tests/test_synthesize_gates_skill.py -v`
Expected: all FAIL.

- [ ] **Step 9.3: Edit SKILL.md procedure section**

In `skills/synthesize-gates/SKILL.md`, find step 6 ("Run Stage 2") and step 7 ("Run Stage 4"). Renumber step 7 → step 8, then insert a new step 7:

```markdown
7. **Run Stage 3 (validate).** Shell out:
   ```bash
   python <plugin-root>/scripts/synthesize/validate.py \
     --skillgoid-dir .skillgoid
   ```
   Forward `--skip-validation` from the invocation if the user passed it. On non-zero exit, surface stderr and STOP. On zero exit, `.skillgoid/synthesis/validated.json` exists and labels each gate `oracle | smoke-only | none` with optional warn text.

   **For `--validate-only` invocations:** skip steps 3–6. Verify `.skillgoid/synthesis/grounding.json` and `.skillgoid/synthesis/drafts.json` both exist; if either is missing, error: `"--validate-only requires a prior full synthesis run. Re-run /skillgoid:synthesize-gates <analogues> first."` Then jump directly to this step, then step 8.
```

Also update the "Inputs" section — add a bullet near the top:

```markdown
**Flags:**

- `--skip-validation` — bypass oracle (Stage 3). Every gate lands `validated: none, warn: validation skipped by --skip-validation`.
- `--validate-only` — skip Stages 1, 2. Re-run Stage 3 + Stage 4 against the existing `drafts.json`. Use after installing analogue deps to refresh validation without re-synthesizing.
```

Update Phase 1 limitations block — replace the entire block with:

```markdown
## Phase 1 / 2 progress

- **v0.11 (current)**: Oracle validates analogue-cited gates. Every rendered gate carries a `validated: oracle | smoke-only | none` label derived from running the adapter against the analogue's cache-dir and an empty scaffold.
- **Remaining Phase 2 work (v0.13/v0.14)**: context7 grounding; curated template fallback for cold-start projects; oracle for context7/template-sourced gates; subagent auto-retry on Stage 2 validation failure.
```

Update the Risks section — append:

```markdown
- `validated: oracle` means the gate *discriminated* the analogue from an empty scaffold. That's a strong signal but not a proof of correctness. Users reviewing the criteria should still sanity-check each gate against their project's actual expectations.
- Oracle runs the adapter in the user's current Python environment. If the analogue's test deps aren't importable, gates land `validated: none` with a warn line; install the analogue's deps (`pip install -e ~/.cache/skillgoid/analogues/<slug>[dev]`) and re-run with `--validate-only`.
```

- [ ] **Step 9.4: Run tests**

Run: `.venv/bin/pytest tests/test_synthesize_gates_skill.py -v`
Expected: 4 PASS.

- [ ] **Step 9.5: Commit**

```bash
git add skills/synthesize-gates/SKILL.md tests/test_synthesize_gates_skill.py
git commit -m "docs(synthesize-gates): add Stage 3 orchestration and flag plumbing"
```

---

## Phase F — Integration test and ship

### Task 10: Extend e2e test to cover oracle labels

**Context:** `test_synthesize_e2e.py::test_e2e_canonical_coverage_gate` built by Task 14 of v0.10 asserts the canonical coverage gate shape end-to-end. Extend it so it exercises Stage 3 and asserts a `# validated:` line appears in the rendered output. The exact label is env-dependent (whether pytest-cov is importable), so we assert presence of the line, not a specific label value. Also add a new e2e that asserts `--skip-validation` emits uniform `none + warn: validation skipped`.

**Files:**
- Modify: `tests/test_synthesize_e2e.py`

- [ ] **Step 10.1: Extend the canonical-coverage test**

Find `test_e2e_canonical_coverage_gate` in `tests/test_synthesize_e2e.py`. After the existing `run_synthesize(sg, subagent_output)` line and before the `run_write_criteria(sg)` call, insert:

```python
    # Stage 3: validate
    from scripts.synthesize.validate import run_validate
    run_validate(sg, skip=False)
```

Also update the final assertions block — append:

```python
    # Oracle label is present (exact label depends on env: pytest-cov availability)
    assert "# validated: " in text
    first_validated_line = next(
        line for line in text.splitlines() if line.strip().startswith("# validated:")
    )
    label = first_validated_line.split(":", 1)[1].strip()
    assert label in ("oracle", "smoke-only", "none")
```

- [ ] **Step 10.2: Add a new --skip-validation e2e test**

Append a new function to `tests/test_synthesize_e2e.py`:

```python
def test_e2e_skip_validation_labels_all_gates_none(tmp_path):
    """With --skip-validation the rendered YAML labels every gate 'none'
    and carries the 'validation skipped' warn line.
    """
    import json as _json
    from scripts.synthesize.ground import run_ground
    from scripts.synthesize.synthesize import run_synthesize
    from scripts.synthesize.validate import run_validate
    from scripts.synthesize.write_criteria import run_write_criteria

    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "goal.md").write_text("Mini flask demo.\n")

    fixture = Path(__file__).resolve().parents[0] / "fixtures" / "synthesize" / "mini-flask-demo"
    run_ground(sg, [fixture])

    subagent_output = _json.dumps({"drafts": [
        {"id": "ruff_check", "type": "ruff", "args": ["check", "."],
         "provenance": {"source": "analogue", "ref": "mini-flask-demo/pyproject.toml"},
         "rationale": "lint"},
    ]})
    run_synthesize(sg, subagent_output)

    run_validate(sg, skip=True)

    out = run_write_criteria(sg)
    text = out.read_text()
    assert "# validated: none" in text
    assert "# warn: validation skipped by --skip-validation" in text
```

- [ ] **Step 10.3: Run the e2e tests**

Run: `.venv/bin/pytest tests/test_synthesize_e2e.py -v`
Expected: all PASS (existing 3 + 1 new = 4).

- [ ] **Step 10.4: Commit**

```bash
git add tests/test_synthesize_e2e.py
git commit -m "test(e2e): assert # validated: line on oracle and --skip-validation paths"
```

---

### Task 11: SKILL.md / CHANGELOG / plugin.json version bump

**Context:** Final release tasks. Bumps the plugin version, records the change, and leaves main ready for a `v0.11.0` tag.

**Files:**
- Modify: `.claude-plugin/plugin.json` — version 0.10.0 → 0.11.0.
- Modify: `CHANGELOG.md` — add 0.11.0 entry at top (under the preamble).
- Verify: `skills/synthesize-gates/SKILL.md` — Phase 1/2 block (done in Task 9).

- [ ] **Step 11.1: Bump plugin.json**

Edit `.claude-plugin/plugin.json`. Change:

```
  "version": "0.10.0",
```

to:

```
  "version": "0.11.0",
```

- [ ] **Step 11.2: Add CHANGELOG entry**

In `CHANGELOG.md`, insert the following block immediately below the preamble (above the `## 0.10.0 (2026-04-19)` entry):

```markdown
## 0.11.0 (2026-04-19)

### Features

- `synthesize-gates` Stage 3: oracle validation. Every gate in `criteria.yaml.proposed` now carries a `# validated: oracle | smoke-only | none` label derived from running the adapter against the analogue's cache-dir and a type-driven empty scaffold. Failures carry a `# warn:` line explaining the cause.
- `--skip-validation` flag — bypass Stage 3 and render every gate with `validated: none, warn: validation skipped`.
- `--validate-only` flag — skip Stages 1–2; re-run Stage 3 + Stage 4 against the existing `drafts.json`. Supports iteration after installing analogue deps.
- `grounding.json` gains an `analogues: {slug -> absolute_path}` map consumed by Stage 3 to resolve refs to on-disk checkouts.
- Per-gate-type should-fail scaffolds (`scripts/synthesize/_scaffold.py`): pytest, ruff, mypy, coverage, cli-command-runs, run-command, import-clean.

### Notes

- `validated: oracle` means the gate discriminated the analogue from an empty scaffold — it's a strong signal, not proof of correctness. Review each gate against your own expectations.
- Oracle runs use the user's active Python environment. Missing analogue deps → `validated: none` with a warn line; install them and re-run with `--validate-only`.
- No breaking changes.
```

- [ ] **Step 11.3: Run the full suite one final time**

Run: `.venv/bin/pytest -q`
Expected: all pass.

Run: `.venv/bin/ruff check .`
Expected: no violations.

- [ ] **Step 11.4: Commit**

```bash
git add .claude-plugin/plugin.json CHANGELOG.md
git commit -m "chore(release): v0.11.0 — oracle validation for synthesized gates"
```

---

## Self-review checklist (for the plan author, done now)

1. **Spec coverage:**
   - Spec D1 (adapter reuse) → Task 4 imports `measure_python.run_gates` directly; no separate runner.
   - Spec D2 (don't auto-install) → Task 4 classification table's "should-pass failed" row surfaces deps errors as warn text; no install logic is introduced anywhere.
   - Spec D3 (coverage oracle = "produced a number") → Task 5 `_classify_coverage`.
   - Spec D4 (should-fail scaffold composition) → Task 2 `_scaffold.py` encodes the full table.
   - Spec D5 (first ref wins) → Task 7 `_resolve_analogue_path` splits on `/` on the first ref entry; Task 7 test asserts against the first ref's slug.
   - Spec D6 (`--skip-validation` + `--validate-only`) → `--skip-validation` lands as a validate.py flag in Task 3; `--validate-only` is the SKILL.md-level orchestration in Task 9.
   - Classification table (the six rows) → Tasks 4, 5, 6, 7 cover pass/fail, pass/pass, fail, timeout, adapter-internal, missing-analogue.
   - validated.json shape → Task 3, Task 4.
   - write_criteria render block → Task 8.
   - SKILL.md Stage 3 + flags + limitations → Task 9.
   - File structure (validate.py, _scaffold.py) → Tasks 2, 3.
   - Testing: test_scaffold.py → Task 2, test_validate.py → Tasks 3–7, e2e → Task 10, write_criteria rendering → Task 8.
   - Backward compatibility for missing validated.json → Task 8.
   - Plugin version + CHANGELOG → Task 11.
   - Success criteria items 1–6 → Tasks 8 + 10 + 11 all contribute.

2. **Placeholder scan:** No TBDs, TODOs, vague `add error handling`, or "similar to Task N". Every code step shows complete code.

3. **Type consistency:**
   - `_oracle_one_gate(draft, analogues_map) -> dict` — used consistently in Tasks 4, 6, 7.
   - `_classify(gate_id, gate_type, should_pass, should_fail)` — Task 5 updates the signature from Task 4; Task 5 explicitly shows the update to `_oracle_one_gate`'s caller.
   - `_resolve_analogue_path(draft, analogues_map) -> tuple[Path | None, str | None]` — Task 7 shows the signature change from Task 4's version; Task 7 updates the caller.
   - `run_validate(sg, skip=False, stage_timeout_sec=600) -> Path` — signature stable across Tasks 3–7.
   - `build_scaffold(gate_type, gate, analogue_cache_dir) -> Iterator[Path]` — used in Task 4's `_oracle_one_gate` with positional args matching Task 2's definition.
   - `render_criteria_yaml(drafts_payload, language, validated_payload=None)` — Task 8 preserves the existing positional signature and adds an optional third arg.

All checks pass. Plan is ready for execution.
