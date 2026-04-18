# Skillgoid v0.4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Skillgoid v0.4 — Integration Polish & Unstick. Observed-ROI-reranked additions from the first real Skillgoid run (jyctl, 2026-04-17), plus two autonomy-preservation bets (unstick, stats).

**Architecture:** Three thematic groups: (A) integration ergonomics — gate env field + python-binary auto-resolution; (B) pre-build correctness — feasibility skill + clarify caveats; (C) autonomy — unstick skill + stats reader. Everything additive — no architectural changes to the build/loop/retrospect dispatch flow.

**Tech Stack:** Python 3.11+, pytest, ruff (existing). One new helper script (`scripts/stats_reader.py`), `measure_python.py` extensions, three new skill markdown files. No new runtime dependencies.

**Backward compatibility:** Fully additive. v0.3 criteria.yaml / iteration records parse unchanged. Missing `env:` → empty dict. Missing feasibility/unstick/stats skills → build's current v0.3 flow continues.

**Spec:** `docs/superpowers/specs/2026-04-18-skillgoid-v0.4-integration-polish-and-unstick.md` (commit `cd15a6f`).
**Evidence:** `~/.claude/skillgoid/metrics.jsonl` line 1 + `/home/flip/Development/skillgoid-test/jyctl/.skillgoid/retrospective.md`.

---

## Repo layout changes

```
skillgoid-plugin/
├── scripts/
│   ├── measure_python.py              # MODIFIED: env merge + python resolution
│   ├── stats_reader.py                # NEW: metrics.jsonl aggregation
│   └── (others unchanged)
├── schemas/
│   └── criteria.schema.json           # MODIFIED: gate env field
├── skills/
│   ├── build/SKILL.md                 # MODIFIED: wire feasibility step + surface unstick on stall
│   ├── clarify/SKILL.md               # MODIFIED: gitignore + coverage caveat prose
│   ├── python-gates/SKILL.md          # MODIFIED: note env is honored
│   ├── feasibility/SKILL.md           # NEW
│   ├── unstick/SKILL.md               # NEW
│   ├── stats/SKILL.md                 # NEW
│   └── (others unchanged)
├── tests/
│   ├── test_env_gate.py               # NEW
│   ├── test_python_resolution.py      # NEW
│   ├── test_stats_reader.py           # NEW
│   ├── test_schemas.py                # MODIFIED: env field tests
│   └── (others unchanged)
├── README.md                          # MODIFIED: v0.4 section
├── CHANGELOG.md                       # MODIFIED: [0.4.0] entry
└── docs/roadmap.md                    # MODIFIED: v0.4 shipped, v0.5 defined
```

**Expected test count:** 80 (v0.3) → ~94 after v0.4.

---

## Task 1: Branch setup

**Files:** none — git housekeeping.

- [ ] **Step 1.1: Verify baseline on main**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git checkout main
. .venv/bin/activate
pytest -q
ruff check .
```
Expected: `80 passed`, ruff clean.

- [ ] **Step 1.2: Create feat/v0.4 branch**

```bash
git checkout -b feat/v0.4
git branch --show-current  # → feat/v0.4
```

- [ ] **Step 1.3: No commit — housekeeping only**

---

## Task 2: Gate `env:` field

**Files:**
- Modify: `schemas/criteria.schema.json`
- Modify: `scripts/measure_python.py`
- Create: `tests/test_env_gate.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 2.1: Write failing tests — `tests/test_env_gate.py`**

```python
"""Gate `env:` field — merged into subprocess env at dispatch."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "measure_python.py"


def run_cli(criteria: str, project: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(project), "--criteria-stdin"],
        input=criteria, capture_output=True, text=True, check=False, timeout=30,
    )
    return json.loads(result.stdout)


def test_gate_env_overrides_for_subprocess(tmp_path: Path):
    """A gate env: key should be visible to the subprocess via its environment."""
    criteria = """
gates:
  - id: check_env
    type: run-command
    command: ["sh", "-c", "echo $MYVAR"]
    expect_exit: 0
    expect_stdout_match: "hello-from-env"
    env:
      MYVAR: "hello-from-env"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert "hello-from-env" in report["results"][0]["stdout"]


def test_gate_env_overrides_outer_env(tmp_path: Path, monkeypatch):
    """Gate env: value should win against a pre-existing value in os.environ."""
    monkeypatch.setenv("MYVAR", "outer-value")
    criteria = """
gates:
  - id: check_override
    type: run-command
    command: ["sh", "-c", "echo $MYVAR"]
    expect_exit: 0
    expect_stdout_match: "inner-value"
    env:
      MYVAR: "inner-value"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert "inner-value" in report["results"][0]["stdout"]


def test_cli_command_runs_with_env(tmp_path: Path):
    """cli-command-runs also honors env:."""
    criteria = """
gates:
  - id: cli_with_env
    type: cli-command-runs
    command: ["sh", "-c", "echo $PYTHONPATH"]
    expect_exit: 0
    expect_stdout_match: "/custom/path"
    env:
      PYTHONPATH: "/custom/path"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
```

- [ ] **Step 2.2: Run — confirm 3 FAIL**

```bash
pytest tests/test_env_gate.py -v
```

- [ ] **Step 2.3: Update `schemas/criteria.schema.json`**

Add to gate item `properties` (in both `gates[].items.properties` AND `integration_gates[].items.properties`):

```json
"env": {
  "type": "object",
  "additionalProperties": {"type": "string"},
  "description": "Environment variables merged into os.environ when running this gate."
}
```

- [ ] **Step 2.4: Add schema tests — append to `tests/test_schemas.py`**

