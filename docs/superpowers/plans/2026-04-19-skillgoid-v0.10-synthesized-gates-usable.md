# Skillgoid v0.10 — Synthesized Gates That Actually Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `synthesize-gates` produce drafts that `/skillgoid:build` can consume without hand-editing — tighten `type: coverage` to a declarative shape, move analogue clones out of the project tree, and collapse duplicate coverage drafts.

**Architecture:** Three parallel-ish concerns inside the existing 4-stage synthesis pipeline (`ground → synthesize → write`): schema+validator tightening for `type: coverage` (Stage 2/schema), `coverage_threshold` observation extraction (Stage 1a), and cache-dir migration for analogue clones (Stage 1 orchestrator). No new stages, no new skills.

**Tech Stack:** Python 3.11+, `tomllib`, PyYAML, pytest, `jsonschema`. All changes confined to `scripts/synthesize/*`, `schemas/criteria.schema.json`, `skills/synthesize-gates/*`, and `tests/`.

---

## Spec Reference

Full spec: `docs/superpowers/specs/2026-04-19-skillgoid-v0.10-synthesized-gates-usable.md`. Do not duplicate the spec in each task — follow it.

## File Structure

**Modified:**
- `schemas/criteria.schema.json` — add `oneOf` branch for `type: coverage`, reject args, require `min_percent`. Mirror in `integration_gates`.
- `scripts/synthesize/synthesize.py` — new coverage-shape validator in `parse_subagent_output`, post-validation collapse pass, widened `provenance.ref` handling.
- `scripts/synthesize/ground_analogue.py` — new `coverage_threshold` observation source from `[tool.coverage.report].fail_under` and from `--fail-under=N` tokens in CI commands.
- `scripts/synthesize/ground.py` — `_cache_dir()` helper, URL detection + shallow-clone, one-time migration from `<sg>/synthesis/analogues/` to cache dir. Accepts both URLs and local paths as analogue args.
- `scripts/synthesize/write_criteria.py` — multi-ref comment block rendering (single ref: current shape; list: `refs:\n#   - <r>` block).
- `skills/synthesize-gates/prompts/synthesize.md` — canonical `type: coverage` shape teaching; `type: run-command` escape hatch note.
- `skills/synthesize-gates/SKILL.md` — Procedure step 2 delegates URL cloning to `ground.py`; Phase 1.5 limitations block updated; add coverage-shape note to Risks.
- `tests/test_ground_analogue.py` — threshold-from-pyproject, threshold-from-CI, dedup-preserves-both-values.
- `tests/test_ground.py` — cache-dir resolution, XDG override, unwritable fallback, migration (empty cache-dir, both-exist conflict).
- `tests/test_synthesize.py` — coverage with args rejected, coverage without min_percent rejected, min_percent out-of-range rejected, duplicate collapse, widened provenance.ref.
- `tests/test_write_criteria.py` — multi-ref rendering.
- `tests/test_synthesize_e2e.py` — end-to-end assertions for canonical coverage gate.
- `tests/fixtures/synthesize/mini-flask-demo/pyproject.toml` — add `[tool.coverage.report] fail_under = 100`.
- `tests/fixtures/synthesize/mini-flask-demo/.github/workflows/test.yml` — add `coverage report --fail-under=95` step.
- `.claude-plugin/plugin.json` — version bump 0.9.0 → 0.10.0.

**New:** none. All changes are additive to existing files.

## Conventions for all tasks

- **TDD:** test before implementation in every task. Write the test, watch it fail with the expected message, then implement, then watch it pass.
- **Project root:** all `pytest` commands run from `skillgoid-plugin/` (the plugin manifest parent). Absolute path on this machine: `/home/flip/Development/skillgoid/skillgoid-plugin/`.
- **Commit style:** Conventional-style prefix (`feat:`, `fix:`, `test:`, `chore:`). One commit per task unless a task's steps explicitly split.
- **Line length:** ruff `line-length = 100`, `T201` (no `print`) enabled — write to stderr via `sys.stderr.write(...)`.
- **No print.** Any CLI output goes through `sys.stdout.write` or `sys.stderr.write`.
- **Existing patterns to follow:** `Observation` dataclass for new observation type additions; `_PYPROJECT_TOOL_SPECS`-style declarative config for new pyproject extractions; `parse_subagent_output` raise-`DraftValidationError`-with-specific-message pattern for new validator rules.

---

## Phase A — `type: coverage` schema + validator tightening (F2)

### Task 1: Schema tightening for `type: coverage`

**Files:**
- Modify: `schemas/criteria.schema.json` — both `gates` items schema (lines ~17-39) and `integration_gates` items schema (~47-66).
- Test: `tests/test_criteria_schema.py` (verify if it exists; otherwise add assertions to `tests/test_synthesize.py` if schema parity is already tested there).

First check whether a schema test file exists.

- [ ] **Step 1.1: Locate or create the schema test file**

Run: `ls tests/test_criteria_schema.py 2>/dev/null && echo EXISTS || echo MISSING`
Expected: either EXISTS (skip to 1.2) or MISSING (create the file in 1.3).

- [ ] **Step 1.2: If the file exists, open it and read the existing assertions**

Read: `tests/test_criteria_schema.py`
Note its import style and fixture conventions. Append new tests in its style.

- [ ] **Step 1.3: Write the failing test — coverage gate with args is rejected**

Add to `tests/test_criteria_schema.py` (create the file if missing, with this imports block at the top):

```python
"""Tests for schemas/criteria.schema.json gate-type shape constraints."""
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "criteria.schema.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _validate(criteria: dict) -> None:
    jsonschema.validate(instance=criteria, schema=_load_schema())


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
```

- [ ] **Step 1.4: Run the failing test**

Run: `pytest tests/test_criteria_schema.py -v`
Expected: FAIL — current schema allows args on coverage and does not require min_percent; some assertions will not raise.

- [ ] **Step 1.5: Tighten the schema — gate items**

In `schemas/criteria.schema.json`, replace the `gates.items` object (currently `{"type": "object", "required": ["id", "type"], "properties": {...}, "additionalProperties": true}`) with a conditional shape using `allOf` + `if/then` so `type: coverage` gets the strict variant.

Target structure (applied to both `gates.items` and `integration_gates.items`):

```json
{
  "type": "object",
  "required": ["id", "type"],
  "properties": {
    "id": {"type": "string"},
    "type": {"type": "string", "enum": ["pytest", "ruff", "mypy", "import-clean", "cli-command-runs", "run-command", "coverage"]},
    "args": {"type": "array", "items": {"type": "string"}},
    "command": {"type": "array", "items": {"type": "string"}},
    "expect_exit": {"type": "integer"},
    "expect_stdout_match": {"type": "string"},
    "module": {"type": "string"},
    "timeout": {"type": "integer", "minimum": 1, "default": 300},
    "target": {"type": "string"},
    "min_percent": {"type": "integer", "minimum": 0, "maximum": 100, "default": 80},
    "compare_to_baseline": {"type": "boolean", "default": false},
    "env": {"type": "object", "additionalProperties": {"type": "string"}}
  },
  "additionalProperties": true,
  "allOf": [
    {
      "if": {"properties": {"type": {"const": "coverage"}}, "required": ["type"]},
      "then": {
        "required": ["id", "type", "min_percent"],
        "not": {"required": ["args"]}
      }
    }
  ]
}
```

