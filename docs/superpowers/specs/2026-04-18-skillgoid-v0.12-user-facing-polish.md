# Skillgoid v0.12 — User-Facing Polish Bundle

**Status:** spec
**Date:** 2026-04-18
**Predecessor:** v0.11.0 (Machinery Reliability Bundle, tag `v0.11.0` at commit `16cd79c`)
**Purpose:** Close the user-visible rough edges surfaced by the v0.8 `minischeme` and v0.9 `chrondel` stress runs — silent long runs, expensive post-mortems, lost lessons on stall, and opaque recovery actions — by adding two read-only observability skills, automating partial-retrospective, and adding a dry-run preview to unstick.

## Problem statement

Four user-facing pain points have been observed across the v0.8 / v0.9 stress runs and subsequent real-world use. Each is language-agnostic; none requires new orchestrator logic or schema changes.

- **P1 — Silent long runs.** During a multi-chunk wave, the user sees `Agent: working...` for minutes with no sense of which chunk is on which iteration, which gates are failing, or which chunks are still pending. `/skillgoid:stats` is cross-project only — there is no per-project in-flight view. Users resort to tailing `iterations/*.json` by hand.

- **P2 — Post-mortem cost.** When a chunk stalls, understanding *why* requires reading 3–5 iteration JSON files and mentally diffing `gate_report` / `failure_signature` / `reflection` across them. The information is all present in the files; it is just not shaped for human reading.

- **P3 — Lost lessons on stall / budget_exhausted.** `retrospect` is currently only invoked when every chunk succeeds (or via explicit `/skillgoid:build retrospect-only`). Any terminal failure short of success silently drops the retrospective — no `retrospective.md` is written, no line is appended to `metrics.jsonl`, no vault curation happens. The information most likely to teach future runs is the information most likely to be lost.

- **P4 — Opaque recovery.** `/skillgoid:unstick <chunk_id> "<hint>"` commits the user immediately: the subagent is re-dispatched, attempt counter reset, iteration budget consumed. Users who want to preview what the hint-injected prompt will look like have no option short of reading the `unstick` skill prose and imagining it.

## Design principles

- **Every deliverable is language-agnostic.** Scripts read the generic iteration / chunks / integration schemas; no assumption about which adapter is in use. Aligns with the multi-language roadmap (v0.15+ TypeScript adapter).
- **Script-driven extraction, not AI synthesis.** Both new observability skills shell out to pure-Python scripts that emit structured markdown. Matches the v0.11 principle of moving fragile prose into deterministic, unit-testable scripts. Zero token cost per invocation; fully testable; consistent output across runs.
- **No new state, no schema changes.** Every deliverable is a read (observability) or a one-line behavioral tweak (auto-retrospect trigger, unstick dry-run flag) on top of existing files.
- **Additive and backward-compatible.** Existing `criteria.yaml`, `chunks.yaml`, iteration records, and hook behavior unchanged. Existing `retrospect` skill and `metrics_append.py` unchanged.

## Deliverables

### 1. `/skillgoid:status` — in-flight progress view

**New skill:** `skills/status/SKILL.md`
**New script:** `scripts/status_reader.py`

Reads `.skillgoid/iterations/`, `.skillgoid/chunks.yaml`, and `.skillgoid/integration/` (if present) in the current working directory. Emits a markdown snapshot of the current project's state.

**CLI:**
```
python scripts/status_reader.py [--skillgoid-dir .skillgoid]
```

**Output (example):**
```markdown
# Skillgoid status — <cwd basename>

**Phase:** per-chunk waves (wave 2 of 3 active)

## Chunks
| chunk_id  | wave | state        | iter | latest gate state       | files touched    |
|-----------|------|--------------|------|-------------------------|------------------|
| scaffold  | 1    | success      | 1    | all pass                | 4 files          |
| parser    | 2    | stalled      | 3    | pytest_unit FAIL        | src/parser.py    |
| formatter | 2    | in_progress  | 2    | ruff pass, pytest ?     | src/format.py    |
| renderer  | 3    | pending      | —    | —                       | —                |

## Latest integration attempt
- Attempt 1 (2026-04-18T10:01:00Z) — FAILED
  - Gate `integration_check` stderr: `src/parser.py:42: AssertionError...` (truncated)
```