```python
def test_criteria_gate_env_validates():
    data = {"gates": [{"id": "g", "type": "pytest", "env": {"PYTHONPATH": "src"}}]}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert errors == []


def test_criteria_gate_env_values_must_be_strings():
    data = {"gates": [{"id": "g", "type": "pytest", "env": {"N": 42}}]}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any(e.validator == "type" for e in errors)
```

- [ ] **Step 2.5: Update `scripts/measure_python.py` — env merging**

Add a helper near `_run`:

```python
def _merge_env(project: Path, gate_env: dict) -> dict:
    """Merge gate env: overrides onto os.environ. Relative paths in known
    path-like vars (PYTHONPATH, PATH) are resolved against project dir."""
    merged = {**os.environ}
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

In `_gate_run_command` and `_gate_cli_command_runs`, replace:
```python
code, out, err = _run(cmd, project, timeout=timeout)
```
with:
```python
env = _merge_env(project, gate.get("env") or {})
proc = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True, check=False, timeout=timeout)
code, out, err = proc.returncode, proc.stdout, proc.stderr
```

Wrap the `subprocess.run` in a try/except TimeoutExpired identical to existing handlers (return a timeout GateResult).

- [ ] **Step 2.6: Run tests**

```bash
pytest -v && ruff check .
```
Expected: 80 + 3 env + 2 schema = 85 total, ruff clean.

- [ ] **Step 2.7: Commit**

```bash
git add scripts/measure_python.py schemas/criteria.schema.json tests/test_env_gate.py tests/test_schemas.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(gates): optional env: field for cli-command-runs and run-command

Gates can now specify env: dict in criteria.yaml; merged into os.environ
when dispatching the subprocess. Relative PATH/PYTHONPATH entries
resolve against project dir. User-supplied values override outer env.
Observed in jyctl real run: integration gates needed PYTHONPATH=src
which v0.3 had no way to express."
```

---

## Task 3: Python binary auto-resolution

**Files:**
- Modify: `scripts/measure_python.py`
- Create: `tests/test_python_resolution.py`

- [ ] **Step 3.1: Write failing tests — `tests/test_python_resolution.py`**

```python
"""python binary auto-resolution — bare 'python' in command[] is replaced with
sys.executable so jobs run correctly in environments where only python3 exists.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "measure_python.py"


def run_cli(criteria: str, project: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(project), "--criteria-stdin"],
        input=criteria, capture_output=True, text=True, check=False, timeout=30,
    )
    return json.loads(result.stdout)


def test_bare_python_resolves_to_sys_executable(tmp_path: Path):
    """Command starting with 'python' auto-resolves so environments without
    bare python on PATH still work."""
    criteria = """
gates:
  - id: py_version
    type: run-command
    command: ["python", "-c", "import sys; print('ok')"]
    expect_exit: 0
    expect_stdout_match: "ok"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"


def test_python3_untouched(tmp_path: Path):
    """Non-'python' names pass through unchanged."""
    criteria = """
gates:
  - id: py3_version
    type: run-command
    command: ["python3", "-c", "print('ok3')"]
    expect_exit: 0
    expect_stdout_match: "ok3"
"""
    report = run_cli(criteria, tmp_path)
    # Pass if python3 is on PATH (most environments); skip if not.
    import shutil
    if shutil.which("python3") is None:
        import pytest
        pytest.skip("python3 not on PATH")
    assert report["passed"] is True


def test_opt_out_via_env_marker(tmp_path: Path):
    """SKILLGOID_PYTHON_NO_RESOLVE=1 disables the substitution."""
    criteria = """
gates:
  - id: no_resolve
    type: run-command
    command: ["python", "-c", "print('should-not-run-in-broken-env')"]
    expect_exit: 0
    env:
      SKILLGOID_PYTHON_NO_RESOLVE: "1"
"""
    # On a system with python on PATH this still passes; on a system without,
    # the opt-out means we get a FileNotFoundError → exit 124 or exception.
    # Test is mostly a smoke check that the env marker is honored (no crash).
    report = run_cli(criteria, tmp_path)
    # Either ran (if bare python exists) or failed with a clean FileNotFoundError
    assert report["results"][0]["gate_id"] == "no_resolve"
```

- [ ] **Step 3.2: Run — confirm failure**

```bash
pytest tests/test_python_resolution.py -v
```
Expected: the first test may FAIL if bare `python` isn't on PATH (this is exactly the case we're fixing).

- [ ] **Step 3.3: Update `scripts/measure_python.py`**

Add a helper near `_merge_env`:

```python
def _resolve_python(cmd: list[str], env: dict) -> list[str]:
    """Replace bare 'python' with sys.executable unless opt-out is set."""
    if not cmd:
        return cmd
    if env.get("SKILLGOID_PYTHON_NO_RESOLVE") == "1":
        return cmd
    if cmd[0] == "python":
        return [sys.executable, *cmd[1:]]
    return cmd
```

In `_gate_run_command` and `_gate_cli_command_runs`, apply the resolution right before running:
```python
env = _merge_env(project, gate.get("env") or {})
cmd = _resolve_python(cmd, env)
```

- [ ] **Step 3.4: Run tests**

```bash
pytest -v && ruff check .
```
Expected: 85 + 3 = 88 total, ruff clean.

- [ ] **Step 3.5: Commit**

```bash
git add scripts/measure_python.py tests/test_python_resolution.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(gates): auto-resolve bare 'python' to sys.executable

cli-command-runs and run-command now replace command[0] == 'python'
with sys.executable so jobs work in environments without bare python
on PATH (modern Debian/Ubuntu, minimal containers).