Apply this shape to both `gates.items` and `integration_gates.items`. Preserve all other top-level properties (`language`, `loop`, `integration_retries`, `acceptance`, `models`) exactly as they are.

- [ ] **Step 1.6: Run the test — should now pass**

Run: `pytest tests/test_criteria_schema.py -v`
Expected: PASS — all five tests green.

- [ ] **Step 1.7: Run the broader suite to catch unexpected breakage**

Run: `pytest -q`
Expected: all green. If any existing fixture or test has a `type: coverage` gate with `args`, it will now fail validation — those fixtures need updating in later tasks. If unrelated tests break, stop and investigate.

- [ ] **Step 1.8: Commit**

```bash
git add schemas/criteria.schema.json tests/test_criteria_schema.py
git commit -m "feat(schema): tighten type: coverage to require min_percent and reject args"
```

---

### Task 2: Validator tightening for `type: coverage`

**Files:**
- Modify: `scripts/synthesize/synthesize.py` — extend `parse_subagent_output` with a per-draft `type: coverage` shape check.
- Test: `tests/test_synthesize.py` — add three tests in the same style as `test_parse_rejects_unsupported_type`.

- [ ] **Step 2.1: Write the failing tests**

Append to `tests/test_synthesize.py`:

```python
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
    with pytest.raises(DraftValidationError, match="coverage gate 'cov' must not have args"):
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
    with pytest.raises(DraftValidationError, match="coverage gate 'cov' must have min_percent"):
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
    with pytest.raises(DraftValidationError, match="min_percent must be 0-100"):
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
```

- [ ] **Step 2.2: Run the failing tests**

Run: `pytest tests/test_synthesize.py -k coverage -v`
Expected: 3 FAIL (reject tests — current parser does not enforce coverage shape), 1 PASS (accepts test).

- [ ] **Step 2.3: Implement the coverage-shape validator**

In `scripts/synthesize/synthesize.py`, inside `parse_subagent_output`, after the existing provenance-ref check (line ~104) and before the `return drafts`, add the coverage-shape block:

```python
        if gate_type == "coverage":
            args = draft.get("args")
            if args is not None and len(args) > 0:
                raise DraftValidationError(
                    f"coverage gate '{gate_id}' must not have args; "
                    f"use type: run-command for literal CLI usage"
                )
            min_percent = draft.get("min_percent")
            if min_percent is None:
                raise DraftValidationError(
                    f"coverage gate '{gate_id}' must have min_percent (int, 0-100)"
                )
            if not isinstance(min_percent, int) or min_percent < 0 or min_percent > 100:
                raise DraftValidationError(
                    f"coverage gate '{gate_id}' min_percent must be 0-100 "
                    f"(got {min_percent!r})"
                )
```

- [ ] **Step 2.4: Run the tests — all should pass now**

Run: `pytest tests/test_synthesize.py -v`
Expected: PASS (all coverage tests + the pre-existing suite).

- [ ] **Step 2.5: Commit**

```bash
git add scripts/synthesize/synthesize.py tests/test_synthesize.py
git commit -m "feat(synthesize): reject type: coverage drafts with args or bad min_percent"
```

---

## Phase B — `coverage_threshold` grounding (F2)

### Task 3: Extract `coverage_threshold` from `[tool.coverage.report].fail_under`

**Files:**
- Modify: `scripts/synthesize/ground_analogue.py` — extend observation extraction.
- Test: `tests/test_ground_analogue.py` — new assertions using a small tmp-path fixture.

Note on design: this observation type is **not** a gate. Its `command` field is not a real command — by convention, use `f"coverage_threshold={value}"` so downstream consumers (the subagent) can still see a printable representation, but `observed_type` is `"coverage_threshold"` which is distinct from the `"coverage"` gate-type. The subagent prompt (Task 5) teaches the subagent to use this value for `min_percent`.

- [ ] **Step 3.1: Write the failing test**

Append to `tests/test_ground_analogue.py`:

```python
def test_coverage_threshold_from_pyproject_fail_under(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage.report]\n"
        "fail_under = 95\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert len(thresholds) == 1
    t = thresholds[0]
    assert t.source == "analogue"
    assert t.ref.endswith("/pyproject.toml#tool.coverage.report")
    assert t.command == "coverage_threshold=95"
    assert t.context == "pyproject.toml [tool.coverage.report] declares fail_under"


def test_coverage_threshold_absent_when_fail_under_missing(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage.report]\n"
        "show_missing = true\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert thresholds == []


def test_coverage_threshold_non_int_is_skipped(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.coverage.report]\n'
        'fail_under = "ninety"\n'
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert thresholds == []
```

- [ ] **Step 3.2: Run the failing tests**

Run: `pytest tests/test_ground_analogue.py -k coverage_threshold -v`
Expected: 3 FAIL — no extraction exists yet.

- [ ] **Step 3.3: Implement pyproject `coverage_threshold` extraction**

In `scripts/synthesize/ground_analogue.py`, add a new helper below `parse_pyproject_tool_sections` (around line 132):

```python
def parse_pyproject_coverage_threshold(pyproject: Path) -> int | None:
    """Return fail_under int from [tool.coverage.report], or None if missing/invalid."""
    if not pyproject.exists():
        return None
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        return None
    try:
        data = tomllib.loads(pyproject.read_text())
    except tomllib.TOMLDecodeError:
        return None
    fail_under = (
        data.get("tool", {}).get("coverage", {}).get("report", {}).get("fail_under")
    )
    if isinstance(fail_under, int):
        return fail_under
    return None
```

Then in `extract_observations` (around line 269, after the `parse_pyproject_tool_sections` loop), insert:

```python
    # Source 1c: pyproject.toml [tool.coverage.report].fail_under
    threshold = parse_pyproject_coverage_threshold(repo / "pyproject.toml")
    if threshold is not None:
        observations.append(Observation(
            source="analogue",
            ref=f"{repo_name}/pyproject.toml#tool.coverage.report",
            command=f"coverage_threshold={threshold}",
            context="pyproject.toml [tool.coverage.report] declares fail_under",
            observed_type="coverage_threshold",
        ))
```

- [ ] **Step 3.4: Run the tests — should pass**

Run: `pytest tests/test_ground_analogue.py -k coverage_threshold -v`
Expected: all 3 PASS.

- [ ] **Step 3.5: Run full ground tests**

Run: `pytest tests/test_ground_analogue.py -v`
Expected: all PASS. Existing fixture `mini-flask-demo` has no `fail_under` yet (Task 13 adds it), so existing tests are unaffected.

- [ ] **Step 3.6: Commit**

```bash
git add scripts/synthesize/ground_analogue.py tests/test_ground_analogue.py
git commit -m "feat(ground): extract coverage_threshold from [tool.coverage.report].fail_under"
```

---

### Task 4: Extract `coverage_threshold` from CI commands (`--fail-under=N`)

**Files:**
- Modify: `scripts/synthesize/ground_analogue.py` — scan CI step commands and wrapper script commands for the `--fail-under=N` token.
- Test: `tests/test_ground_analogue.py` — new tests.

