# Skillgoid v0.11 — Oracle Validation for Synthesized Gates

**Version:** 0.10.0 → 0.11.0

**Depends on:** v0.10.0 (`synthesize-gates` skill with canonicalized `type: coverage`, cache-dir analogue clones, collapsed coverage drafts).

**Precedent:** `docs/superpowers/specs/2026-04-19-skillgoid-self-authored-gates-design.md` — Stage 3 "Validate — oracle with graceful degradation" was deferred from Phase 1 / v0.10. This spec adopts its classification scheme and adapts it to the v0.10 infrastructure.

## Problem

Every gate in today's `criteria.yaml.proposed` carries the literal comment `# validated: none (Phase 1: oracle validation deferred)`. The user is the only validator. The v0.10 dogfood run confirmed that synthesized gates are shaped correctly, but offered no answer to "will this gate discriminate a working project from a broken one?" — which is the first question a reviewer actually asks.

Consequences:

- **Low review trust.** Users ship hand-edits to the proposed criteria defensively because nothing in the file has been exercised.
- **No early detection of malformed commands.** A typo like `pytest tetsts/` survives schema validation and the subagent's own self-check; the user discovers it only on the first `/skillgoid:build` loop iteration.
- **No discrimination signal.** A gate that passes against a legit project but also passes against an empty scaffold (e.g., `pytest` with `-p no:cacheprovider` and zero tests) is smoke-only and should be flagged.

## Goal

Each synthesized gate carries a `validated:` label that reflects a real execution against two environments:

- **should-pass:** the analogue repo's checkout in `~/.cache/skillgoid/analogues/<slug>/`.
- **should-fail:** a minimal tmpdir scaffold that contains no real code — just the minimum structure the gate type needs to be exerciseable.

A gate that passes should-pass and fails should-fail is `validated: oracle` — the user can trust it discriminates. Any other outcome surfaces a per-gate warn label so the user sees the specific failure mode before editing.

## Non-goals

- **Non-Python oracle.** v0.11 only wires oracle validation to `skills/python-gates`. Other language skills inherit the adapter-reuse pattern when they ship.
- **Auto-install of analogue dependencies.** Oracle runs use the user's current Python environment. If the analogue's test deps aren't importable, the gate fails and the warn label tells the user what to do.
- **Per-analogue virtualenv management.** Deferred; see `validated: none` UX below.
- **Parallel oracle runs across gates.** Serial execution is simpler and fits the 10-minute total-stage budget.
- **Oracle for context7- or template-sourced gates.** v0.11 grounds only from analogues (Phase 1 invariant); context7/template oracle handling lands with Phase 2 v0.13/v0.14.
- **Auto-retry on oracle failure.** If oracle fails, the gate gets `validated: none` and a warn label. User re-runs after addressing the cause.
- **Any change to `skills/build/SKILL.md` or the build loop.** Oracle affects only synthesis-time label rendering, not runtime gate execution.

## Design

### D1 — Adapter reuse, not a new runner

Oracle validation invokes the existing language-gates adapter — for v0.11, `scripts/measure_python.py` — against a project path and a criteria subset. Each oracle run is:

```python
adapter_result = measure_python.run(project=<path>, criteria={"gates": [<one_gate>]})
# adapter_result.results[0].passed is the exit signal for this environment
```

Running the adapter twice (once in the analogue cache-dir, once in the should-fail scaffold tmpdir) and comparing `passed` booleans is the full oracle. No new gate-type execution logic. Timeouts, env handling, `SKILLGOID_PYTHON` injection, hint text — all inherited.

**Coverage-gate oracle semantics (D3 below) is the one deviation:** `type: coverage` gates are considered oracle-passed if the adapter returns a coverage percentage (any non-None value), regardless of whether that percentage meets `min_percent`. Comparing against `min_percent` is the build-loop's job; oracle only checks exerciseability.

### D2 — Don't auto-install analogue dependencies

Oracle runs the adapter with the caller's `sys.executable`. If the analogue's test stack isn't importable (e.g., `from flask import Flask` fails), the adapter's per-gate result will carry a failing stderr excerpt.

In that case the classification is `validated: none` with a warn like:

```
warn: oracle run failed — likely missing analogue deps.
      To validate this gate: cd ~/.cache/skillgoid/analogues/<slug>/ && pip install -e '.[dev]'
      Then re-run: /skillgoid:synthesize-gates --validate-only
```

Rationale: tmpdir venv management triples v0.11's surface area, and most users run oracle from inside an already-active venv where the analogue's deps either already exist or are one `pip install` away. The warn label puts the install instructions in the user's face without guessing at their env layout.

### D3 — `type: coverage` oracle = "produces a number"

A coverage gate's adapter result carries a measured percentage in `stdout` (and the adapter's pass/fail is evaluated against `min_percent`). For oracle we do NOT want to assert `≥ min_percent`: many analogues have less-than-perfect coverage, and oracle's job is to prove the gate is runnable, not that the user's analogue meets the proposed threshold.

**Oracle rule for `type: coverage`:**
- Should-pass run counts as PASS if the adapter produced a coverage percentage (i.e., pytest-cov ran to completion), regardless of the percentage's relationship to `min_percent`.
- Should-fail run counts as FAIL if pytest-cov returns 0% or errors (empty scaffold has no code to cover).
- If should-pass produced a number and should-fail produced 0% / error → `validated: oracle`.
- If both produced numbers > 0 → `validated: smoke-only` (rare; implies the scaffold accidentally has covered code, probably a bug in scaffold generation — treat as smoke-only and warn).
- If should-pass errored (e.g., pytest-cov not installed) → `validated: none, warn: coverage tooling not exerciseable on analogue`.

This semantic diverges from every other gate type's exit-code semantics — worth a comment in `validate.py` that says so.

### D4 — Should-fail scaffold composition

The should-fail scaffold is a freshly-created tmpdir. Its contents are determined by the gate's `type`, just enough to let the adapter execute without a setup error (so the gate fails for *content* reasons, not *structural* reasons):