Opt-out via env: SKILLGOID_PYTHON_NO_RESOLVE=1 for niche cases.
Observed in jyctl real run: integration gate's 'python -m jyctl'
failed with FileNotFoundError on an env with only python3 on PATH."
```

---

## Task 4: `feasibility` skill

New skill that pre-flight-checks criteria.yaml gates before the build loop starts. Invoked by `build` between `clarify` and `plan`.

**Files:**
- Create: `skills/feasibility/SKILL.md`

- [ ] **Step 4.1: Write `skills/feasibility/SKILL.md`**

```markdown
---
name: feasibility
description: Use after `clarify` completes (or invokable directly as `/skillgoid:feasibility`) to pre-flight-check every gate in `.skillgoid/criteria.yaml` against the current environment. Catches missing tools, unresolvable commands, and obvious env mismatches before iteration budget burns. Advisory only — user decides to proceed or fix first.
---

# feasibility

## What this skill does

Runs a shallow pre-flight check on every gate (and integration_gate) in `.skillgoid/criteria.yaml` — not a full gate run, just a "can this gate plausibly execute?" check. Surfaces mismatches as a readable report so the user can fix criteria before burning iteration budget on environment issues.

## When to use

- Invoked automatically by `skillgoid:build` on fresh start, between `clarify` and `plan`.
- Invokable directly: `/skillgoid:feasibility` — useful after editing `criteria.yaml` or moving the project to a new environment.

## Inputs

- `.skillgoid/criteria.yaml` — must exist.
- Current working environment (PATH, installed tools, env vars).

## Procedure

1. **Read** `.skillgoid/criteria.yaml`. Extract all gates from `gates[]` and `integration_gates[]`.
2. **For each gate, check by type:**
   - `pytest` → `shutil.which("pytest")` or `python -m pytest --version` succeeds.
   - `ruff` → `_resolve_tool("ruff")` succeeds (prefers venv-sibling, falls back to PATH).
   - `mypy` → same pattern as ruff.
   - `import-clean` → `module` field is non-empty and matches `^[a-zA-Z_][a-zA-Z0-9_.]*$`.
   - `coverage` → `pytest --cov --version` succeeds (verifies pytest-cov is installed).
   - `cli-command-runs`, `run-command` → `command[0]` is resolvable on PATH OR declared in `env:` OR is bare `python` (auto-resolved to sys.executable).
3. **For each gate with `env:`** — check PATH-like values (`PYTHONPATH`, `PATH`): relative paths must resolve under the project dir (`src/` exists if `PYTHONPATH: src` is declared).
4. **Emit a structured report** to stdout (JSON):
   ```json
   {
     "all_ok": bool,
     "checks": [
       {"gate_id": "...", "ok": true|false, "hint": "..."},
       ...
     ]
   }
   ```
5. **Human-readable summary:**
   ```
   feasibility check — N gates, K ok, M failing:
   ✓ pytest: tool found at /path/to/pytest
   ✓ ruff: tool found at .venv/bin/ruff
   ✗ cli_smoke: command 'python' not on PATH (consider python3 or add env:)
   ```
6. **If `all_ok == false`**, ask the user: *"Proceed anyway / fix criteria now / abort?"*. If invoked from `build`, pass the user's choice back so build can either continue to `plan` or stop.
7. **Return** the structured report to the caller.

## What this skill does NOT do

- Run actual gates (no pytest execution, no code written).
- Install missing tools.
- Modify `criteria.yaml` without user consent.
- Check gate output shape (that's for the real loop).

## Failure modes

- Missing `.skillgoid/criteria.yaml`: exit with clear error, suggest `/skillgoid:clarify` first.
- Malformed criteria.yaml: emit `{"all_ok": false, "checks": [{"gate_id": "__parse__", "ok": false, "hint": "yaml parse failed: <msg>"}]}`.

## Output

Markdown report + JSON object. Human reads the markdown; the calling build skill parses the JSON.
```

- [ ] **Step 4.2: Verify frontmatter parses**

```bash
python -c "import yaml; f=open('skills/feasibility/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"
```

- [ ] **Step 4.3: Commit**

```bash
git add skills/feasibility/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(skill): feasibility — pre-flight gate check before build

New skill invoked by build between clarify and plan. Shallow-checks
every gate's prerequisites (tool exists, command resolvable, env paths
make sense) without actually running them. Catches environment
mismatches before iteration budget burns.

Observed from jyctl real run: the 'python vs python3' PATH mismatch
would have been caught before iteration 1 instead of requiring an
integration retry."
```

---

## Task 5: Build orchestrator — wire feasibility + surface unstick

**Files:**
- Modify: `skills/build/SKILL.md`

- [ ] **Step 5.1: Read current file**

The v0.3 build skill has a "### Dispatch — Fresh start" section that invokes retrieve → clarify → plan. Insert feasibility between clarify and plan.

- [ ] **Step 5.2: Insert feasibility step**

In `skills/build/SKILL.md`, find the fresh-start dispatch block (step 2). After the `clarify` invocation and before `plan`, add:

```markdown
   - Invoke `skillgoid:feasibility`. Parse the returned JSON report. If `all_ok == false`, surface the markdown summary to the user. Ask: "Proceed anyway / fix criteria / abort?" — pause until user chooses. Only proceed to `plan` on "proceed" or "fix criteria" (after user edits).