- [ ] **Step 4.1: Write the failing test**

Append to `tests/test_ground_analogue.py`:

```python
def test_coverage_threshold_from_workflow_fail_under(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "jobs:\n"
        "  t:\n"
        "    steps:\n"
        "      - run: coverage report --fail-under=85\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert len(thresholds) == 1
    t = thresholds[0]
    assert t.command == "coverage_threshold=85"
    assert t.ref.endswith("/.github/workflows/ci.yml")


def test_coverage_threshold_two_sources_emits_two_observations(tmp_path):
    # pyproject says 100, workflow says 95 — both recorded, subagent picks
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage.report]\n"
        "fail_under = 100\n"
    )
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "jobs:\n"
        "  t:\n"
        "    steps:\n"
        "      - run: coverage report --fail-under=95\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = sorted(
        (o for o in obs if o.observed_type == "coverage_threshold"),
        key=lambda o: o.command,
    )
    assert len(thresholds) == 2
    assert thresholds[0].command == "coverage_threshold=100"
    assert thresholds[1].command == "coverage_threshold=95"


def test_coverage_threshold_from_wrapper_script(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    wrapper = scripts_dir / "test"
    wrapper.write_text(
        "#!/bin/sh\n"
        "set -e\n"
        "pytest\n"
        "coverage report --fail-under=90\n"
    )
    wrapper.chmod(0o755)
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "jobs:\n"
        "  t:\n"
        "    steps:\n"
        "      - run: ./scripts/test\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert len(thresholds) == 1
    assert thresholds[0].command == "coverage_threshold=90"
```

- [ ] **Step 4.2: Run the failing tests**

Run: `pytest tests/test_ground_analogue.py -k coverage_threshold_from_workflow -v`
Expected: FAIL — no command-level extraction yet.

- [ ] **Step 4.3: Implement `--fail-under=N` extraction**

In `scripts/synthesize/ground_analogue.py`, add a constant at module level near `_PREFIX_SUB_RE` (around line 181):

```python
_FAIL_UNDER_RE = re.compile(r"--fail-under=(\d+)")
```

Add a small helper below `_classify_command`:

```python
def _extract_fail_under(cmd: str) -> int | None:
    """Return int N if the command contains --fail-under=N, else None."""
    match = _FAIL_UNDER_RE.search(cmd)
    if match:
        return int(match.group(1))
    return None
```

Modify `extract_observations` (the workflow-steps + wrapper-follow loop starting around line 275) so that every time we observe a command — either directly from a workflow step or from a followed wrapper — we also check `_extract_fail_under(cmd)` and, if non-None, emit a `coverage_threshold` observation alongside the existing gate-shaped observation. Use the same `ref` that the surrounding observation used.

Concretely, in both branches (`wrapper_cmds` loop and the `else` direct-step branch), right after appending the main observation, add:

```python
                        threshold = _extract_fail_under(inner)  # or step_cmd in else branch
                        if threshold is not None:
                            observations.append(Observation(
                                source="analogue",
                                ref=wrapper_ref,  # or wf_ref in else branch
                                command=f"coverage_threshold={threshold}",
                                context="CI step declares --fail-under",
                                observed_type="coverage_threshold",
                            ))
```

**Dedup consideration:** the existing dedup key is `(command, observed_type)`. Two `coverage_threshold` observations with different values (`coverage_threshold=100` vs `coverage_threshold=95`) differ on `command`, so the dedup key is unique and both are preserved — that's what the spec says to do. Re-verify this holds by running the "two sources" test in the next step.

- [ ] **Step 4.4: Run the tests — should pass**

Run: `pytest tests/test_ground_analogue.py -k coverage_threshold -v`
Expected: all coverage_threshold tests PASS (6 total across Tasks 3 and 4).

- [ ] **Step 4.5: Run the full suite**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 4.6: Commit**

```bash
git add scripts/synthesize/ground_analogue.py tests/test_ground_analogue.py
git commit -m "feat(ground): extract coverage_threshold from --fail-under=N in CI commands"
```

---

## Phase C — Subagent prompt (F2)

### Task 5: Teach canonical `type: coverage` shape

**Files:**
- Modify: `skills/synthesize-gates/prompts/synthesize.md`.

- [ ] **Step 5.1: Edit the prompt**

In `skills/synthesize-gates/prompts/synthesize.md`, after the "## Guidance" section (line ~65) and before "## Common pitfalls", add a new section:

```markdown
## Canonical shape for `type: coverage`

`type: coverage` is a **declarative threshold gate**, not a runbook step. The
ONLY CLI-shaped fields it may carry are `target` (optional) and `timeout`.
Specifically:

- **Required:** `min_percent` (integer, 0-100).
- **Forbidden:** `args`. The Stage 2 validator rejects any `type: coverage`
  draft with a non-empty `args`.
- **How to pick `min_percent`:**
  - If grounding contains an observation with `observed_type = "coverage_threshold"`,
    use its value (parse the integer from `coverage_threshold=<N>`). Cite its
    `ref` in `provenance.ref`.
  - If two `coverage_threshold` observations disagree (e.g., pyproject says 100,
    CI says 95), prefer the CI-script value — that's what's actually enforced.
  - If no `coverage_threshold` observation exists, default to `min_percent: 80`
    and write `"no threshold found in analogue, defaulting to 80"` in `rationale`.
    Cite the nearest coverage-related observation (e.g., a pyproject section
    declaring coverage configured) as `provenance.ref`.
- **Emit at most one `type: coverage` gate.** If the analogue runs coverage
  through multiple steps (e.g., `coverage run` then `coverage report`), that's
  one semantic — one gate.

If the analogue uses the `coverage` CLI in a way that isn't threshold enforcement
(e.g., `coverage combine`, `coverage erase`, custom post-processing), emit those
as separate `type: run-command` gates. Don't conflate literal CLI invocation with
threshold enforcement.
```

Also append one bullet to "## Common pitfalls":

```markdown
- Emitting `type: coverage` with `args: ["report", "--fail-under=100"]`. The Stage 2 validator rejects this. Use `min_percent: 100` instead (no `args`). If you actually need the literal CLI, emit a separate `type: run-command` gate.
```

- [ ] **Step 5.2: Verify no other file needs updating**

Run: `grep -rn "type: coverage" skills/`
Expected: only the prompt file and any SKILL.md references. Task 14 handles SKILL.md. Nothing to do here.

- [ ] **Step 5.3: Commit**

```bash
git add skills/synthesize-gates/prompts/synthesize.md
git commit -m "feat(prompt): teach canonical type: coverage shape and escape hatch"
```

---

## Phase D — Cache-dir + migration (F1)

### Task 6: `_cache_dir()` helper in ground.py

**Files:**
- Modify: `scripts/synthesize/ground.py` — add helper.
- Create/Modify: `tests/test_ground.py` — new test file for the orchestrator (check if it exists first).

- [ ] **Step 6.1: Check whether `test_ground.py` exists**

Run: `ls tests/test_ground.py 2>/dev/null && echo EXISTS || echo MISSING`
Expected: `EXISTS` (per summary). Read the top to match its style.

- [ ] **Step 6.2: Read existing tests to match style**

Read: `tests/test_ground.py` (first 60 lines)
Note the import block and tmp_path usage. Match that style below.