**Logic:**
- Project label = `Path.cwd().name` (basename of the directory containing `.skillgoid/`). No dependency on `goal.md` content.
- Waves computed via `scripts/chunk_topo.py`'s existing wave computation (reuse, don't reimplement).
- Per chunk: glob `.skillgoid/iterations/<chunk_id>-*.json`; pick latest by `mtime` (same convention as `gate-guard.sh` post-v0.9). If no iteration exists, state is `pending`.
- `state` column mapped from latest iteration's `exit_reason`: `success`, `in_progress`, `stalled`, `budget_exhausted`, or `pending` if no record.
- `latest gate state` summarized from `gate_report.results`: e.g., `ruff pass, pytest_unit FAIL`. Show at most 3 gate names; append `(+N more)` if truncated.
- `files touched` from iteration's `changes.files_touched`; truncate to 2 paths plus `(+N more)` summary.
- Integration section rendered only if `.skillgoid/integration/` exists and contains `*.json` files; shows latest attempt by `mtime`.
- On missing `.skillgoid/` → exit 1 with `"not a Skillgoid project"` on stderr.

**Skill prose (`skills/status/SKILL.md`):** thin wrapper. Invokes the script, passes stdout through to the user unchanged. No LLM synthesis.

### 2. `/skillgoid:explain <chunk_id>` — iteration timeline

**New skill:** `skills/explain/SKILL.md`
**New script:** `scripts/explain_chunk.py`

Reads all `.skillgoid/iterations/<chunk_id>-*.json` in order. Emits a compact timeline + verbatim reflections.

**CLI:**
```
python scripts/explain_chunk.py --chunk-id <id> [--skillgoid-dir .skillgoid]
```

**Output (example):**
```markdown
# Chunk `parser` — 3 iterations

## Timeline
| iter | gate state        | files touched  | first stderr / hint                         | exit_reason | sig       |
|------|-------------------|----------------|---------------------------------------------|-------------|-----------|
| 1    | pytest_unit FAIL  | src/parser.py  | AssertionError in test_parse_iso            | in_progress | a1b2c3d4  |
| 2    | pytest_unit FAIL  | src/parser.py  | AssertionError in test_parse_iso (same)     | in_progress | a1b2c3d4  |
| 3    | pytest_unit FAIL  | src/parser.py  | AssertionError in test_parse_iso (same)     | stalled     | a1b2c3d4  |

## Stall signal
Signature `a1b2c3d4` repeated 3 times — loop detected no-progress at iteration 3.

## Reflections
### Iteration 1
<reflection text verbatim from iteration record>

### Iteration 2
<reflection text verbatim from iteration record>

### Iteration 3
<reflection text verbatim from iteration record>
```

**Logic:**
- `first stderr / hint`: first line from the first failing gate's `stderr` (falls back to `hint` if `stderr` is empty), truncated to 80 characters. Append `(same)` if identical to prior iteration's first-stderr.
- `sig`: first 8 chars of `failure_signature`; `—` if field is missing.
- `Stall signal` section: emitted only if any two consecutive iterations share a `failure_signature`. States which signature repeated, how many times, and at which iteration stall was flagged.
- `Reflections` section: each iteration's `reflection` field verbatim under its own subheading. Omit if empty.
- On missing chunk_id in the project → exit 1 with `"no iteration files for chunk <id>"` on stderr.

**Skill prose (`skills/explain/SKILL.md`):** thin wrapper. Invokes the script with the given chunk_id, passes stdout through unchanged.

### 3. Auto-partial-retrospective

**Edit to `skills/build/SKILL.md`:** add a new step that invokes `retrospect` automatically on any terminal state, not just success.

**Current behavior:** `retrospect` is invoked only when all per-chunk gates pass and integration passes. On stall or budget-exhaust, `build` surfaces a summary to the user and exits without calling `retrospect`.