```

- [ ] **Step 5.3: Update stall/budget exit message**

Find step 3e (chunk gate check). Current block surfaces stall/budget_exhausted and lists two recovery options (`build resume` / `build retrospect-only`). Extend to three:

```markdown
   - If `exit_reason` is `"budget_exhausted"` or `"stalled"`: STOP. Do NOT dispatch subsequent chunks. Surface the failure and the summary to the user with recovery options:

     ```
     Chunk <chunk_id> exited with <exit_reason> after <N> iterations.
     Latest failure signature: <sig> — <one-line summary>
     Options:
       • /skillgoid:build resume                 retry with same budget (useful only if env changed)
       • /skillgoid:unstick <chunk_id> "<hint>"  re-dispatch with a human one-sentence hint
       • /skillgoid:build retrospect-only        finalize this project as-is
     ```
```

- [ ] **Step 5.4: Verify frontmatter**

```bash
python -c "import yaml; f=open('skills/build/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"
```

- [ ] **Step 5.5: Full suite + ruff**

```bash
. .venv/bin/activate && pytest -v && ruff check .
```
Expected: 88 total (no code tests added), ruff clean.

- [ ] **Step 5.6: Commit**

```bash
git add skills/build/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(build): wire feasibility step + surface unstick on stall

After clarify, build now invokes skillgoid:feasibility and surfaces
the report to the user before proceeding to plan. User can opt to fix
criteria first, proceed anyway, or abort.

Stall/budget exit message now offers /skillgoid:unstick as a third
recovery option alongside resume/retrospect-only."
```

---

## Task 6: Clarify skill — gitignore + coverage caveat

**Files:**
- Modify: `skills/clarify/SKILL.md`

- [ ] **Step 6.1: Add `.gitignore` proposal sub-step**

In `skills/clarify/SKILL.md`, after step 5.2 (default coverage gate for Python), add:

```markdown
5.3. **Default `.gitignore` for Python projects.** If the project directory has no `.gitignore`, propose adding one (it prevents `__pycache__/`, `.pytest_cache/`, etc. from being committed by `git_iter_commit.py`):

   ```gitignore
   __pycache__/
   *.pyc
   .pytest_cache/
   .ruff_cache/
   .mypy_cache/
   .coverage
   .venv/
   *.egg-info/
   build/
   dist/
   ```

   Add to `.gitignore` if it exists; do not overwrite the user's existing file.
```

- [ ] **Step 6.2: Add subprocess-coverage caveat comment**

In step 5.1 (default integration gate) or step 5.2 (default coverage gate), wherever you propose a `coverage` gate for a CLI project, add this comment to the proposed yaml block:

```markdown
   When proposing both a `pytest` coverage gate AND a `cli-command-runs` gate on the same project, include this comment in the proposed `criteria.yaml`:

   ```yaml
   # NOTE: pytest-cov does not instrument subprocess calls.
   # Combine this coverage gate with in-process CLI tests that call
   # your main(argv) directly with monkeypatched sys.stdin/stdout,
   # not just subprocess-based tests. Otherwise CLI code will
   # register as uncovered and this gate will fail.
   ```

   This prevents the "pytest passes, ruff passes, coverage drops to ~50% on the CLI chunk" failure mode observed on real runs.
```

- [ ] **Step 6.3: Verify frontmatter**

```bash
python -c "import yaml; f=open('skills/clarify/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"
```

- [ ] **Step 6.4: Commit**

```bash
git add skills/clarify/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(clarify): propose default .gitignore + coverage subprocess caveat

Two observed-from-jyctl tweaks:
- For Python projects without .gitignore, propose a minimal one
  covering pycache/ruff/mypy/pytest caches, .venv, build artifacts.
  Without it, the per-iteration git commits carry bytecode noise.
- When proposing coverage + cli-command-runs, include a comment
  warning that pytest-cov does not instrument subprocesses — users
  must add in-process CLI tests or the gate will fail."
```

---

## Task 7: `unstick` skill

**Files:**
- Create: `skills/unstick/SKILL.md`

- [ ] **Step 7.1: Write `skills/unstick/SKILL.md`**

```markdown
---
name: unstick
description: Use when a chunk has stalled or exhausted its budget and the user has a one-sentence hint that would unblock the agent. Invoked as `/skillgoid:unstick <chunk_id> "<hint>"`. Re-dispatches the chunk's subagent with the hint injected into the chunk prompt's integration-failure-context slot, resetting the attempt counter.
---

# unstick

## What this skill does

Given a stuck chunk and a one-sentence human hint, re-dispatches the chunk's subagent with the hint as extra context. Lets a user rescue a stalled loop with minimal intervention — one sentence, not a full manual takeover.

## When to use

- A chunk has exited with `stalled` or `budget_exhausted`.
- The user has a specific correction that would likely unblock the loop (e.g., "the API key env var is `MYAPP_KEY`, not `API_KEY`"; "use `pytest-asyncio` for the async tests"; "the sqlite database path should be relative to cwd, not absolute").

**NOT** for:
- Complex multi-step corrections (use manual intervention + `build resume`).
- Chunks that haven't stalled (use `build resume` instead).

## Inputs

- `chunk_id` — must match an entry in `.skillgoid/chunks.yaml`.
- `hint` — a single sentence. Shorter is better.

## Procedure

1. **Validate chunk_id** — must exist in `.skillgoid/chunks.yaml`. If not, error out.
2. **Read recent state** — the latest iteration for this chunk in `.skillgoid/iterations/`.
   - If `exit_reason` ∈ {`success`} — warn: "this chunk already succeeded. Unstick is for stalled chunks." Ask user to confirm before proceeding.
   - If `exit_reason` ∈ {`stalled`, `budget_exhausted`} — proceed.
   - If `exit_reason == "in_progress"` — the loop is still running or was interrupted. Unstick in this case means "restart with hint" — ask user to confirm.
