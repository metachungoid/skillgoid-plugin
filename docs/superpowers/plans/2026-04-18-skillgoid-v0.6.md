# Skillgoid v0.6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Skillgoid v0.6 — one fix: `_merge_env` exports `SKILLGOID_PYTHON` so shell strings can reference a guaranteed-working python binary. Observed on indexgrep's integration-retry after bare `python` failed inside `bash -c`.

**Architecture:** ~3 lines in `_merge_env`, two small skill-prose notes, docs, plugin.json bump. No new helpers, no schema changes.

**Tech Stack:** Python 3.11+. No new deps.

**Spec:** `docs/superpowers/specs/2026-04-18-skillgoid-v0.6-shell-python.md`.
**Evidence:** 4-run `metrics.jsonl` + indexgrep retrospective at `/home/flip/Development/skillgoid-test/indexgrep/.skillgoid/retrospective.md`.

---

## Repo layout changes

```
skillgoid-plugin/
├── .claude-plugin/plugin.json       # MODIFIED: version → 0.6.0
├── scripts/measure_python.py        # MODIFIED: _merge_env exports SKILLGOID_PYTHON
├── skills/python-gates/SKILL.md     # MODIFIED: document SKILLGOID_PYTHON
├── skills/clarify/SKILL.md          # MODIFIED: shell-pipeline example uses $SKILLGOID_PYTHON
├── tests/test_env_gate.py           # MODIFIED: +2 tests
├── README.md                        # MODIFIED: v0.6 section
├── CHANGELOG.md                     # MODIFIED: [0.6.0] entry
└── docs/roadmap.md                  # MODIFIED: plan-refinement formally dropped
```

**Expected test count:** 115 → 117.

---

## Task 1: Branch setup

- [ ] **Step 1.1: Verify main baseline**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git checkout main
. .venv/bin/activate
pytest -q && ruff check .
```
Expected: 115 passed, ruff clean.

- [ ] **Step 1.2: Create feat/v0.6**

```bash
git checkout -b feat/v0.6
```

- [ ] **Step 1.3: No commit — housekeeping only.**

---

## Task 2: `_merge_env` exports `SKILLGOID_PYTHON` + tests

**Files:**
- Modify: `scripts/measure_python.py`
- Modify: `tests/test_env_gate.py`

### Step 2.1: Write failing tests — append to `tests/test_env_gate.py`

```python
def test_skillgoid_python_env_is_exported(tmp_path: Path):
    """SKILLGOID_PYTHON should be set to sys.executable in the gate subprocess."""
    criteria = """
gates:
  - id: check
    type: run-command
    command: ["sh", "-c", "echo $SKILLGOID_PYTHON"]
    expect_exit: 0
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    stdout = report["results"][0]["stdout"].strip()
    assert stdout.endswith("python") or stdout.endswith("python3") or "/python" in stdout, \
        f"expected python path, got: {stdout!r}"


def test_shell_string_uses_skillgoid_python_successfully(tmp_path: Path):
    """A bash -c command referencing $SKILLGOID_PYTHON should run the right interpreter."""
    criteria = """
gates:
  - id: check
    type: run-command
    command: ["bash", "-c", "$SKILLGOID_PYTHON -c 'print(42)'"]
    expect_exit: 0
    expect_stdout_match: "42"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert "42" in report["results"][0]["stdout"]