**New behavior:** auto-retrospect is scoped to the `build` invocation modes that actually run the loop — `/skillgoid:build "<goal>"` (new project) and `/skillgoid:build resume` (continuation). When either mode reaches a terminal state (success, stalled, or budget_exhausted), `build` invokes `retrospect` exactly once before surfacing the final summary.

**Modes that do NOT auto-invoke retrospect:**
- `/skillgoid:build retrospect-only` — already invokes retrospect as its entire purpose; auto-invoke would double-call.
- `/skillgoid:build status` — read-only subcommand, no loop run, no terminal state reached.

**Additional skip condition:** if no iteration records exist under `.skillgoid/iterations/` (e.g., clarify/plan phase aborted before any loop dispatch), skip auto-retrospect — there is nothing to retrospect on.

**Slug source for `metrics_append.py`:** the auto-invoke path passes `--slug <cwd basename>` (same convention as section 1 of this spec). Manual `retrospect-only` and direct `/skillgoid:retrospect` invocations continue to accept the slug as today.

**No changes to `retrospect/SKILL.md` or `metrics_append.py`:**
- `retrospect` already emits `outcome: partial` for projects with any chunk in `stalled` / `budget_exhausted` state (locked in by v0.10 test H9).
- `retrospect` already writes `retrospective.md` with `## Outcome` set to `success | partial | abandoned`.
- `metrics.jsonl` remains append-only; a subsequent `build resume` after unstick will append a fresh line with the new outcome. Users viewing `stats` see multiple entries for the same `slug` — dedup-by-slug display is an explicit v0.13+ concern.

**Trigger placement in `build/SKILL.md`:** the new step lives just before the "surface final summary to user" step, and after the per-wave / integration loops have terminated. The existing "all chunks succeeded → invoke retrospect" branch becomes a no-op (superseded by the always-invoke rule).

### 4. Unstick dry-run

**Edit to `skills/unstick/SKILL.md`:** add `--dry-run` as an optional flag.

**Current invocation:** `/skillgoid:unstick <chunk_id> "<hint>"`

**New invocation:** `/skillgoid:unstick <chunk_id> [--dry-run] "<hint>"`

**Dry-run behavior:**
1. Validate `chunk_id` exists in `chunks.yaml` (same as today).
2. Read latest iteration for this chunk (same as today).
3. Construct the chunk subagent prompt with the hint injected into the `integration_failure_context` slot, prefixed with `UNSTICK HINT (from human operator): `.
4. Print the full constructed prompt to stdout, wrapped in a visible `--- begin dispatched prompt ---` / `--- end dispatched prompt ---` banner.
5. Return without dispatching the subagent. Attempt counter is not reset. No iteration record is written. Unstick budget is not consumed.

**No new script:** the construction logic is already inside `skills/unstick/SKILL.md` step 4; the dry-run is a prose branch that swaps "dispatch the subagent" for "print the constructed prompt." Keeps the change small and localized.

## Tests

### `tests/test_status_reader.py`

- **Empty project (no iterations).** All chunks show `pending`; no integration section.
- **Mixed state (success + stalled + in_progress + pending).** Table renders correctly; state column reflects latest `exit_reason` per chunk.
- **Wave computation.** Chunks with `depends_on:` are grouped into correct waves via `chunk_topo.py`.
- **Files-touched truncation.** 5 files → shows first 2 + `(+3 more)`.
- **Gate state truncation.** 5 gates → shows first 3 + `(+2 more)`.
- **Integration section present.** Project with `integration/1.json` → latest attempt rendered.
- **Not a Skillgoid project.** No `.skillgoid/` → exit 1.

### `tests/test_explain_chunk.py`

- **Three-iteration stalled chunk.** Table has 3 rows, stall signal section present, reflections verbatim.
- **Single-iteration success.** One row, no stall signal section.
- **Same-signature detection.** `(same)` annotation on repeated stderr lines; stall section emitted at the right iteration.
- **Missing `reflection` field.** Reflection section for that iteration omitted, no crash.
- **Missing `failure_signature` field.** Legacy record handled; `sig` shown as `—`.
- **Unknown chunk_id.** Exit 1 with clear stderr message.