3. **Check unstick budget** — count prior unstick invocations for this chunk by inspecting `iterations/*.json` records where `unstick_hint` field is present. Cap total unsticks per chunk at 3 (prevents runaway).
4. **Dispatch a fresh chunk subagent** — same dispatch pattern as `build` step 3c, with TWO differences:
   - Inject the `<hint>` into the chunk prompt's `## Integration failure context (populated on integration auto-repair, empty otherwise)` slot (repurpose the v0.2 slot — it was designed for exactly this kind of mid-flight hint injection).
   - Prefix the hint with: `"UNSTICK HINT (from human operator): "` so the subagent knows the source.
5. **Reset the attempt counter.** The subagent starts from iteration N+1 but with `attempt=1` for its internal `max_attempts` tracking. (This is semantic — just don't pass a starting `attempt` arg to `loop`.)
6. **Mark the new iteration record** with `unstick_hint: "<hint>"` so future unstick budget counts can find it.
7. **Continue the build loop** from that point — the subagent returns with a fresh `exit_reason`, and `build` resumes the normal per-chunk loop.

## Output

On success:
```
unstick: chunk <chunk_id> re-dispatched with hint.
Subagent returned: <exit_reason>, iterations_used: N, gates: <summary>
```

On over-budget:
```
unstick: chunk <chunk_id> has already been unstuck 3 times. Break out
with /skillgoid:build retrospect-only or continue manually.
```

## Risks

- If the hint is wrong, the chunk spends a fresh budget getting it wrong in a new way. That's the cost.
- If the hint contradicts criteria.yaml, the subagent will likely revert to criteria-driven behavior on subsequent iterations. Consider editing criteria directly instead for structural disagreements.
```

- [ ] **Step 7.2: Verify frontmatter**

```bash
python -c "import yaml; f=open('skills/unstick/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"
```

- [ ] **Step 7.3: Commit**

```bash
git add skills/unstick/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(skill): unstick — mid-flight hint injection for stalled chunks

New user-invokable skill: /skillgoid:unstick <chunk_id> \"<hint>\".
When a chunk has stalled or budget-exhausted, a one-sentence hint is
injected into the chunk prompt's integration-failure-context slot
(reusing v0.2's slot) and the chunk subagent is re-dispatched with
fresh context. Capped at 3 unsticks per chunk.

Preserves autonomy by reducing the cost of recovery from 'full manual
takeover' to 'one-sentence hint'."
```

---

## Task 8: `stats_reader.py` helper

**Files:**
- Create: `scripts/stats_reader.py`
- Create: `tests/test_stats_reader.py`

- [ ] **Step 8.1: Write failing tests — `tests/test_stats_reader.py`**

```python
"""Tests for scripts/stats_reader.py — reads metrics.jsonl and summarizes."""
import json
import subprocess
import sys
from pathlib import Path

from scripts.stats_reader import summarize, format_report

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "stats_reader.py")]