| Gate type | Scaffold contents |
| --- | --- |
| `pytest` | `tests/` (empty dir); no conftest, no test files |
| `ruff` | `src/__init__.py` (empty); `pyproject.toml` with `[tool.ruff]` from the analogue (for `line-length` parity) |
| `mypy` | `src/__init__.py` (empty); `pyproject.toml` with `[tool.mypy]` from the analogue if present |
| `coverage` | `tests/` (empty); `src/` (empty); `pyproject.toml` with `[tool.pytest.ini_options] testpaths = ["tests"]` |
| `cli-command-runs` | `pyproject.toml` with `[project.scripts]` stub pointing to `src/app.py:main`; `src/app.py` with `def main(): raise SystemExit(1)` |
| `run-command` | empty tmpdir (the gate's command provides everything it needs) |
| `import-clean` | `src/<package>/__init__.py` that does `raise ImportError("scaffold")` |

Under this table, "pass should-fail" for most types means the adapter's structural checks succeed but the content check fails — e.g., pytest finds no tests → non-zero exit; ruff finds no code → zero exit (ruff of nothing is clean). The `ruff` row is the edge case: `ruff check src/` over empty `__init__.py` passes. That's OK — it means the gate is `smoke-only` for ruff-against-empty, which is accurate and gets surfaced as a warn.

Scaffold generation lives in `scripts/synthesize/_scaffold.py` with one factory per gate-type. Keeping it data-driven (the table above encoded as dict literals) keeps adding new types mechanical.

### D5 — Multi-analogue: oracle runs against the draft's first `ref`

A draft gate's `provenance.ref` is either a string or (post-v0.10 collapse) a list of strings. Each ref has the form `<analogue-slug>/<path>` where the slug maps to a directory under `~/.cache/skillgoid/analogues/<slug>/`.

Oracle picks the **first** ref's slug and runs should-pass against that analogue's cache-dir. No cross-analogue comparison. A gate synthesized from two analogues gets oracle-validated against one; the other serves only as provenance documentation.

Rationale: the dominant case in v0.10 is single-analogue synthesis. Multi-analogue support exists but is rare, and the honest "we only oracled against the first" is better than the complexity of defining "oracle against all" semantics.

### D6 — Flags: `--skip-validation` and `--validate-only`

Two new flags on the `synthesize-gates` SKILL invocation:

- `--skip-validation` — Stage 3 is bypassed entirely. Every gate gets `validated: none, warn: validation skipped by --skip-validation`. Escape hatch for offline work, broken analogues, or time-pressured first runs. Maps 1:1 to the original design.
- `--validate-only` — Skips Stages 1, 2. Reads the existing `.skillgoid/synthesis/grounding.json` + `.skillgoid/synthesis/drafts.json`, runs Stage 3, and re-runs Stage 4 to refresh `.skillgoid/criteria.yaml.proposed` with updated labels. Requires both JSON artifacts to exist; errors out with a clear message if either is missing (indicating the user should run the full skill at least once first). Supports the D2 iteration loop where the user installs analogue deps and re-runs oracle without burning another subagent dispatch.

Both flags are forwarded by the SKILL.md to the underlying scripts. `--validate-only` is implemented as a short-circuit in SKILL.md's procedure: if set, skip to step 7 (Stage 3).

### Classification table (inherited, adapted)

| should-pass | should-fail | label | warn (rendered as YAML comment) |
| --- | --- | --- | --- |
| pass | fail | `validated: oracle` | — |
| pass | pass | `validated: smoke-only` | `scaffold also passes; consider tightening` |
| fail | — | `validated: none` | `should-pass failed: <first 200 chars of stderr>` |
| timeout | — | `validated: none` | `timeout after <gate.timeout or 90>s on analogue` |
| adapter internal (exit 2) | — | `validated: none` | `adapter internal error: <stderr excerpt>` |

Per-gate default timeout: 90 seconds (matches original design). Adapter already respects `gate.timeout` when set. Total Stage 3 wall-clock cap: 10 minutes; remaining gates labeled `validated: none, warn: Stage 3 stage-timeout exceeded`.

### Rendered output

`write_criteria.py` extends `_gate_comment_block` to emit the validated label + optional warn. For a gate with `validated: oracle`:

```yaml
  # source: analogue, ref: mini-flask-demo/.github/workflows/test.yml
  # validated: oracle
  - id: ruff_check
    type: ruff
    ...
```

For a gate with a warn:

```yaml
  # source: analogue, ref: mini-flask-demo/pyproject.toml#tool.coverage.report
  # validated: none
  # warn: oracle run failed — likely missing analogue deps. ...
  - id: coverage_main
    type: coverage
    min_percent: 95
```

The multi-ref `refs:` block from v0.10 renders above the validated line.

### Data flow

```
[analogue cache] + [drafts.json]          (v0.11 NEW)
  ↓                                         ↓
  ────── validate.py ──── validated.json
           per-gate:
             1. build should-fail scaffold (type-driven)
             2. run adapter against analogue cache-dir
             3. run adapter against scaffold
             4. classify → label + optional warn
             5. accumulate with 10-min total cap

validated.json → write_criteria.py → criteria.yaml.proposed
                         (now renders validated: label and warn comments)
```

`grounding.json` and `drafts.json` are unchanged on disk. `validated.json` is new:

```json
{
  "schema_version": 1,
  "gates": [
    {
      "id": "ruff_check",
      "validated": "oracle",
      "warn": null,
      "oracle_run": {
        "should_pass": {"passed": true, "duration_ms": 1420},
        "should_fail": {"passed": false, "duration_ms": 830}
      }
    },
    {
      "id": "coverage_main",
      "validated": "none",
      "warn": "oracle run failed — likely missing analogue deps. ...",
      "oracle_run": {"should_pass": {"passed": false, "duration_ms": 210}, "should_fail": null}
    }
  ]
}
```

## Architecture

### New script: `scripts/synthesize/validate.py`

Responsibilities:

1. Read `.skillgoid/synthesis/drafts.json` + the set of analogue slugs from `grounding.json` (to map refs to cache-dir paths).
2. For each draft, invoke the should-pass adapter run, then the should-fail adapter run (against a freshly-built scaffold from `_scaffold.py`).
3. Classify per the table; accumulate into `validated.json`.
4. Respect the 10-minute stage cap via `time.monotonic()` checks between gates.

CLI surface:

```
python scripts/synthesize/validate.py \
    --skillgoid-dir .skillgoid \
    [--skip-validation] \
    [--stage-timeout-sec 600]
```

Exit codes: 0 on clean run (regardless of per-gate labels); 2 on internal error (can't read drafts.json, adapter missing).

### New script: `scripts/synthesize/_scaffold.py`

`build_scaffold(gate_type: str, gate: dict, analogue_cache_dir: Path | None) -> Path` — creates a tmpdir, populates it per the D4 table, returns the path. Caller is responsible for `shutil.rmtree` after use (or `tempfile.TemporaryDirectory` context manager wrapping).

For gate types that need parity with the analogue (`ruff` line-length, `mypy` strict), the function reads the analogue's `pyproject.toml` and copies just the relevant `[tool.*]` section into the scaffold's pyproject. This keeps the should-fail run configuration-equivalent to should-pass, so a failure there is signal about the project's code, not a config mismatch.

### Modified: `scripts/synthesize/write_criteria.py`

`_gate_comment_block` gains access to `validated.json` and renders `# validated: <label>` and (if present) `# warn: <text>` lines after the existing `# source:` / `refs:` block. If `validated.json` is absent (the `--skip-validation` path where validate.py ran and wrote `validated: none` for every gate), the label is still rendered — just uniformly `none`.

### Modified: `skills/synthesize-gates/SKILL.md`

Procedure gains step 7:

```
7. Run Stage 3 (validate). Shell out:

   python <plugin-root>/scripts/synthesize/validate.py \
       --skillgoid-dir .skillgoid

   Forward --skip-validation from the invocation if set.
   If Stage 3 exits non-zero, surface its stderr and STOP.
```

Step 8 is the existing Stage 4 write. The `--validate-only` short-circuit lives at the top of the procedure: if the flag is set, verify `.skillgoid/synthesis/drafts.json` exists, then jump to step 7.

Phase 1/Phase 2 limitations block updates to remove the `validated: none` bullet and replace it with `v0.11 oracle validates single-analogue-cited gates; context7/template sources still emit validated: none pending v0.13/v0.14`.

### Modified: `schemas/`

No schema changes. `validated` is a YAML comment, not a schema field. `validated.json` is an internal artifact and doesn't need a published schema.

## File structure

```
scripts/synthesize/
├── _common.py                  (unchanged)
├── _scaffold.py                (NEW)
├── ground.py                   (unchanged)
├── ground_analogue.py          (unchanged)
├── synthesize.py               (unchanged)
├── validate.py                 (NEW)
└── write_criteria.py           (renders validated/warn comments)

skills/synthesize-gates/
├── SKILL.md                    (step 7 + --skip-validation + --validate-only)
└── prompts/synthesize.md       (unchanged)

tests/
├── test_scaffold.py            (NEW: per-gate-type scaffold contents)
├── test_validate.py            (NEW: classification table, stage timeout, --skip-validation)
├── test_synthesize_e2e.py      (extended: asserts validated: oracle for the canonical coverage gate)
└── fixtures/synthesize/
    └── mini-flask-demo/        (unchanged — already exercises the e2e path)
```

## Testing strategy

**Unit:**

- `test_scaffold.py` — for each row of D4's table, assert the generated tmpdir contains the expected files. Edge case: scaffold for a gate-type not in the table errors with a clear message.
- `test_validate.py` — classification: mock adapter to return each row of the classification table; assert the written `validated.json` label + warn match. Cover the 10-min stage-timeout short-circuit. Cover `--skip-validation`.

**Integration (mocked adapter):**

- `test_validate.py::test_validate_uses_real_adapter_against_fixture` — run validate.py against the real `tests/fixtures/synthesize/mini-flask-demo/` with measure_python as the adapter. Assert the pytest and ruff gates land `validated: oracle`, assert coverage gate lands either `validated: oracle` (if pytest-cov is importable in the test env) or `validated: none, warn: <deps>` (if not) — test tolerates both.

**End-to-end:**

- Extend `test_synthesize_e2e.py::test_e2e_canonical_coverage_gate` to assert the rendered `criteria.yaml.proposed` contains `# validated:` lines for every gate. Don't assert the exact label (env-dependent); assert the line is present and uses one of `oracle | smoke-only | none`.

## Risks

- **Adapter concurrency bugs on repeated invocation.** We call `measure_python` twice per gate, back-to-back. If the adapter has hidden state (e.g., leaving files in `/tmp`), the second run could interact with the first. Mitigation: `validate.py` creates each scaffold in a fresh `TemporaryDirectory` and the adapter has never been shown to leak state in prior dogfood. Testing covers back-to-back runs explicitly.
- **Analogue missing from cache-dir.** If a user runs `--validate-only` after `rm -rf ~/.cache/skillgoid/`, oracle will fail for every gate. `validate.py` detects this up front and exits with a clear `"analogue <slug> missing from cache; re-run /skillgoid:synthesize-gates without --validate-only"`.
- **Scaffold config divergence from analogue.** If D4's scaffold copies only `[tool.ruff]` and the analogue's real config lives in `ruff.toml`, the scaffold won't match and should-fail may misbehave. Mitigation: v0.11 reads from `pyproject.toml` only; standalone `ruff.toml` / `mypy.ini` support can come later if we see real repos needing it. Document the limitation in SKILL.md.
- **Oracle run time on large analogues.** A pytest run over a 5000-test analogue easily exceeds 90 seconds. Per-gate timeout is user-tunable via `gate.timeout`; the original synthesis subagent prompt already teaches it to set sensible timeouts. If oracle times out, the gate gets `validated: none, warn: timeout after Ns` — accurate, actionable.
- **User reads `validated: oracle` as "this gate is correct".** It's not — it's "this gate discriminates the analogue from an empty scaffold." That's a strong signal but not proof of correctness. SKILL.md's render block should include a short explainer comment at the top of `criteria.yaml.proposed` that says so.

## Backward compatibility

- **Existing `.skillgoid/criteria.yaml`** — unchanged. The build loop doesn't consult `validated:` comments; they're purely informational.
- **Existing `.skillgoid/synthesis/drafts.json`** — unchanged on disk. `validate.py` only reads it.
- **Existing `criteria.yaml.proposed` files from v0.10** — stay valid. On the next synthesis run they're overwritten with the new label block; no migration needed.
- **`--skip-validation`** — new but optional. Absent flag = Stage 3 runs as default.
- **Pre-v0.11 callers of `write_criteria.py`** (none outside the SKILL.md) — CLI signature gains no required args. Missing `validated.json` → writer emits `validated: none` for every gate, never crashes.

## Success criteria

After v0.11:

1. `/skillgoid:synthesize-gates <local-analogue-path>` against `tests/fixtures/synthesize/mini-flask-demo/` produces a `criteria.yaml.proposed` where each gate block has a `# validated:` line.
2. For the fixture, the pytest and ruff gates carry `validated: oracle` (they discriminate empty scaffold from the fixture's own code).
3. Re-running with `--skip-validation` produces the same file but every gate lands `validated: none, warn: validation skipped by --skip-validation`.
4. `/skillgoid:synthesize-gates --validate-only` after hand-editing `drafts.json`'s draft IDs re-runs Stage 3 in under 30 seconds for the fixture (no subagent dispatch).
5. Total added test count ~20 (roughly: 7 scaffold rows, 5 classification rows, 2 stage-timeout cases, 3 flag/edge cases, 3 e2e extensions).
6. No regressions in the existing 322 tests.

## Open questions (to resolve in the implementation plan)

- **Scaffold config source priority.** If both `pyproject.toml` and a standalone `ruff.toml` exist in the analogue, which does the scaffold copy? v0.11 picks `pyproject.toml` only (per "Risks" above); revisit if a dogfood run against a real repo with `ruff.toml` surfaces the gap.
- **Does `measure_python.run()` expose a Python API, or does oracle have to shell out to the script?** If the API is available, `validate.py` calls it directly. If not, `subprocess.run([sys.executable, "scripts/measure_python.py", ...])` — functionally identical; marginal perf cost per gate. Resolve in Task 1 of the plan.
- **Stage-timeout behavior on partial progress.** If gate 3 of 6 times out at 10 minutes, are gates 4-6 labeled or omitted? v0.11 answer: labeled `validated: none, warn: Stage 3 stage-timeout exceeded`, written to the file. Keeps the user's mental model of "every drafted gate appears in the output" intact.
