# skillgoid v0.11.1: Subagent Auto-Retry on Stage 2 Validation Failure

**Status:** Draft
**Version target:** 0.11.1 (patch release on top of 0.11.0)
**Audience:** Engineer implementing the feature

## Problem

`scripts/synthesize/synthesize.py` rejects subagent output when drafts violate
the provenance / schema contract (invalid JSON, missing `drafts` key, bad
provenance ref, unsupported gate type, coverage rule violations, duplicate
ids). Today `skills/synthesize-gates/SKILL.md` step 6 surfaces the failure and
stops: the user must re-run the whole skill or hand-author `criteria.yaml`.

The failure mode is usually transient — a subagent that emitted one bad ref
will produce valid drafts on a second try if it sees the rejection reason.

## Goal

When Stage 2 rejects drafts, re-dispatch the synthesis subagent **once** with
the rejection reason appended to its prompt, re-run Stage 2 on the retry
output, and continue on success. On a second failure, STOP and surface both
rejection messages.

## Non-goals

- No retry budget flag (hardcoded at 1).
- No per-error-class retry prompt tailoring (raw stderr is fed back verbatim).
- No changes to `synthesize.py`'s validation rules or stderr shape.
- No retry for Stage 1 (`ground.py`) or Stage 3 (`validate.py`) failures.
- No telemetry / metrics for retry attempts.

## Architecture

The synthesis subagent is dispatched by **skill prose via the Agent tool**,
not from a Python script. Therefore the retry loop lives in
`skills/synthesize-gates/SKILL.md`, not in `synthesize.py`.

`synthesize.py` already exits 1 with stderr naming the violated rule (e.g.,
`synthesize: DraftValidationError: draft 'x' provenance ref not found in
grounding: nonexistent/ref.py`). That stderr becomes the retry signal — no
API change required.

## Behavior spec

### SKILL.md step 6 becomes a two-attempt loop

**Attempt 1** (unchanged from v0.11):

1. Pipe `subagent_stdout` into `synthesize.py`.
2. If exit 0 → continue to Stage 3.
3. If exit 1 → capture stderr as `attempt1_stderr` and proceed to Attempt 2.

**Attempt 2** (new):

1. Re-dispatch the synthesis subagent with the **same** prompt as Attempt 1
   plus an appended instruction block:

   > Your previous output failed Stage 2 validation with:
   > ```
   > {attempt1_stderr}
   > ```
   > Re-emit the drafts JSON with this problem fixed. Do not include any
   > prose — only valid JSON.

2. Capture the retry's stdout.
3. Pipe it into `synthesize.py` a second time.
4. If exit 0 → continue to Stage 3 (treat retry as the canonical drafts).
5. If exit 1 → capture stderr as `attempt2_stderr`, surface both messages to
   the user, and STOP with:

   > Synthesis subagent failed Stage 2 validation twice. Re-run the skill
   > or hand-author `.skillgoid/criteria.yaml`.
   >
   > Attempt 1 stderr:
   > {attempt1_stderr}
   >
   > Attempt 2 stderr:
   > {attempt2_stderr}

### Triggered by

All `DraftValidationError` failures — the skill does not distinguish error
classes. If `synthesize.py` exits 1 for any reason, the retry fires once.

## Files changed

- `skills/synthesize-gates/SKILL.md`
  - Replace step 6's "Do not retry the subagent in Phase 1 — surface the
    failure so the user can re-run or hand-author. Phase 2 will add a single
    auto-retry." with the two-attempt loop above.
  - Update the "Phase 1 / 2 progress" section: remove "subagent auto-retry on
    Stage 2 validation failure" from the v0.13/v0.14 remaining list; note it
    shipped in v0.11.1.
- `tests/test_synthesize_gates_skill.py`
  - Add grep-assertions that the retry instructions exist in SKILL.md (see
    Testing below).
- `CHANGELOG.md`
  - Add a v0.11.1 entry.
- `.claude-plugin/plugin.json`
  - Version bump `0.11.0` → `0.11.1`.

## Not changing

- `scripts/synthesize/synthesize.py` — its behavior, stderr format, and exit
  code are already the contract the retry depends on. No change.
- All other Stage 1 / Stage 3 / Stage 4 scripts.
- `schemas/criteria.schema.json`.
- The existing Stage 2 unit tests (`tests/test_synthesize.py`) and e2e tests
  (`tests/test_synthesize_e2e.py`). The retry happens in skill prose; Python
  tests of `synthesize.py` are unaffected.

## Testing

### What we can test

The retry is prose-driven (invoked via the Agent tool from within
`SKILL.md`), so it is **not** reachable from pytest. The tests assert the
**prose contract** — i.e., that the SKILL.md instructions express the
contract correctly so the executing agent will follow it.

Add to `tests/test_synthesize_gates_skill.py`:

- `test_skill_documents_stage2_retry`: assert SKILL.md contains the phrase
  "Your previous output failed Stage 2 validation" (the retry prompt).
- `test_skill_documents_retry_stop_condition`: assert SKILL.md contains
  "failed Stage 2 validation twice" (the two-failure STOP message).
- `test_skill_removes_phase1_no_retry_text`: assert SKILL.md does **not**
  contain "Phase 2 will add a single auto-retry" (the stale note).

### What we cannot test

The actual retry flow — dispatching the Agent tool, capturing its stdout,
piping into `synthesize.py`, re-dispatching on failure — runs only in a
live skill invocation. Manual verification during release:

1. Construct a grounding.json with one observation.
2. Prompt the subagent to emit a draft citing a ref that doesn't exist.
3. Verify the skill detects the failure, re-dispatches with the stderr
   appended, and accepts the corrected output.

This manual step is called out in the release checklist below.

## Release checklist

- All pytest tests pass.
- `ruff check .` clean.
- Manual retry verification (above) executed against a real subagent run.
- CHANGELOG.md v0.11.1 entry present.
- `.claude-plugin/plugin.json` version is `"0.11.1"`.
- Tag `v0.11.1` at release commit; push tag.

## Risks and tradeoffs

- **Doubled subagent cost on failure.** A failure path now runs the subagent
  twice. Acceptable: the alternative is the user re-running the whole skill,
  which costs at least as much.
- **Retry context widens the prompt.** Appending stderr to the subagent
  prompt adds tokens. Stderr is typically one line (`DraftValidationError:
  ...`); no truncation needed.
- **Malformed JSON on retry too.** If the subagent ignores instructions a
  second time (e.g., wraps JSON in markdown fences), both attempts fail the
  same way. We STOP rather than loop further — the 1-retry budget is a
  deliberate ceiling.
- **Prose-only testing.** The retry itself has no unit test coverage; we rely
  on grep-assertions and manual verification. Phase 3+ could move the retry
  orchestration into a Python driver (e.g., a subprocess that calls out to
  Claude via the API), which would enable real coverage — out of scope for
  v0.11.1.

## Open questions

None. All design questions resolved during brainstorming:

- Retry budget: 1 retry (2 attempts total).
- Trigger: all `DraftValidationError` failures.
- Prompt shape: raw stderr appended verbatim.