def _write_metrics(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def _sample(**overrides) -> dict:
    base = {
        "timestamp": "2026-04-17T12:00:00+00:00",
        "slug": "proj",
        "language": "python",
        "outcome": "success",
        "chunks": 3,
        "total_iterations": 4,
        "stall_count": 0,
        "budget_exhausted_count": 0,
        "integration_retries_used": 0,
        "elapsed_seconds": 120,
    }
    base.update(overrides)
    return base


def test_summarize_empty_file(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    path.write_text("")
    s = summarize(path, limit=20)
    assert s["count"] == 0
    assert s["success_rate"] is None


def test_summarize_single_line(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    _write_metrics(path, [_sample()])
    s = summarize(path, limit=20)
    assert s["count"] == 1
    assert s["success_rate"] == 1.0
    assert s["avg_iterations_per_chunk"] == 4 / 3
    assert s["languages"] == {"python": 1}


def test_summarize_mixed_outcomes(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    _write_metrics(path, [
        _sample(slug="a", outcome="success", stall_count=0),
        _sample(slug="b", outcome="partial", stall_count=1),
        _sample(slug="c", outcome="success", integration_retries_used=2),
    ])
    s = summarize(path, limit=20)
    assert s["count"] == 3
    assert s["success_rate"] == 2 / 3
    assert s["stall_rate"] == 1 / 3
    assert s["integration_retry_rate"] == 1 / 3


def test_format_report_produces_markdown(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    _write_metrics(path, [_sample(slug="one"), _sample(slug="two", outcome="partial")])
    s = summarize(path, limit=20)
    md = format_report(s, limit=20)
    assert "# Skillgoid stats" in md
    assert "one" in md
    assert "two" in md
    assert "Success rate" in md


def test_summarize_skips_malformed_lines(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    path.write_text('{"slug": "good", "outcome": "success", "chunks": 1, "total_iterations": 1, "stall_count": 0, "budget_exhausted_count": 0, "integration_retries_used": 0}\n{this is broken json\n')
    s = summarize(path, limit=20)
    assert s["count"] == 1  # only the good line


def test_cli_on_missing_file(tmp_path: Path):
    path = tmp_path / "nonexistent.jsonl"
    result = subprocess.run(
        CLI + ["--metrics-file", str(path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0  # handled gracefully
    assert "no metrics" in result.stdout.lower() or "empty" in result.stdout.lower()
```

- [ ] **Step 8.2: Run — confirm failure**

```bash
pytest tests/test_stats_reader.py -v
```
Expected: 6 FAIL — module not found.

- [ ] **Step 8.3: Implement `scripts/stats_reader.py`**

```python
#!/usr/bin/env python3
"""Skillgoid metrics.jsonl reader and summarizer.

Reads ~/.claude/skillgoid/metrics.jsonl (or --metrics-file override) and
produces a markdown summary. Used by the `stats` skill. Never modifies
the metrics file.

Contract:
    summarize(path: Path, limit: int) -> dict
    format_report(summary: dict, limit: int) -> str

CLI:
    python scripts/stats_reader.py [--metrics-file PATH] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path


def _default_metrics_path() -> Path:
    home = Path(os.environ.get("HOME") or Path.home())
    return home / ".claude" / "skillgoid" / "metrics.jsonl"


def _load_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines: list[dict] = []
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            lines.append(json.loads(raw))
        except Exception:
            continue
    return lines


def summarize(path: Path, limit: int = 20) -> dict:
    lines = _load_lines(path)
    count = len(lines)
    if count == 0:
        return {
            "count": 0,
            "success_rate": None,
            "stall_rate": None,
            "budget_rate": None,
            "integration_retry_rate": None,
            "avg_iterations_per_chunk": None,
            "languages": {},
            "recent": [],
        }

    success = sum(1 for line in lines if line.get("outcome") == "success")
    stalls = sum(1 for line in lines if line.get("stall_count", 0) > 0)
    budget = sum(1 for line in lines if line.get("budget_exhausted_count", 0) > 0)
    integ_retries = sum(1 for line in lines if line.get("integration_retries_used", 0) > 0)

    total_chunks = sum(max(line.get("chunks", 0), 0) for line in lines) or 1
    total_iters = sum(max(line.get("total_iterations", 0), 0) for line in lines)

    languages = Counter(line.get("language") or "unknown" for line in lines)

    # Recent N, newest first
    recent = sorted(
        lines,
        key=lambda line: line.get("timestamp", ""),
        reverse=True,
    )[:limit]

    return {
        "count": count,
        "success_rate": success / count,
        "stall_rate": stalls / count,
        "budget_rate": budget / count,
        "integration_retry_rate": integ_retries / count,
        "avg_iterations_per_chunk": total_iters / total_chunks,
        "languages": dict(languages),
        "recent": recent,
    }


def _pct(f: float | None) -> str:
    return "—" if f is None else f"{f * 100:.1f}%"


def format_report(summary: dict, limit: int = 20) -> str:
    lines = ["# Skillgoid stats", ""]
    if summary["count"] == 0:
        lines.append("_No metrics recorded yet. Run a Skillgoid project through retrospect to populate `~/.claude/skillgoid/metrics.jsonl`._")
        return "\n".join(lines)

    lines.append(f"**{summary['count']} projects tracked**")
    lines.append("")
    lines.append("## Rollups")
    lines.append("")
    lines.append(f"- Success rate: {_pct(summary['success_rate'])}")
    lines.append(f"- Stall rate: {_pct(summary['stall_rate'])}")
    lines.append(f"- Budget-exhaustion rate: {_pct(summary['budget_rate'])}")
    lines.append(f"- Integration-retry rate: {_pct(summary['integration_retry_rate'])}")
    avg = summary["avg_iterations_per_chunk"]
    lines.append(f"- Avg iterations per chunk: {'—' if avg is None else f'{avg:.2f}'}")
    lines.append("")
    lines.append("## Languages")
    lines.append("")
    for lang, n in sorted(summary["languages"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {lang}: {n}")
    lines.append("")

    lines.append(f"## Last {min(limit, summary['count'])} projects")
    lines.append("")
    lines.append("| date | slug | lang | outcome | chunks | iters | stalls | retries | elapsed |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|")
    for line in summary["recent"]:
        date = (line.get("timestamp") or "")[:10]
        slug = line.get("slug") or "—"
        lang = line.get("language") or "—"
        outcome = line.get("outcome") or "—"
        chunks = line.get("chunks", "—")
        iters = line.get("total_iterations", "—")
        stalls = line.get("stall_count", 0)
        retries = line.get("integration_retries_used", 0)
        elapsed = line.get("elapsed_seconds")
        elapsed_str = "—" if elapsed is None else f"{elapsed}s"
        lines.append(f"| {date} | {slug} | {lang} | {outcome} | {chunks} | {iters} | {stalls} | {retries} | {elapsed_str} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid metrics.jsonl reader")
    ap.add_argument("--metrics-file", type=Path, default=_default_metrics_path())
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)

    summary = summarize(args.metrics_file, limit=args.limit)
    sys.stdout.write(format_report(summary, limit=args.limit) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8.4: Run tests**

```bash
pytest tests/test_stats_reader.py -v
```
Expected: 6 tests pass.

- [ ] **Step 8.5: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 88 + 6 = 94 total, ruff clean.

- [ ] **Step 8.6: Commit**

```bash
git add scripts/stats_reader.py tests/test_stats_reader.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(stats): metrics.jsonl reader + summarizer helper

scripts/stats_reader.py reads ~/.claude/skillgoid/metrics.jsonl and
produces a markdown report with rollups (success/stall/budget/retry
rates, avg iterations per chunk), language breakdown, and a
last-N-projects table. Skips malformed lines, handles missing file.

Consumed by the stats skill (Task 9)."
```

---

## Task 9: `stats` skill

**Files:**
- Create: `skills/stats/SKILL.md`

- [ ] **Step 9.1: Write `skills/stats/SKILL.md`**

```markdown
---
name: stats
description: Use when the user wants to see cross-project metrics — success rates, stalls, iterations per chunk, language distribution. Reads `~/.claude/skillgoid/metrics.jsonl` populated by `retrospect` and produces a markdown summary. Read-only; never modifies the metrics file. Invokable as `/skillgoid:stats` or `/skillgoid:stats <N>` for last-N projects.
---

# stats

## What this skill does

Reads the user-global metrics jsonl (populated one line per project by `retrospect` since v0.3) and produces a markdown summary of cross-project performance. Surfaces rollups + a recent-N table.

## When to use

- User asks "how's Skillgoid been performing lately?" / "what's my stall rate?" / "which languages have I built in?".
- After running several projects, to decide where to focus v0.X priorities based on observed failure modes.

## Inputs

- Optional `limit` — how many most-recent projects to show in the table. Default 20.
- Optional `metrics_file` path override — defaults to `~/.claude/skillgoid/metrics.jsonl`.

## Procedure

1. Invoke:
   ```bash
   python <plugin-root>/scripts/stats_reader.py [--limit <N>] [--metrics-file <path>]
   ```
2. The script emits a markdown report on stdout. Pass it through to the user unchanged.

## Output format

```markdown
# Skillgoid stats

**N projects tracked**

## Rollups
- Success rate: 80.0%
- Stall rate: 10.0%
- Budget-exhaustion rate: 5.0%
- Integration-retry rate: 20.0%
- Avg iterations per chunk: 1.50

## Languages
- python: 8
- node: 2

## Last N projects
| date | slug | lang | outcome | chunks | iters | stalls | retries | elapsed |
| 2026-04-17 | jyctl | python | success | 3 | 4 | 0 | 1 | 238s |
...
```

## What this skill does NOT do

- Write to or modify `metrics.jsonl`.
- Render HTML or graphs (that's v0.5+ dashboards work).
- Fetch remote metrics.
```

- [ ] **Step 9.2: Verify frontmatter parses**

```bash
python -c "import yaml; f=open('skills/stats/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"
```

- [ ] **Step 9.3: Commit**

```bash
git add skills/stats/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(skill): stats — user-invokable metrics summary

/skillgoid:stats reads ~/.claude/skillgoid/metrics.jsonl and prints a
markdown summary: success/stall/budget/retry rates, avg iterations
per chunk, language breakdown, last-N-projects table. Wraps
scripts/stats_reader.py.

Closes the observability loop opened by v0.3's metrics.jsonl
scaffolding."
```

---

## Task 10: python-gates skill — note env is honored

**Files:**
- Modify: `skills/python-gates/SKILL.md`

- [ ] **Step 10.1: Add env note**

In `skills/python-gates/SKILL.md`, locate the existing `**Note:**` about the `timeout` field (v0.3 addition). Add a second note just below it:

```markdown
**Note:** gates may also carry an `env:` dict (string → string). The adapter merges it into the subprocess environment. Useful for passing `PYTHONPATH: src` on projects not yet installed via `pip install -e .`. Relative PATH/PYTHONPATH values are resolved against the project dir.
```

- [ ] **Step 10.2: Commit**

```bash
git add skills/python-gates/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(skill): python-gates documents env: field"
```

---

## Task 11: Docs — README + CHANGELOG + roadmap

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/roadmap.md`

- [ ] **Step 11.1: `README.md` — insert "What's new in v0.4" before v0.3 section**

```markdown
## What's new in v0.4

Observed-ROI reprioritization driven by the first real Skillgoid run (jyctl, 2026-04-17):

- **Gate `env:` field.** Gates can now carry an `env:` dict. Lets `cli-command-runs` pass `PYTHONPATH=src` without pre-installing the project.
- **Python binary auto-resolution.** Bare `python` in command lists is replaced with `sys.executable`, fixing environments where only `python3` is on PATH.
- **Pre-plan feasibility skill.** `/skillgoid:feasibility` — invoked automatically between `clarify` and `plan` — shallow-checks every gate's tools and commands against the environment before any iteration budget burns.
- **Unstick skill.** `/skillgoid:unstick <chunk> "<hint>"` — re-dispatch a stalled chunk with a one-sentence human hint injected into the chunk prompt. Autonomy-preservation lever: recovery cost drops from "full manual takeover" to "one sentence."
- **`/skillgoid:stats` reader.** Cross-project metrics summary — success/stall/budget rates, avg iterations per chunk, language breakdown. Reads `~/.claude/skillgoid/metrics.jsonl` (populated by v0.3's `retrospect`).
- **Clarify improvements.** Proposes a default `.gitignore` for Python projects; adds a subprocess-coverage caveat comment when coverage + CLI gates are both in play.

All changes fully backward-compatible with v0.3.

```

- [ ] **Step 11.2: `CHANGELOG.md` — `[0.4.0]` entry**

After the existing header and before `[0.3.0]`:

```markdown
## [0.4.0] — 2026-04-18

### Added
- `scripts/stats_reader.py` — metrics.jsonl summarizer helper.
- Optional `env:` dict on every gate (merged into subprocess env, path values resolved against project dir).
- Python binary auto-resolution: bare `python` in gate commands → `sys.executable`. Opt-out via `SKILLGOID_PYTHON_NO_RESOLVE=1`.
- New skills: `feasibility` (pre-plan gate check), `unstick` (stalled-chunk recovery with hint), `stats` (metrics summary).

### Changed
- `build` skill wires `feasibility` between `clarify` and `plan`; surfaces `/skillgoid:unstick` on chunk stall/budget-exhaustion.
- `clarify` skill proposes default `.gitignore` + subprocess-coverage caveat comment on coverage gates.
- `python-gates` skill documents `env:` field.

### Backward compatibility
- v0.3 `criteria.yaml` / iteration records parse unchanged.
- Missing `env:` → no env override, v0.3 behavior.
- Missing `feasibility` / `unstick` / `stats` skills → never-invoked-implicitly except feasibility (but if the skill is absent, build falls back to direct clarify→plan).

```

- [ ] **Step 11.3: `docs/roadmap.md` — mark v0.4 shipped, define v0.5**

Replace the "## Deferred — v0.4 goals" section with a shipped entry:

```markdown
### v0.4 — Integration Polish & Unstick (2026-04-18)
Observed-ROI reprioritization driven by the first real run (jyctl):
- Gate `env:` field + python binary auto-resolution
- Pre-plan feasibility skill (catches env mismatches before iter 1)
- Unstick skill (one-sentence hint → chunk re-dispatch)
- `/skillgoid:stats` reader for metrics.jsonl
- Clarify: default `.gitignore` + subprocess-coverage caveat
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.4-integration-polish-and-unstick.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.4.md`

## Deferred — v0.5 goals

Items pushed out of v0.4 for lack of real-world evidence. Re-rank after more runs populate `~/.claude/skillgoid/metrics.jsonl`.

### Adaptive / judgment (still highest predicted value)

- **Plan refinement mid-build.** The single biggest predicted complexity-ceiling lever, but zero real-run evidence yet. Architecturally risky (mutable plan during execution). Revisit after a real project hits a mid-flight replan need.

### Scale / throughput

- **Parallel chunks.** Now safer with v0.2's integration gate. Wall-clock wins on multi-chunk independent work.
- **Polyglot / multi-language projects.** Per-chunk adapter + vault across languages. Unlocks full-stack projects.

### Observability extensions

- **Rehearsal mode** — dry-run each chunk's first iteration before committing chunks.yaml. May overlap with v0.4's feasibility — revisit only if feasibility proves insufficient.
- **Dashboards / HTML rendering.** `/skillgoid:stats` markdown is enough until metrics.jsonl has 20+ entries.

### Quality / safety

- **Tighter vault retrieval.** Extract the 3–5 most relevant vault sections per goal instead of reading whole files. Only matters at vault scale (50+ projects).

### Ecosystem

- **More language adapters** (`node-gates`, `go-gates`, `rust-gates`).
- **Gate type plugins** — third-party-contributable gate types without editing `measure_python.py`.

## How to pick up v0.5

After v0.4 has landed and run on a few real projects:
1. Run `/skillgoid:stats` on accumulated metrics.
2. Look for the most common failure modes in the table.
3. Re-rank v0.5 items by what actually broke.
4. Spec the top 2–3 by observed ROI.
```

- [ ] **Step 11.4: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 94 total, ruff clean.

- [ ] **Step 11.5: Commit**

```bash
git add README.md CHANGELOG.md docs/roadmap.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "docs: v0.4 release notes + roadmap refresh

README gains 'What's new in v0.4' summary. CHANGELOG adds [0.4.0]
entry. Roadmap moves v0.4 into Shipped, defines v0.5 with
plan-refinement, parallel chunks, polyglot, tighter retrieval, more
adapters, gate plugins, dashboards — re-rank those by observed ROI
from /skillgoid:stats once enough metrics have accumulated."
```

---

## Task 12: Optional — manual smoke test

**Files:**
- None (manual QA).

- [ ] **Step 12.1: Run `/skillgoid:stats` against the jyctl run's metrics**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
. .venv/bin/activate
python scripts/stats_reader.py
```

Expected: prints a markdown report with 1 project (jyctl, success, 3 chunks, 4 iterations, 1 integration retry, etc.). Confirms the reader works on real data.

- [ ] **Step 12.2: Run feasibility against jyctl's criteria**

```bash
# No code yet for feasibility — it's prose-only in v0.4.
# Manual check: the feasibility skill's procedure should be readable
# and a human should be able to follow it against /home/flip/Development/skillgoid-test/jyctl/.skillgoid/criteria.yaml
cat skills/feasibility/SKILL.md
```

- [ ] **Step 12.3: No commit — manual QA only**

---

## Self-review

**Spec coverage check (against v0.4 spec §3):**

- §3.1 Gate `env:` field → Task 2
- §3.2 Python binary auto-resolution → Task 3
- §3.3 Pre-plan feasibility skill → Task 4 (skill) + Task 5 (build wires it)
- §3.4 Clarify improvements → Task 6
- §3.5 Unstick skill → Task 7
- §3.6 Build orchestrator surfaces unstick → Task 5
- §3.7 `/skillgoid:stats` reader → Task 8 (helper) + Task 9 (skill)

Open question resolutions (spec §9):
1. Feasibility depth — Task 4 procedure explicitly says "binary exists + one lightweight invocation" per tool. ✓
2. Feasibility blocking vs. advisory — Task 5 says advisory with user confirm. ✓
3. `.gitignore` proposal — Task 6 says never overwrite existing. ✓
4. Unstick reset behavior — Task 7 says attempt counter resets but total unsticks capped at 3. ✓
5. Stats format — Task 8/9 says rollups as text, recent-N as table, default 20. ✓

**Placeholder scan:** every task has concrete code or exact prose. No "TBD". The `<plugin-root>` in skill prose is the conventional placeholder Claude resolves at runtime via `CLAUDE_PLUGIN_ROOT` env — consistent with v0.2/v0.3 conventions.

**Type/name consistency:**
- `summarize(path, limit) -> dict` + `format_report(summary, limit) -> str` (Task 8) — matches test imports (Task 8).
- `_merge_env(project, gate_env) -> dict` + `_resolve_python(cmd, env) -> list[str]` (Tasks 2 & 3) — internal to measure_python.py, consistent.
- Gate `env:` field value type: `object` with `additionalProperties: {type: string}` — matches schema test (Task 2) and Python handler (Task 2).
- Unstick hint slot: repurposes v0.2's "Integration failure context" section in the chunk subagent prompt template — verified by re-reading skills/build/SKILL.md from v0.2/v0.3 commits.

No gaps. No drift.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-skillgoid-v0.4.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
