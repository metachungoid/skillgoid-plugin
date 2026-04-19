# Skillgoid v0.11 — Machinery Reliability Bundle

**Status:** spec
**Date:** 2026-04-18
**Predecessor:** v0.10.0 (Iteration Contract Bundle, tag v0.10.0 at commit d276e33)
**Purpose:** Close the two known cracks in the build-loop machinery surfaced by the v0.9 stress run — H8 (integration retry path, never exercised) and F6 (loop subagent can silently skip the iteration JSON write) — by moving fragile prose into testable scripts and adding post-dispatch verification.

## Problem statement

Two defects in the build/loop machinery have been known since v0.9 but were deferred, not fixed:

- **F6 (iteration JSON not written).** The intervals subagent in the chrondel stress run wrote its iteration summary in response text but never created `.skillgoid/iterations/intervals-001.json`. The driver had to manually reconstruct the file. Nothing in the orchestrator notices when this happens — `detect-resume.sh` silently under-reports completed chunks, `gate-guard.sh` silently picks the wrong "latest" iteration, and later retrospect sees an incomplete history.

- **H8 (integration retry untested).** In chrondel, all integration gates passed on first try, so the auto-repair branch in `build/SKILL.md` step 4g was never exercised. That branch contains fragile prose: "for each failing gate, grep its stderr and stdout for filenames that appear in the chunks' blueprint/impl paths. Pick the chunk whose file is most recently mentioned." Hand-grepping in prose is unreviewable, non-deterministic under driver variance, and has no unit tests.

Both defects live at the orchestrator layer, are language-agnostic, and are addressable by extracting the fragile logic into scripts and adding a verify step after every loop dispatch.

## Design principles

Every v0.11 deliverable is **language-agnostic by construction** — the orchestrator machinery does not know or care which adapter is in use. This aligns with the roadmap toward multi-language support (v0.15+ adds additional adapters). Scripts work off the generic gate_report + iteration schemas; the fixture uses `run-command` gates (the cross-adapter common denominator); no deliverable assumes Python.

## Deliverables

### 1. `scripts/integration_suspect.py` (new)

Extracts the "identify suspect chunk from a failed integration gate report" logic from SKILL.md prose into a deterministic, unit-testable script.

**CLI:**
```
python scripts/integration_suspect.py \
  --gate-report .skillgoid/integration/<attempt>.json \
  --chunks     .skillgoid/chunks.yaml
```

**Input:**
- `--gate-report`: path to an integration attempt file of shape `{iteration, chunk_id: "__integration__", gate_report: {passed, results: [...]}, ...}`
- `--chunks`: path to `.skillgoid/chunks.yaml`

**Output (stdout, JSON):**
```json
{
  "suspect_chunk_id": "parser",
  "confidence": "filename-match",
  "evidence": "chunk 'parser' path 'src/chrondel/parser.py' matched gate 'cli_parse_roundtrip' stderr"
}
```

Or when no match is found:
```json
{
  "suspect_chunk_id": null,
  "confidence": null,
  "evidence": "no chunk path appeared in any failed gate's stdout/stderr"
}
```

**Scoring algorithm (deterministic):**
1. For each chunk in `chunks.yaml`, collect its `paths[]` entries.
2. For each failing gate result (`passed: false`), concatenate `stdout + "\n" + stderr`.
3. For each (chunk, gate) pair, count how many of the chunk's paths appear as substrings in that gate's combined output.
4. Rank chunks by: (a) total match count across all failing gates, descending; (b) tiebreak by which match came from the latest-indexed failing gate in `results` (proxy for most recent failure); (c) alphabetical chunk_id as final tiebreak for determinism.
5. If the top-ranked chunk has zero matches → emit `suspect_chunk_id: null`.

**Exit codes:** 0 always (result is in the JSON). Internal errors exit 2 and print a message to stderr.

### 2. `scripts/verify_iteration_written.py` (new)

Invoked by the build orchestrator immediately after each loop subagent returns. Confirms the expected iteration file exists, parses as JSON, and satisfies the iteration schema.

**CLI:**
```
python scripts/verify_iteration_written.py \
  --chunk-id parser \
  --skillgoid-dir .skillgoid
```

**Output on success (exit 0):**
```json
{
  "ok": true,
  "latest_iteration": ".skillgoid/iterations/parser-002.json",
  "iteration_number": 2,
  "exit_reason": "success"
}
```

**Output on missing file (exit 1):**
```json
{
  "ok": false,
  "reason": "no iteration files found for chunk 'parser'",
  "searched_glob": ".skillgoid/iterations/parser-*.json"
}
```

**Output on invalid JSON / schema failure (exit 2):**
```json
{
  "ok": false,
  "reason": "iteration file failed schema validation",
  "file": ".skillgoid/iterations/parser-002.json",
  "errors": ["'exit_reason' is a required property", ...]
}
```