```

### Step 2.2: Run — confirm 2 FAIL

```bash
. .venv/bin/activate
pytest tests/test_env_gate.py::test_skillgoid_python_env_is_exported tests/test_env_gate.py::test_shell_string_uses_skillgoid_python_successfully -v
```

Expected: both fail — env var not exported yet.

### Step 2.3: Update `_merge_env` in `scripts/measure_python.py`

Read the file. Locate the current `_merge_env` implementation. The first line should be something like `merged = {**os.environ}`. Change the initial merged-dict to also include `SKILLGOID_PYTHON`:

```python
def _merge_env(project: Path, gate_env: dict) -> dict:
    """Merge gate env: overrides onto os.environ. Relative paths in known
    path-like vars (PYTHONPATH, PATH) are resolved against project dir.

    Always exports SKILLGOID_PYTHON=sys.executable so shell command strings
    (e.g., ["bash", "-c", "$SKILLGOID_PYTHON -m myproj"]) can reference a
    guaranteed python binary without worrying about whether `python` is on PATH.
    User-provided gate env: CAN override SKILLGOID_PYTHON if needed (e.g., to
    test against a different interpreter).
    """
    merged = {**os.environ, "SKILLGOID_PYTHON": sys.executable}
    for k, v in (gate_env or {}).items():
        if k in ("PYTHONPATH", "PATH"):
            parts = []
            for part in str(v).split(os.pathsep):
                if part and not os.path.isabs(part):
                    part = str((project / part).resolve())
                parts.append(part)
            merged[k] = os.pathsep.join(parts)
        else:
            merged[k] = str(v)
    return merged
```

Keep the rest of the function identical — only the first `merged = ...` line and the docstring change.

### Step 2.4: Run tests

```bash
pytest -v && ruff check .
```

Expected: 115 + 2 = 117 pass, ruff clean.

### Step 2.5: Commit

```bash
git add scripts/measure_python.py tests/test_env_gate.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(env): export SKILLGOID_PYTHON for shell-string gate commands

_merge_env now always exports SKILLGOID_PYTHON=sys.executable into the
subprocess environment. Shell strings like
  command: ['bash', '-c', '\$SKILLGOID_PYTHON -m myproj']
now work portably in any environment, regardless of whether bare
'python' is on PATH.

Observed on indexgrep's integration-retry: bare 'python' inside bash -c
failed with exit 127 because v0.4's auto-resolve only handles command[0],
not substrings inside shell command bodies. Env-var export is documented
and opt-in — simpler than parsing bash strings.

User gate env: can override SKILLGOID_PYTHON if needed (niche)."
```

---

## Task 3: Skill prose updates

**Files:**
- Modify: `skills/python-gates/SKILL.md`
- Modify: `skills/clarify/SKILL.md`

### Step 3.1: `python-gates` — add SKILLGOID_PYTHON note

Read the file. Find the existing v0.3 **Note:** paragraph about the `timeout` field, and the v0.4 **Note:** paragraph about `env:`. After those, add:

```markdown
**Note:** the adapter always exports `SKILLGOID_PYTHON=sys.executable` into the gate subprocess. Inside shell command strings (e.g., `["bash", "-c", "..."]`), reference `$SKILLGOID_PYTHON` instead of bare `python` to get a guaranteed-working interpreter path. The bare-`python` auto-resolution (v0.4) applies only to `command[0]`, so it won't help when `python` appears inside a shell pipeline. `$SKILLGOID_PYTHON` does.
```

Use Edit with enough context to place it after the v0.4 env: note.

### Step 3.2: `clarify` — shell-pipeline integration gate uses $SKILLGOID_PYTHON

Read the file. Find step 5.1 (default integration gate per project type). For service projects (which often need shell-pipeline gates) AND any shell-based example, update guidance:

Find the "Service" bullet in step 5.1. Extend it with an example:

```markdown
   - **Service:** if the user can describe a start/health-check/shutdown sequence, generate a `run-command` that does all three. Otherwise leave `integration_gates` empty and note that one should be added by hand. When the service needs a shell pipeline, use `$SKILLGOID_PYTHON` instead of bare `python`:
     ```yaml
     integration_gates:
       - id: service_smoke
         type: run-command
         command: ["bash", "-c", "$SKILLGOID_PYTHON -m myservice --port 8999 & sleep 1 && curl -sf http://localhost:8999/health && kill %1"]
         env:
           PYTHONPATH: "src"
     ```
     (`$SKILLGOID_PYTHON` is set by the adapter to `sys.executable` — guaranteed-working interpreter path inside shell strings.)