- [ ] **Step 6.3: Write the failing test**

Append to `tests/test_ground.py`:

```python
def test_cache_dir_uses_xdg_when_set(tmp_path, monkeypatch):
    from scripts.synthesize.ground import _cache_dir
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    result = _cache_dir()
    assert result == tmp_path / "skillgoid" / "analogues"
    assert result.is_dir()


def test_cache_dir_defaults_to_home_cache_when_xdg_unset(tmp_path, monkeypatch):
    from scripts.synthesize.ground import _cache_dir
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() is read from HOME on POSIX
    result = _cache_dir()
    assert result == tmp_path / ".cache" / "skillgoid" / "analogues"
    assert result.is_dir()


def test_cache_dir_falls_back_to_tmpdir_when_unwritable(tmp_path, monkeypatch, capsys):
    from scripts.synthesize import ground
    # Force XDG_CACHE_HOME to a path that cannot be created (a file, not a dir)
    blocker = tmp_path / "blocker"
    blocker.write_text("")  # it's a file, so making subdirs under it fails
    monkeypatch.setenv("XDG_CACHE_HOME", str(blocker))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    result = ground._cache_dir()
    assert result.is_dir()
    assert str(result).startswith(str(tmp_path / "tmp"))
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
```

- [ ] **Step 6.4: Run the failing test**

Run: `pytest tests/test_ground.py -k cache_dir -v`
Expected: FAIL with `ImportError` or `AttributeError` — `_cache_dir` does not exist yet.

- [ ] **Step 6.5: Implement `_cache_dir()` in ground.py**

At the top of `scripts/synthesize/ground.py`, add imports:

```python
import os
import tempfile
```

Add the helper below the imports, above `run_ground`:

```python
def _cache_dir() -> Path:
    """Return the user-global cache dir for analogue clones.

    Prefers $XDG_CACHE_HOME/skillgoid/analogues, falls back to
    ~/.cache/skillgoid/analogues. If both are unwritable, falls back to
    $TMPDIR/skillgoid-analogues and emits a stderr warning.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    target = base / "skillgoid" / "analogues"
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "skillgoid-analogues"
        fallback.mkdir(parents=True, exist_ok=True)
        sys.stderr.write(
            f"warning: cache dir {target} unwritable, using {fallback}\n"
        )
        return fallback
```

- [ ] **Step 6.6: Run the test**

Run: `pytest tests/test_ground.py -k cache_dir -v`
Expected: all 3 PASS.

- [ ] **Step 6.7: Commit**

```bash
git add scripts/synthesize/ground.py tests/test_ground.py
git commit -m "feat(ground): add _cache_dir() helper with XDG and tmpdir fallback"
```

---

### Task 7: Accept URL args and clone to cache-dir in ground.py

**Files:**
- Modify: `scripts/synthesize/ground.py` — detect URL vs path, clone URLs into `_cache_dir() / <slug>/`. Move responsibility for cloning from SKILL.md prose into the script.
- Test: `tests/test_ground.py` — new tests using local file:// URLs (easy to set up; equivalent to git URL detection branch).

Note on URL detection: accept strings that match `^(https?://|git@|ssh://|git://|file://)` as URLs. Paths are everything else. If an arg is a URL, clone it shallow (`git clone --depth=1`). If it's a path, use it as-is (no copy).

- [ ] **Step 7.1: Write the failing tests — URL detection**

Append to `tests/test_ground.py`:

```python
def test_is_url_detects_common_schemes():
    from scripts.synthesize.ground import _is_url
    assert _is_url("https://github.com/pallets/flask.git")
    assert _is_url("http://example.com/repo.git")
    assert _is_url("git@github.com:pallets/flask.git")
    assert _is_url("ssh://git@host/repo.git")
    assert _is_url("git://host/repo.git")
    assert _is_url("file:///tmp/repo")


def test_is_url_rejects_local_paths():
    from scripts.synthesize.ground import _is_url
    assert not _is_url("/home/user/repo")
    assert not _is_url("./repo")
    assert not _is_url("repo")
    assert not _is_url("../sibling/repo")


def test_slug_for_url_extracts_owner_repo():
    from scripts.synthesize.ground import _slug_for_url
    assert _slug_for_url("https://github.com/pallets/flask.git") == "pallets-flask"
    assert _slug_for_url("https://github.com/pallets/flask") == "pallets-flask"
    assert _slug_for_url("git@github.com:encode/httpx.git") == "encode-httpx"
    assert _slug_for_url("https://gitlab.com/group/sub/project.git") == "sub-project"
    assert _slug_for_url("file:///tmp/myrepo") == "myrepo"
```

- [ ] **Step 7.2: Run the failing tests**

Run: `pytest tests/test_ground.py -k "is_url or slug_for_url" -v`
Expected: FAIL — helpers don't exist.

- [ ] **Step 7.3: Implement URL detection + slug helpers**

In `scripts/synthesize/ground.py`, add near `_cache_dir`:

```python
import re

_URL_PREFIX_RE = re.compile(r"^(https?://|git@|ssh://|git://|file://)")
_SLUG_TAIL_RE = re.compile(r"([^/:]+)[/:]([^/:]+?)(?:\.git)?/?$")


def _is_url(arg: str) -> bool:
    """Return True if arg looks like a git URL, False if it's a local path."""
    return bool(_URL_PREFIX_RE.match(arg))


def _slug_for_url(url: str) -> str:
    """Derive a stable <owner>-<repo> slug from a git URL.

    For file:// URLs (no owner), returns the last path segment only.
    """
    if url.startswith("file://"):
        path = url[len("file://"):]
        name = Path(path).name
        return name.removesuffix(".git")
    match = _SLUG_TAIL_RE.search(url.rstrip("/"))
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return url.rsplit("/", 1)[-1].removesuffix(".git")
```

- [ ] **Step 7.4: Run the tests**

Run: `pytest tests/test_ground.py -k "is_url or slug_for_url" -v`
Expected: PASS.

- [ ] **Step 7.5: Write the failing clone test**

Append to `tests/test_ground.py`:

```python
def _make_bare_fixture_repo(tmp_path: Path) -> Path:
    """Create a bare git repo that can be cloned via file:// URL."""
    import subprocess
    src = tmp_path / "src-repo"
    src.mkdir()
    (src / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        "testpaths = ['tests']\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=src, check=True)
    subprocess.run(["git", "add", "."], cwd=src, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=src, check=True,
    )
    return src


def test_run_ground_clones_url_into_cache_dir(tmp_path, monkeypatch):
    from scripts.synthesize.ground import run_ground
    src_repo = _make_bare_fixture_repo(tmp_path)
    url = f"file://{src_repo}"
    # Point XDG_CACHE_HOME to a sandbox so the real ~/.cache isn't touched
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / "dest" / ".skillgoid"
    sg.mkdir(parents=True)
    run_ground(sg, [url])
    slug = "src-repo"  # from _slug_for_url of a file:// URL
    cloned = tmp_path / "cache" / "skillgoid" / "analogues" / slug
    assert (cloned / "pyproject.toml").exists()
    # And no project-local clone was created
    assert not (sg / "synthesis" / "analogues" / slug).exists()


def test_run_ground_accepts_local_path_without_copying(tmp_path, monkeypatch):
    from scripts.synthesize.ground import run_ground
    analogue = tmp_path / "analogue-repo"
    analogue.mkdir()
    (analogue / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        "testpaths = ['tests']\n"
    )
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / "proj" / ".skillgoid"
    sg.mkdir(parents=True)
    run_ground(sg, [analogue])
    # Local paths are NOT copied into the cache
    assert not (tmp_path / "cache" / "skillgoid" / "analogues").glob("analogue-repo")
    # grounding.json still reflects observations from the in-place path
    grounding = json.loads((sg / "synthesis" / "grounding.json").read_text())
    assert any(o["command"].startswith("pytest") for o in grounding["observations"])
```