**Logic:**
1. Glob `<skillgoid-dir>/iterations/<chunk-id>-*.json`; if empty → exit 1 with missing report.
2. Pick the latest by `mtime` (same convention as `gate-guard.sh` post-v0.9 fix).
3. Parse JSON; on parse failure → exit 2.
4. Validate against `schemas/iterations.schema.json`; on failure → exit 2 with error list.
5. Else → exit 0.

### 3. `skills/build/SKILL.md` — two targeted edits

#### Edit A — Add post-dispatch verify step

Insert a new substep after the current step 3e (parse each subagent's JSON response) and **before** step 3f (wave gate check). The implementer may renumber as 3e-bis, 3f, or similar — what matters is the placement: all subagents have returned and their responses are parsed, but the wave gate check has not yet fired.

> **Verify each chunk wrote its iteration file.** For every chunk dispatched in this wave (excluding resume-skipped chunks from step 3a), invoke:
>
> ```bash
> python <plugin-root>/scripts/verify_iteration_written.py \
>   --chunk-id <chunk_id> \
>   --skillgoid-dir .skillgoid
> ```
>
> If any chunk's invocation exits non-zero, halt the wave. Surface to the user:
> - Every chunk that failed to produce a valid iteration file (there may be multiple sibling failures in one wave)
> - The specific reason from each script's JSON output
> - The corresponding subagent's final response text (for manual reconstruction)
>
> Do not proceed to the wave gate check (3f), subsequent waves, or integration until the iteration file(s) are written or the user intervenes. This is a distinct failure surface from the stall/budget recovery menu in 3f — a missing iteration file means the subagent never declared an exit_reason at all, so the existing menu does not apply.

#### Edit B — Replace hand-grep prose in step 4g

Replace the "Identify suspect chunk(s)" bullet in step 4g:

> - **Identify suspect chunk(s).** For each failing gate, grep its `stderr` and `stdout` for filenames that appear in the chunks' blueprint/impl paths. Pick the chunk whose file is most recently mentioned. If no filename match, ask the user which chunk to retry.

With:

> - **Identify suspect chunk.** Invoke:
>
>   ```bash
>   python <plugin-root>/scripts/integration_suspect.py \
>     --gate-report .skillgoid/integration/<attempt>.json \
>     --chunks     .skillgoid/chunks.yaml
>   ```
>
>   Parse `suspect_chunk_id` from the stdout JSON. If non-null, proceed to re-dispatch that chunk's loop subagent. If null (no deterministic match), ask the user which chunk to retry — the script's `evidence` field explains what it examined.

### 4. `skills/loop/SKILL.md` — terminal-MUST for iteration write

Strengthen the current iteration-write instruction (currently "Write `.skillgoid/iterations/<chunk_id>-NNN.json`...") to a terminal requirement:

> **Terminal requirement — write the iteration file before returning.** Your final action before returning from this invocation must be writing `.skillgoid/iterations/<chunk_id>-NNN.json` and confirming the file exists on disk (e.g., `Path(...).exists()`). The build orchestrator invokes `verify_iteration_written.py` immediately after you return; a missing or schema-invalid file halts the wave and alerts the user.
>
> Never return with the iteration file unwritten — not on success, not on failure, not on stall. If you encounter an error late in the process (gate adapter crash, unexpected state), write a record with `exit_reason: "stalled"` and as much context as you have before returning. A partial record is recoverable; no record is not.

### 5. `tests/fixtures/integration-retry/` — reference fixture (new)

Minimal language-agnostic project demonstrating the integration-retry path. Structure:

```
tests/fixtures/integration-retry/
├── README.md                   # explains the fixture's purpose
├── project/
│   ├── src/
│   │   ├── lib_a.sh            # defines fn_a
│   │   └── lib_b.sh            # defines fn_b (depends on fn_a; has a deliberate typo)
│   ├── integration/
│   │   └── check.sh            # sources both libs and invokes fn_a + fn_b
│   └── .skillgoid/
│       ├── criteria.yaml       # per-chunk: `run-command: bash -n src/<file>`; integration: `run-command: bash integration/check.sh`
│       ├── chunks.yaml         # two chunks: lib_a (paths: [src/lib_a.sh]), lib_b (paths: [src/lib_b.sh])
│       ├── blueprint.md
│       ├── iterations/
│       │   ├── lib_a-001.json  # canonical iteration record, exit_reason: success
│       │   └── lib_b-001.json  # canonical iteration record, exit_reason: success
│       └── integration/
│           └── 1.json          # first attempt: failed, stderr mentions src/lib_b.sh:<line>
└── patches/
    └── fix_lib_b.patch         # applied by the retry test to simulate the loop subagent fixing the bug
```

**Why this shape:**
- `bash -n` is a universally-available syntax check. Both per-chunk gates pass because each file is syntactically valid in isolation.
- `integration/check.sh` fails the first time because `lib_b.sh` calls `fn_a_typo` instead of `fn_a`. Error mentions `src/lib_b.sh:<line>`.
- `integration_suspect.py` reading the pre-seeded `integration/1.json` should identify `lib_b` as the suspect.
- The patch simulates the loop subagent's retry fix. After applying, `integration/check.sh` passes.

No Python adapter is invoked by the fixture's gates, so the fixture remains usable when future adapters land.

### 6. Tests (new)

#### `tests/test_integration_suspect.py`

- **Happy path** — single chunk filename in one failed gate's stderr → suspect is that chunk, `confidence: "filename-match"`.
- **Multiple chunks mentioned** — two chunks' files both appear in failed output; highest match count wins.
- **Tiebreak by recency** — equal match counts across two chunks; chunk whose match lives in a later `results[]` index wins.
- **Tiebreak by alphabet** — equal match counts AND equal recency; alphabetical chunk_id wins for determinism.
- **No match** — no chunk path appears anywhere → `suspect_chunk_id: null`.
- **Malformed gate_report** — missing `results` key, not an object → internal error, exit 2.
- **Empty failed results** — all gates passed (shouldn't be called in this case, but defensive) → `suspect_chunk_id: null`.

#### `tests/test_verify_iteration_written.py`

- **File present and valid** — returns `ok: true`, correct iteration_number.
- **File missing entirely** — exits 1, reason references the chunk_id.
- **Multiple iteration files** — returns latest by `mtime`, not alphabetical.
- **File unparseable JSON** — exits 2, reason `"file is not valid JSON"`.
- **File fails schema validation** — exits 2, reason references schema errors, `errors[]` populated.
- **Non-existent `.skillgoid/iterations/` directory** — treated as missing (exit 1), not as an internal error.

#### `tests/test_integration_retry_fixture.py`

Drives the fixture end-to-end without simulating a real subagent:
1. Copy fixture's `project/` to `tmp_path`.
2. Run `integration_suspect.py` against pre-seeded `integration/1.json` + `chunks.yaml`; assert `suspect_chunk_id == "lib_b"`.
3. Apply `patches/fix_lib_b.patch` to the tmp project (simulates the loop subagent's retry fix).
4. Run `bash integration/check.sh` in tmp project; assert exit 0 (confirming the simulated fix repairs the failure).
5. Assert that the orchestrator-side contract (identify suspect → simulate fix → re-run integration → passes) holds end-to-end for the script components.

## What this does NOT change

- No changes to `schemas/iterations.schema.json` — v0.10 handled the schema.
- No changes to `measure_python.py` or the gate adapter contract.
- No auto-redispatch of missing iteration files. Surfacing only; user decides whether to manually re-dispatch or reconstruct. Auto-recovery is deferred (and may never be added — visibility is more valuable than silent recovery).
- No changes to stall detection, budget exhaustion, `exit_reason` semantics, or the iteration record shape.
- No new skills. No changes to `retrospect`, `stats`, `unstick`, `clarify`, `feasibility`, `plan`, or `retrieve`.
- No changes to hooks (`detect-resume.sh`, `gate-guard.sh`). The v0.9 mtime fix already handles the "latest iteration" question correctly; with verify in place upstream, hooks simply get a more reliable filesystem to observe.
- Fixture is language-agnostic on purpose. Language-specific integration-retry fixtures (Python, TypeScript, etc.) are explicitly deferred to whichever version introduces the adapter that needs them.

## Success criteria

1. `scripts/integration_suspect.py` exists and passes all unit tests in `tests/test_integration_suspect.py`.
2. `scripts/verify_iteration_written.py` exists and passes all unit tests in `tests/test_verify_iteration_written.py`.
3. `skills/build/SKILL.md` has a new step 3d invoking `verify_iteration_written.py` after every loop subagent return.
4. `skills/build/SKILL.md` step 4g invokes `integration_suspect.py` instead of hand-grep prose.
5. `skills/loop/SKILL.md` contains the terminal-MUST for iteration-file write, explicitly naming `verify_iteration_written.py` as the orchestrator's check.
6. `tests/fixtures/integration-retry/` exists with the documented structure.
7. `tests/test_integration_retry_fixture.py` passes — the fixture drives both scripts through a realistic failure → fix → pass cycle.
8. Full existing test suite still passes (no regressions).
9. Lint clean: `ruff check .` passes with no new warnings.

## Why this is v0.11 and not a patch

v0.10 fixed the iteration *contract* (what a correct record looks like). v0.11 fixes the *enforcement* of that contract at the orchestrator: every loop dispatch is now verified to have produced a valid record, and every integration retry uses a deterministic suspect identifier rather than hand-grep prose. Together, v0.10's schema and v0.11's machinery close the loop from "records should look like X" to "records actually look like X, and failures to produce them halt the pipeline visibly."

Pattern continues: v0.8 stress test found bugs → v0.9 recovery fixes → v0.10 contract correctness → v0.11 machinery reliability. v0.12 shifts to user-facing polish (recovery + observability).