```

If no "Service:" bullet exists in that exact form, adapt the edit to the closest existing shell-based integration-gate guidance.

### Step 3.3: Verify + run full suite

```bash
for f in skills/python-gates/SKILL.md skills/clarify/SKILL.md; do
  python -c "import yaml; print(yaml.safe_load(open('$f').read().split('---',2)[1])['name'])"
done
. .venv/bin/activate && pytest -v && ruff check .
```

Expected: names print; 117 tests pass; ruff clean.

### Step 3.4: Commit

```bash
git add skills/python-gates/SKILL.md skills/clarify/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(skills): document \$SKILLGOID_PYTHON pattern for shell-string gates

- python-gates: adds a Note explaining that \$SKILLGOID_PYTHON is always
  exported, and that users should prefer it inside shell strings over
  bare 'python' (which only auto-resolves for command[0]).
- clarify: Service integration-gate example now uses \$SKILLGOID_PYTHON
  inside bash -c pipelines so users don't repeat indexgrep's mistake."
```

---

## Task 4: Docs + plugin.json bump

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/roadmap.md`

### Step 4.1: Bump `plugin.json` version

Read `.claude-plugin/plugin.json`. Change `"version": "0.5.0"` → `"0.6.0"`.

### Step 4.2: README — insert "What's new in v0.6" BEFORE v0.5 section

```markdown
## What's new in v0.6

Single fix driven by the indexgrep real-run evidence:

- **`SKILLGOID_PYTHON` env export.** The adapter now always exports `SKILLGOID_PYTHON=sys.executable` into every gate subprocess. Shell command strings (e.g., `["bash", "-c", "..."]`) should reference `$SKILLGOID_PYTHON` instead of bare `python` — v0.4's auto-resolution only handles `command[0]`, not substrings inside shell command bodies.

Before (indexgrep integration retry):
```yaml
command: ["bash", "-c", "python -m myproj"]   # exit 127 if 'python' not on PATH
```

After:
```yaml
command: ["bash", "-c", "$SKILLGOID_PYTHON -m myproj"]   # always works
```

Nothing else in v0.6. Plan-refinement-mid-build was formally dropped from the roadmap after producing zero evidence across four real runs (jyctl, taskq, mdstats, indexgrep). Shipping less is the right response to real data.

All changes fully backward-compatible with v0.5.

```

### Step 4.3: CHANGELOG — `[0.6.0]` entry BEFORE `[0.5.0]`

```markdown
## [0.6.0] — 2026-04-18

### Added
- `SKILLGOID_PYTHON` env var (value: `sys.executable`) is now exported to every gate subprocess by `_merge_env`. Shell command strings can reference `$SKILLGOID_PYTHON` to get a guaranteed-working python path — addresses the gap where v0.4's auto-resolution only covers `command[0]`, not substrings in shell bodies.

### Changed
- `python-gates` skill documents the `SKILLGOID_PYTHON` pattern.
- `clarify` skill proposes `$SKILLGOID_PYTHON` instead of bare `python` for service-style shell-pipeline integration gates.

### Backward compatibility
- Fully additive. v0.5 criteria/chunks/iterations parse unchanged.
- User gate env: can override SKILLGOID_PYTHON for niche cases (testing against a different interpreter).

### Removed from roadmap
- **Plan refinement mid-build.** Four real Skillgoid runs (jyctl, taskq, mdstats, indexgrep) at 3, 4, 6, and 7 chunks all produced zero evidence the feature is needed. Formally dropped from the roadmap as of v0.6. A v0.7+ re-evaluation would require qualitatively different project shapes (research-grade builds with genuine decomposition uncertainty) first.

```

### Step 4.4: docs/roadmap.md — append v0.6 Shipped + redefine what remains

Find the existing "## Shipped" section. Add a new entry after v0.5:

```markdown
### v0.6 — Shell-String Python Resolution (2026-04-18)
One-item micro-release driven by indexgrep evidence:
- `SKILLGOID_PYTHON` env export covers `bash -c` / `sh -c` style gates where v0.4's auto-resolution can't reach.
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.6-shell-python.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.6.md`