- [ ] **Step 7.6: Run the failing tests**

Run: `pytest tests/test_ground.py -k "clones_url or local_path" -v`
Expected: FAIL — `run_ground` currently accepts `list[Path]` and has no URL branch.

- [ ] **Step 7.7: Update `run_ground` to accept URLs and clone**

Change the signature and body of `run_ground`:

```python
def run_ground(sg: Path, analogues: list) -> Path:
    """Run all available grounding sources, write grounding.json, return path.

    Each element of `analogues` may be a str (URL or path) or a Path. Git
    URLs are shallow-cloned into _cache_dir()/<slug>/; local paths are used
    in-place.
    """
    ensure_synthesis_dir(sg)

    observations: list[dict] = []
    language = "unknown"

    for arg in analogues:
        arg_str = str(arg)
        if _is_url(arg_str):
            slug = _slug_for_url(arg_str)
            target = _cache_dir() / slug
            if not target.exists():
                import subprocess
                sys.stderr.write(f"cloning {arg_str} → {target}\n")
                result = subprocess.run(
                    ["git", "clone", "--depth=1", arg_str, str(target)],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    sys.stderr.write(f"clone failed for {arg_str}: {result.stderr}\n")
                    continue
            repo = target
        else:
            repo = Path(arg_str)

        repo_lang = detect_language(repo)
        if language == "unknown" and repo_lang != "unknown":
            language = repo_lang
        for obs in extract_observations(repo):
            observations.append(obs.to_dict())

    payload = {
        "language_detected": language,
        "framework_detected": None,
        "observations": observations,
    }

    out_path = synthesis_path(sg, "grounding.json")
    save_json(out_path, payload)
    return out_path
```

Update `main()` so it accepts `str` instead of `Path` for analogue args:

```python
    parser.add_argument(
        "analogues",
        nargs="*",
        help="Zero or more analogue repo URLs or local paths",
    )
```