### `tests/test_auto_retrospect_trigger.py`

- **Happy path (all success).** Build invokes retrospect exactly once at the end.
- **Stall path.** A chunk exits `stalled` → retrospect is invoked at the end; `retrospective.md` written with `## Outcome: partial`; metrics.jsonl gains one line with `outcome: partial`.
- **Empty project.** No iteration records → retrospect is skipped; no metrics line written.
- **retrospect-only path.** User invokes `/skillgoid:build retrospect-only` → retrospect runs exactly once (not twice).

### Unstick dry-run — testability note

`unstick` is prose-only today (no companion script for prompt construction). Rather than expand v0.12's scope to extract a helper script, the `--dry-run` behavior is added as a prose branch and verified by:

1. **Manual smoke test** in the implementation plan: run `/skillgoid:unstick <chunk_id> --dry-run "<hint>"` against the v0.11 integration-retry fixture, confirm the constructed prompt is printed and no iteration record is written.
2. **Skill-review diff check**: the plan step requiring the prose edit includes a `grep` assertion that the `--dry-run` branch and the `UNSTICK HINT (from human operator):` prefix both appear in `skills/unstick/SKILL.md`.

If v0.13+ introduces a `scripts/unstick_prompt.py` helper (which would de-duplicate prompt construction across dry-run and dispatch paths), a proper `tests/test_unstick_dry_run.py` can be added then. Explicitly out of scope for v0.12.

## Success criteria

1. `scripts/status_reader.py` exists and passes all unit tests in `tests/test_status_reader.py`.
2. `scripts/explain_chunk.py` exists and passes all unit tests in `tests/test_explain_chunk.py`.
3. `skills/status/SKILL.md` and `skills/explain/SKILL.md` exist and shell out to their respective scripts with stdout passthrough.
4. `skills/build/SKILL.md` invokes `retrospect` on every terminal state (success, stalled, budget_exhausted) for `build "<goal>"` and `build resume` invocation modes, with the documented skip conditions.
5. `tests/test_auto_retrospect_trigger.py` covers all four scenarios listed above.
6. `skills/unstick/SKILL.md` supports `--dry-run` with the documented preview-only behavior (manual verification per testability note above).
7. Full existing test suite still passes. No regressions.
8. Lint clean: `ruff check .` passes with no new warnings.

## What this does NOT change

- No schema changes to `schemas/iterations.schema.json`, `schemas/criteria.schema.json`, or `schemas/chunks.schema.json`.
- No changes to `retrospect/SKILL.md`, `metrics_append.py`, or `stats_reader.py` (except where explicitly noted — auto-retrospect touches only the build-orchestrator trigger).
- No changes to the gate adapter contract (`measure_python.py`) or the loop's build → measure → reflect cycle.
- No changes to `verify_iteration_written.py`, `integration_suspect.py`, or any v0.11 deliverable.
- No dedup-by-slug logic in metrics or stats — that is an explicit v0.13+ concern.
- No vault / `retrieve` / `feasibility` changes.
- No new hooks.
- No AI-synthesized narratives. Every new output is deterministic extraction from iteration JSON.
- No dashboards, HTML rendering, or remote telemetry. Stays at markdown-to-stdout.

## Why this is v0.12 and not a patch

v0.11 closed the orchestrator's machinery cracks (F6 verify + H8 integration suspect). v0.12 closes the *human* cracks that sit on top of that machinery: "I don't know what's happening" (status), "I don't know why it failed" (explain), "I lost the retrospective because the run stalled" (auto-partial), and "I can't preview what unstick will do" (dry-run). Together, v0.11 + v0.12 complete the 2026-Q2 "the build loop is reliable AND legible" arc.

Pattern continues: v0.8 stress test → v0.9 recovery → v0.10 contract → v0.11 machinery → v0.12 legibility. v0.13 shifts to vault curation improvements; v0.14 is a stress test of the v0.11 + v0.12 bundle; v0.15 introduces the TypeScript adapter.