```

Replace the existing "## Deferred — v0.6 goals" (or whatever the deferred section is currently titled) with:

```markdown
## Dropped from roadmap (v0.6 decision)

- **Plan refinement mid-build.** Four real runs, zero evidence. Formally dropped. Re-evaluation would require qualitatively different project shapes (research-grade builds with genuine decomposition uncertainty) AND two+ subsequent runs still producing evidence for the need.

## Deferred — await qualitatively different project shapes

Items kept deferred because no real run has exercised them. Don't revive without new evidence.

- **Polyglot / multi-language projects.** All 4 real runs have been single-language python. Until a project actually demands it, don't build.
- **Parallel chunks extensions.** v0.5 shipped the core — indexgrep validated a 3-way parallel wave. No further parallel-chunks work until a run surfaces an unmet need (e.g., failures when waves exceed some N, or a need for parallel-subagent retry coordination).
- **Rehearsal mode.** Subsumed by v0.4 feasibility + v0.5 scaffolding awareness.
- **More language adapters** (`node-gates`, `go-gates`, `rust-gates`). Wait for a project that demands them.
- **Gate-type plugins.** Premature abstraction; no ecosystem demand.
- **Dashboards / HTML rendering.** `/skillgoid:stats` markdown sufficient.
- **Tighter vault retrieval.** 5 entries after 4 projects; no scale pressure.

## How to pick up v0.7

1. Run Skillgoid on a **qualitatively different** project shape (not another python CLI). Real candidates:
   - A polyglot project (Python backend + Node CLI wrapper) — would need `node-gates` adapter first.
   - An async/concurrent project — may surface timeout-during-async-io issues.
   - A project with **genuine planning uncertainty** (e.g., "design a system that processes X" where the decomposition isn't obvious upfront) — the only real test of plan-refinement value.
2. Observe what actually fails. Demote predicted-ROI items that don't surface.
3. Spec v0.7 around the top 1-2 observed issues.
4. **Shipping less is the correct response to real-world data** — v0.2 shipped 3 big items, v0.3 shipped 6 polish items, v0.4 shipped 4 items, v0.5 shipped 3, v0.6 shipped 1. The trajectory is correct.
```

### Step 4.5: Verify everything

```bash
python -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])"
. .venv/bin/activate && pytest -v && ruff check .
```

Expected: version prints `0.6.0`; 117 tests pass; ruff clean.

### Step 4.6: Commit

```bash
git add .claude-plugin/plugin.json README.md CHANGELOG.md docs/roadmap.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "docs: v0.6 release + plan-refinement formally dropped

plugin.json → 0.6.0. README gains 'What's new in v0.6'. CHANGELOG
adds [0.6.0] with the 'Removed from roadmap' section for
plan-refinement-mid-build. Roadmap moves v0.6 to Shipped, creates a
'Dropped from roadmap' section for plan-refinement, and narrows v0.7
guidance to 'await qualitatively different project shapes' — shipping
less is the correct response to four-run evidence."
```

---

## Self-review

**Spec coverage:**
- §3.1 SKILLGOID_PYTHON export → Task 2 (code) + Task 3 (docs).
- §10 Definition of done — plugin.json bump → Task 4 (learned from v0.5 critical-fix).

**Placeholder scan:** no TBD/TODO. `$SKILLGOID_PYTHON` placeholder in examples is the intended shell-reference, not a template placeholder.

**Type/name consistency:**
- `_merge_env(project: Path, gate_env: dict) -> dict` — unchanged signature; only initial merged-dict differs.
- `SKILLGOID_PYTHON` env var name — consistent across Task 2 code, Task 3 skill prose, Task 4 docs.

No gaps.

---

## Execution handoff

Plan complete. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch one subagent per task, fast iteration.

**2. Inline Execution** — `superpowers:executing-plans` with checkpoints.

Which approach?