(Drop `type=Path` from that arg so URLs aren't mangled.)

- [ ] **Step 7.8: Run the tests**

Run: `pytest tests/test_ground.py -v`
Expected: PASS.

- [ ] **Step 7.9: Run the full suite**

Run: `pytest -q`
Expected: PASS. `test_synthesize_e2e.py` may still pass because its fixture path is still local.

- [ ] **Step 7.10: Commit**

```bash
git add scripts/synthesize/ground.py tests/test_ground.py
git commit -m "feat(ground): accept URLs as analogue args and clone to cache-dir"
```

---

### Task 8: Migrate legacy project-local analogues

**Files:**
- Modify: `scripts/synthesize/ground.py` — add `_migrate_legacy_analogues(sg)` called at the top of `run_ground`.
- Test: `tests/test_ground.py`.

Migration scan: `<sg>/synthesis/analogues/` — for each child directory:
- If `_cache_dir()/<name>/` does not exist: rename (move) into cache dir, log to stderr.
- If `_cache_dir()/<name>/` exists: leave both untouched, warn about the orphan.

- [ ] **Step 8.1: Write the failing tests**

Append to `tests/test_ground.py`:

```python
def test_migrate_moves_legacy_to_cache(tmp_path, monkeypatch, capsys):
    from scripts.synthesize.ground import _migrate_legacy_analogues
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / ".skillgoid"
    legacy = sg / "synthesis" / "analogues" / "pallets-flask"
    legacy.mkdir(parents=True)
    (legacy / "pyproject.toml").write_text("# marker\n")
    _migrate_legacy_analogues(sg)
    moved = tmp_path / "cache" / "skillgoid" / "analogues" / "pallets-flask"
    assert (moved / "pyproject.toml").read_text() == "# marker\n"
    assert not legacy.exists()
    captured = capsys.readouterr()
    assert "migrated pallets-flask" in captured.err


def test_migrate_conflict_leaves_both_and_warns(tmp_path, monkeypatch, capsys):
    from scripts.synthesize.ground import _migrate_legacy_analogues
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / ".skillgoid"
    legacy = sg / "synthesis" / "analogues" / "pallets-flask"
    legacy.mkdir(parents=True)
    (legacy / "LEGACY").write_text("x")
    cached = tmp_path / "cache" / "skillgoid" / "analogues" / "pallets-flask"
    cached.mkdir(parents=True)
    (cached / "CACHED").write_text("y")
    _migrate_legacy_analogues(sg)
    assert (legacy / "LEGACY").exists()  # not moved
    assert (cached / "CACHED").exists()  # untouched
    captured = capsys.readouterr()
    assert "orphaned" in captured.err


def test_migrate_noop_when_no_legacy(tmp_path, monkeypatch):
    from scripts.synthesize.ground import _migrate_legacy_analogues
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    # Nothing to migrate
    _migrate_legacy_analogues(sg)
    # No directories created in cache
    cache_root = tmp_path / "cache" / "skillgoid" / "analogues"
    assert cache_root.is_dir()  # _cache_dir() creates this lazily; OK either way
    assert list(cache_root.iterdir()) == []
```

- [ ] **Step 8.2: Run the failing tests**

Run: `pytest tests/test_ground.py -k migrate -v`
Expected: FAIL — `_migrate_legacy_analogues` doesn't exist.

- [ ] **Step 8.3: Implement `_migrate_legacy_analogues`**

In `scripts/synthesize/ground.py`, add below `_cache_dir`:

```python
import shutil


def _migrate_legacy_analogues(sg: Path) -> None:
    """Move any project-local analogue clones into the user-global cache dir.

    Scans <sg>/synthesis/analogues/<slug>/ and for each child directory:
      - If the cache dir has no entry with that name, rename the project-local
        copy into the cache dir.
      - If both exist, leave both alone and emit an "orphaned" warning.

    Idempotent: safe to call on every ground.py run.
    """
    legacy_root = sg / "synthesis" / "analogues"
    if not legacy_root.is_dir():
        return
    cache_root = _cache_dir()
    for child in sorted(legacy_root.iterdir()):
        if not child.is_dir():
            continue
        target = cache_root / child.name
        if target.exists():
            sys.stderr.write(
                f"warning: analogue cache already exists at {target}; "
                f"project-local copy at {child} is now orphaned, "
                f"please remove manually\n"
            )
            continue
        shutil.move(str(child), str(target))
        sys.stderr.write(f"migrated {child.name} analogue to {target}\n")
```

Then call it at the top of `run_ground`, right after `ensure_synthesis_dir(sg)`:

```python
    _migrate_legacy_analogues(sg)
```

- [ ] **Step 8.4: Run the tests**

Run: `pytest tests/test_ground.py -k migrate -v`
Expected: PASS (3 tests).

- [ ] **Step 8.5: Commit**

```bash
git add scripts/synthesize/ground.py tests/test_ground.py
git commit -m "feat(ground): migrate legacy project-local analogues to cache-dir on run"
```

---

### Task 9: Update SKILL.md so ground.py handles cloning

**Files:**
- Modify: `skills/synthesize-gates/SKILL.md` — Procedure step 2 no longer clones; just delegates to ground.py.

- [ ] **Step 9.1: Edit SKILL.md**

Replace the Procedure step 2 (`**Resolve analogue paths.**`) with a simpler version:

```markdown
2. **Collect analogue args.**
   - Accept each arg as-is. `ground.py` detects URLs (http/https/git@/ssh/git/file) vs local paths and shallow-clones URL analogues into the user-global cache dir (`~/.cache/skillgoid/analogues/<slug>/` on Linux; overridable via `$XDG_CACHE_HOME`).
   - If zero analogues given on CLI, prompt the user: `"No analogue repo provided. Please give a URL or local path to a reference project: "`. Read one line, treat as a single analogue.
```

Update the **Inputs** section bullet from:

```
  - A git URL — the skill clones it (shallow, depth=1) into `.skillgoid/synthesis/analogues/<slug>/`.
```

to:

```
  - A git URL — `ground.py` shallow-clones it (depth=1) into `~/.cache/skillgoid/analogues/<slug>/`.
```

Add a note at the end of **Phase 1 limitations** section:

```markdown
- Analogue clones live in a user-global cache (`~/.cache/skillgoid/analogues/` by default, or `$XDG_CACHE_HOME/skillgoid/analogues/`). Project-local clones from earlier versions are migrated automatically on first run.
```

Update **Output** section to remove mention of `.skillgoid/synthesis/analogues/` (replace with `~/.cache/skillgoid/analogues/`):

Change:
```
Per-stage artifacts are visible under `.skillgoid/synthesis/` (`grounding.json`, `drafts.json`) for debugging.
```

To:
```
Per-stage artifacts are visible under `.skillgoid/synthesis/` (`grounding.json`, `drafts.json`). Analogue clones live under the user-global cache dir, not the project.
```

- [ ] **Step 9.2: Verify no other skill/doc references the old clone path**

Run: `grep -rn "\.skillgoid/synthesis/analogues" skills/ docs/`
Expected: only documentation references to the migration. If the string appears in live procedure text, update it.

- [ ] **Step 9.3: Commit**

```bash
git add skills/synthesize-gates/SKILL.md
git commit -m "docs(synthesize-gates): delegate analogue cloning to ground.py and document cache-dir"
```

---

## Phase E — Duplicate collapse + multi-ref provenance (F3)

### Task 10: Widen `provenance.ref` to `str | list[str]`

**Files:**
- Modify: `scripts/synthesize/synthesize.py` — set-membership check handles both shapes.
- Test: `tests/test_synthesize.py`.

- [ ] **Step 10.1: Write the failing test**

Append to `tests/test_synthesize.py`:

```python
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
```

- [ ] **Step 10.2: Run the failing tests**

Run: `pytest tests/test_synthesize.py -k "provenance_ref_as_list or list_ref_containing" -v`
Expected: FAIL — current validator asserts `ref not in valid_refs`, which for a list raises `TypeError` or returns True.

- [ ] **Step 10.3: Widen the check**

In `scripts/synthesize/synthesize.py`, replace the provenance-ref block (around lines 98-104):

```python
        provenance = draft.get("provenance")
        if not isinstance(provenance, dict):
            raise DraftValidationError(f"draft '{gate_id}' missing 'provenance' object")
        ref = provenance.get("ref")
        if not ref:
            raise DraftValidationError(f"draft '{gate_id}' provenance missing 'ref'")
        refs_to_check = ref if isinstance(ref, list) else [ref]
        for r in refs_to_check:
            if not isinstance(r, str):
                raise DraftValidationError(
                    f"draft '{gate_id}' provenance.ref entries must be strings (got {r!r})"
                )
            if r not in valid_refs:
                raise DraftValidationError(
                    f"draft '{gate_id}' provenance ref not found in grounding: {r}"
                )
```

- [ ] **Step 10.4: Run the tests**

Run: `pytest tests/test_synthesize.py -k "provenance_ref_as_list or list_ref_containing" -v`
Expected: PASS.

- [ ] **Step 10.5: Commit**

```bash
git add scripts/synthesize/synthesize.py tests/test_synthesize.py
git commit -m "feat(synthesize): widen provenance.ref to accept list[str] for multi-source gates"
```

---

### Task 11: `write_criteria.py` multi-ref rendering

**Files:**
- Modify: `scripts/synthesize/write_criteria.py` — update `_gate_comment_block`.
- Test: `tests/test_write_criteria.py` — add assertions (check existence first).

- [ ] **Step 11.1: Check whether `test_write_criteria.py` exists**

Run: `ls tests/test_write_criteria.py 2>/dev/null && echo EXISTS || echo MISSING`
Expected: EXISTS (per summary). Read its top to match style.

- [ ] **Step 11.2: Write the failing test**

Append to `tests/test_write_criteria.py`:

```python
def test_gate_comment_block_renders_single_ref_as_inline():
    from scripts.synthesize.write_criteria import _gate_comment_block
    draft = {
        "id": "cov",
        "type": "coverage",
        "min_percent": 80,
        "provenance": {"source": "analogue", "ref": "mini/pyproject.toml"},
    }
    block = _gate_comment_block(draft)
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
    block = _gate_comment_block(draft)
    assert "source: analogue" in block
    assert "refs:" in block
    assert "- mini/pyproject.toml" in block
    assert "- mini/.github/workflows/ci.yml" in block
```

- [ ] **Step 11.3: Run the failing tests**

Run: `pytest tests/test_write_criteria.py -k gate_comment_block -v`
Expected: FAIL — current function always renders single-ref form.

- [ ] **Step 11.4: Update `_gate_comment_block`**

In `scripts/synthesize/write_criteria.py`, replace `_gate_comment_block`:

```python
def _gate_comment_block(draft: dict) -> str:
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
    lines.append(f"  # {PHASE1_VALIDATION_LABEL}")
    rationale = draft.get("rationale")
    if rationale:
        lines.append(f"  # rationale: {rationale}")
    return "\n".join(lines)
```

- [ ] **Step 11.5: Run the tests**

Run: `pytest tests/test_write_criteria.py -v`
Expected: PASS.

- [ ] **Step 11.6: Commit**

```bash
git add scripts/synthesize/write_criteria.py tests/test_write_criteria.py
git commit -m "feat(write_criteria): render multi-ref provenance as a refs: block"
```

---

### Task 12: Duplicate coverage-gate collapse pass

**Files:**
- Modify: `scripts/synthesize/synthesize.py` — add `_collapse_duplicate_coverage` and call it after per-draft validation.
- Test: `tests/test_synthesize.py`.

- [ ] **Step 12.1: Write the failing test**

Append to `tests/test_synthesize.py`:

```python
def test_parse_collapses_duplicate_coverage_drafts(capsys):
    grounding = _grounding_payload()
    # Add a second coverage-capable observation
    grounding["observations"].append({
        "source": "analogue",
        "ref": "mini-flask-demo/.github/workflows/test.yml",
        "command": "coverage_threshold=95",
        "context": "CI step declares --fail-under",
        "observed_type": "coverage_threshold",
    })
    raw = json.dumps({
        "drafts": [
            {
                "id": "cov_run",
                "type": "coverage",
                "min_percent": 80,
                "provenance": {"source": "analogue", "ref": "mini-flask-demo/pyproject.toml"},
                "rationale": "from pyproject",
            },
            {
                "id": "cov_report",
                "type": "coverage",
                "min_percent": 95,
                "provenance": {"source": "analogue", "ref": "mini-flask-demo/.github/workflows/test.yml"},
                "rationale": "from CI step",
            },
        ]
    })
    drafts = parse_subagent_output(raw, grounding)
    coverage_drafts = [d for d in drafts if d["type"] == "coverage"]
    assert len(coverage_drafts) == 1
    # max threshold wins
    assert coverage_drafts[0]["min_percent"] == 95
    # provenance.ref becomes a list
    assert isinstance(coverage_drafts[0]["provenance"]["ref"], list)
    assert set(coverage_drafts[0]["provenance"]["ref"]) == {
        "mini-flask-demo/pyproject.toml",
        "mini-flask-demo/.github/workflows/test.yml",
    }
    # rationale is concatenated
    assert "from pyproject" in coverage_drafts[0]["rationale"]
    assert "from CI step" in coverage_drafts[0]["rationale"]
    # stderr mentions the collapse
    captured = capsys.readouterr()
    assert "collapsed 2 coverage drafts" in captured.err


def test_parse_single_coverage_draft_not_collapsed(capsys):
    grounding = _grounding_payload()
    raw = json.dumps({
        "drafts": [
            {
                "id": "cov",
                "type": "coverage",
                "min_percent": 80,
                "provenance": {"source": "analogue", "ref": "mini-flask-demo/pyproject.toml"},
                "rationale": "x",
            }
        ]
    })
    drafts = parse_subagent_output(raw, grounding)
    assert len(drafts) == 1
    assert isinstance(drafts[0]["provenance"]["ref"], str)  # unchanged
    captured = capsys.readouterr()
    assert "collapsed" not in captured.err
```

- [ ] **Step 12.2: Run the failing test**

Run: `pytest tests/test_synthesize.py -k "duplicate_coverage or single_coverage" -v`
Expected: FAIL.

- [ ] **Step 12.3: Implement the collapse pass**

In `scripts/synthesize/synthesize.py`, add a private helper above `parse_subagent_output`:

```python
def _collapse_duplicate_coverage(drafts: list[dict]) -> list[dict]:
    """Merge multiple type: coverage drafts into one (max min_percent wins).

    Provenance refs are unioned into a list. Rationale strings are concatenated
    with ' + '. Non-coverage drafts pass through unchanged.
    """
    coverage_drafts = [d for d in drafts if d.get("type") == "coverage"]
    if len(coverage_drafts) <= 1:
        return drafts

    refs: list[str] = []
    for d in coverage_drafts:
        prov_ref = d.get("provenance", {}).get("ref")
        if isinstance(prov_ref, list):
            refs.extend(prov_ref)
        elif isinstance(prov_ref, str):
            refs.append(prov_ref)
    # Dedupe while preserving first-occurrence order
    seen: set[str] = set()
    deduped_refs: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            deduped_refs.append(r)

    merged = {
        "id": coverage_drafts[0]["id"],
        "type": "coverage",
        "min_percent": max(d.get("min_percent", 0) for d in coverage_drafts),
        "provenance": {
            "source": coverage_drafts[0].get("provenance", {}).get("source", "analogue"),
            "ref": deduped_refs if len(deduped_refs) > 1 else deduped_refs[0],
        },
        "rationale": " + ".join(
            d.get("rationale", "") for d in coverage_drafts if d.get("rationale")
        ),
    }

    sys.stderr.write(
        f"collapsed {len(coverage_drafts)} coverage drafts into one "
        f"(min_percent={merged['min_percent']})\n"
    )

    out: list[dict] = []
    merged_emitted = False
    for d in drafts:
        if d.get("type") == "coverage":
            if not merged_emitted:
                out.append(merged)
                merged_emitted = True
            continue
        out.append(d)
    return out
```

At the bottom of `parse_subagent_output`, just before `return drafts`, call the collapse:

```python
    drafts = _collapse_duplicate_coverage(drafts)
    return drafts
```

- [ ] **Step 12.4: Run the tests**

Run: `pytest tests/test_synthesize.py -k "duplicate_coverage or single_coverage" -v`
Expected: PASS.

- [ ] **Step 12.5: Run the full synthesize suite**

Run: `pytest tests/test_synthesize.py -v`
Expected: all PASS.

- [ ] **Step 12.6: Commit**

```bash
git add scripts/synthesize/synthesize.py tests/test_synthesize.py
git commit -m "feat(synthesize): collapse duplicate type: coverage drafts into one"
```

---

## Phase F — Fixture + E2E updates

### Task 13: Update `mini-flask-demo` fixture

**Files:**
- Modify: `tests/fixtures/synthesize/mini-flask-demo/pyproject.toml` — add `[tool.coverage.report]` section.
- Modify: `tests/fixtures/synthesize/mini-flask-demo/.github/workflows/test.yml` — add a `coverage report --fail-under=95` step.

This fixture is hand-rolled test data, not a real Python project, so we don't need to keep the two values consistent — the spec calls for two different values so grounding emits two observations.

- [ ] **Step 13.1: Edit the fixture pyproject.toml**

Replace the contents of `tests/fixtures/synthesize/mini-flask-demo/pyproject.toml` with:

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

[tool.mypy]
strict = false

[tool.coverage.run]
omit = ["tests/*"]

[tool.coverage.report]
fail_under = 100
```

- [ ] **Step 13.2: Edit the fixture workflow**

Replace the contents of `tests/fixtures/synthesize/mini-flask-demo/.github/workflows/test.yml` with:

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
      - run: coverage report --fail-under=95
```

- [ ] **Step 13.3: Re-run the ground_analogue tests to confirm**

Run: `pytest tests/test_ground_analogue.py -v`
Expected: PASS. The existing `test_extract_observations_*` tests should still find `pytest` and `ruff` types; any test that counts exact observation list length may need updating — search and adjust.

- [ ] **Step 13.4: Check for any length-sensitive assertions**

Run: `grep -n "len(obs)" tests/test_ground_analogue.py`
If any assertion pins a count, adjust it to accept the new `coverage_threshold` observations (one from pyproject, one from workflow).

- [ ] **Step 13.5: Commit**

```bash
git add tests/fixtures/synthesize/mini-flask-demo/
git commit -m "test(fixture): add coverage threshold declarations to mini-flask-demo"
```

---

### Task 14: Update `test_synthesize_e2e.py` for canonical coverage gate

**Files:**
- Modify: `tests/test_synthesize_e2e.py`.

- [ ] **Step 14.1: Read the existing E2E test**

Read: `tests/test_synthesize_e2e.py`
Identify how it constructs a simulated subagent output string and what it asserts about the final `criteria.yaml.proposed`.

- [ ] **Step 14.2: Add the failing assertions**

Append to `tests/test_synthesize_e2e.py` (a new test using the same fixture + machinery):

```python
def test_e2e_canonical_coverage_gate(tmp_path):
    """Running the full pipeline with a subagent draft that cites coverage_threshold
    observations produces a criteria.yaml.proposed where the coverage gate has
    min_percent set and no args.
    """
    import json as _json
    import subprocess as _subprocess
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
    assert "args:" not in text.split("coverage_main", 1)[1].split("- id:", 1)[0] if "- id:" in text else True
    # Source ref is cited in the comment block
    assert "mini-flask-demo/.github/workflows/test.yml" in text
```

- [ ] **Step 14.3: Run the failing test**

Run: `pytest tests/test_synthesize_e2e.py -k canonical_coverage -v`
Expected: it should PASS if Tasks 1-13 are correct — Task 14 is primarily a regression-guard. If it fails, walk back through the preceding tasks and confirm the fixture, grounding extraction, and write_criteria rendering all align.

- [ ] **Step 14.4: Run the full suite**

Run: `pytest -q`
Expected: PASS. If any other e2e assertion broke because of the fixture addition, fix it inline (likely an exact-count assertion that needs updating to include threshold observations).

- [ ] **Step 14.5: Commit**

```bash
git add tests/test_synthesize_e2e.py
git commit -m "test(e2e): assert canonical coverage gate shape end-to-end"
```

---

## Phase G — Ship

### Task 15: SKILL.md limitations, CHANGELOG, plugin version bump

**Files:**
- Modify: `skills/synthesize-gates/SKILL.md` — update Phase 1.5 limitations.
- Modify: `.claude-plugin/plugin.json` — version 0.9.0 → 0.10.0.
- Modify or Create: `CHANGELOG.md` at plugin root — add 0.10.0 entry. Check existence first.

- [ ] **Step 15.1: Check for CHANGELOG.md**

Run: `ls CHANGELOG.md 2>/dev/null && echo EXISTS || echo MISSING`
If EXISTS, append to the top; if MISSING, skip that edit (the plugin doesn't ship one).

- [ ] **Step 15.2: Update `SKILL.md` Phase 1.5 limitations**

In `skills/synthesize-gates/SKILL.md`, find the "## Phase 1 limitations (called out for users)" section. Update it to reflect v0.10 changes:

```markdown
## Phase 1 limitations (called out for users)

Phase 1.5 (v0.9.0) addressed pyproject `[tool.*]` section parsing and CI
wrapper-script following. v0.10 tightens `type: coverage` and relocates
analogue clones. The remaining Phase 2 gaps:

- All gates are labeled `validated: none (Phase 1: oracle validation deferred)`. The user is the only validator.
- No context7 grounding — only user-pointed analogues.
- No curated template fallback for cold-start projects.
- No retry on subagent output validation failure — re-run the skill if needed.

Phase 2 (planned) addresses all four.
```

Also update the Risks section — append:

```markdown
- `type: coverage` gates are now **declarative only**: `min_percent` required, `args` forbidden. Literal `coverage` CLI invocations must use `type: run-command`. Hand-authored criteria from pre-v0.10 that used the loose shape will fail schema validation at the build's feasibility stage — see the v0.10 release note for migration.
```

- [ ] **Step 15.3: Bump `plugin.json`**

Edit `.claude-plugin/plugin.json` — change `"version": "0.9.0"` to `"version": "0.10.0"`. Leave all other fields alone.

- [ ] **Step 15.4: Add / update CHANGELOG.md (if it exists)**

If CHANGELOG.md exists, add a new section at the top (below any preamble, above earlier entries):

```markdown
## 0.10.0 (2026-04-19)

**Breaking:** `type: coverage` gates no longer accept `args`. The loose shape silently dropped `--fail-under=N` thresholds. Migration: replace `args: ['report', '--fail-under=N']` with `min_percent: N`, or switch to `type: run-command` for literal CLI usage.

### Features

- `synthesize-gates` grounds `coverage_threshold` from `[tool.coverage.report].fail_under` and from `--fail-under=N` tokens in CI commands.
- Subagent prompt teaches the canonical `type: coverage` shape; Stage 2 validator rejects `args` and requires `min_percent` on coverage gates.
- Duplicate `type: coverage` drafts are collapsed into one (max `min_percent` wins, provenance refs unioned).
- Analogue clones now live in `~/.cache/skillgoid/analogues/` (or `$XDG_CACHE_HOME/skillgoid/analogues/`) instead of inside the user's project tree. Legacy project-local clones are migrated automatically on next `ground.py` run.

### Fixes

- Analogue clones no longer contaminate the project's lint/type/coverage scope.
```

If CHANGELOG.md doesn't exist, skip this step.

- [ ] **Step 15.5: Run the full suite one final time**

Run: `pytest -q`
Expected: all PASS.

Run: `make lint` (or `ruff check .`)
Expected: no violations.

- [ ] **Step 15.6: Commit**

```bash
git add skills/synthesize-gates/SKILL.md .claude-plugin/plugin.json CHANGELOG.md 2>/dev/null
git commit -m "chore(release): v0.10.0 — synthesized gates usable end-to-end"
```

---

## Self-review checklist (for the plan author, done now)

1. **Spec coverage check:**
   - 13a schema tightening → Task 1.
   - 13a validator → Task 2.
   - 13a `coverage_threshold` from pyproject → Task 3.
   - 13a `coverage_threshold` from CI `--fail-under=N` → Task 4.
   - 13a subagent prompt → Task 5.
   - 13b `_cache_dir()` helper → Task 6.
   - 13b URL detection + clone-to-cache → Task 7.
   - 13b legacy-analogue migration → Task 8.
   - 13b SKILL.md delegation → Task 9.
   - 13c widened `provenance.ref` → Task 10.
   - 13c multi-ref rendering → Task 11.
   - 13c collapse pass → Task 12.
   - Fixture updates → Task 13.
   - E2E assertions → Task 14.
   - Version bump + limitations + CHANGELOG → Task 15.
   All spec sections covered.

2. **Placeholder scan:** no "TBD", "TODO", "implement later", or vague steps. Every step has either a concrete code block, a concrete file edit, or a concrete command with expected output.

3. **Type consistency:** functions used consistently across tasks:
   - `_cache_dir()` returns `Path` (Tasks 6, 7, 8).
   - `_is_url(str) -> bool` and `_slug_for_url(str) -> str` (Task 7 only).
   - `_migrate_legacy_analogues(sg: Path) -> None` (Task 8 only).
   - `parse_pyproject_coverage_threshold(Path) -> int | None` (Task 3 only).
   - `_extract_fail_under(str) -> int | None` (Task 4 only).
   - `_collapse_duplicate_coverage(list[dict]) -> list[dict]` (Task 12 only).
   - `observed_type: "coverage_threshold"` — string literal, used identically in Tasks 3, 4, 5, 12, 13, 14.
   - `provenance.ref` accepts `str | list[str]` — asserted by validator (Task 10), produced by collapse (Task 12), rendered by `_gate_comment_block` (Task 11).

No inconsistencies detected.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-19-skillgoid-v0.10-synthesized-gates-usable.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
