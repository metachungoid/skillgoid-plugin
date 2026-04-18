# Skillgoid v0.9 Stress-Test Design — `chrondel` (recovery + resume)

**Status:** experiment design (not a feature spec)
**Date:** 2026-04-18
**Predecessor:** v0.8 Correctness + Subagent Discipline Bundle (shipped same day, tag `v0.8.0`)
**Purpose:** Run Skillgoid v0.8 against a date/time library with deliberately-injected failure scenarios to surface v0.9 priorities. This is the third stress-test experiment in the v0.7 → v0.8 → v0.9 cycle; the first two hit the polyglot and scale dimensions. This one hits the **recovery / resume / failure-mode** dimension that has zero prior data across all 8 real runs.

## Why this experiment exists

v0.7 came from a polyglot stress test (`taskbridge`). v0.8 came from a scale stress test (`minischeme`, 18 chunks, width-6 parallel). Both surfaced concrete bugs and shipped evidence-driven releases. The pattern works.

But v0.9 is different. The remaining deferred items from the roadmap are mostly **waiting on organic evidence** — polyglot-for-real, glob-aware overlap, cross-platform — not things another synthetic test can decisively produce. Adding more chunks or another language would mostly re-confirm what v0.7/v0.8 already shipped.

The one genuinely-unexplored dimension is **failure behavior**. Every prior run was a green-first-try execution. Across 8 real runs:

- **0 stalls** (no chunk ever exited `stalled`)
- **0 budget exhaustions** (no chunk ever hit `max_attempts`)
- **0 `/skillgoid:unstick` invocations** (never needed)
- **0 SessionStart-based resumes** (every run was single-session end-to-end)
- **1 integration retry** (`indexgrep` — the whole evidence we have)
- **0 `gate-guard.sh` Stop-blocks** (never fired in anger)
- **0 `build retrospect-only`** invocations

The v0.2/v0.4/v0.6 machinery for these scenarios EXISTS but has never been exercised under real failure conditions. We don't actually know if any of it works. v0.9's planning needs data from a run where things go wrong.

## The target project — `chrondel`

A date/time library implemented in Python 3.11+, with deliberately strict acceptance criteria designed to force iteration. Chosen because:

- **Timezone, DST, leap-year, leap-second, and sub-second-precision handling are well-documented LLM weakness spots.** First-iteration code reliably has bugs in these areas — iteration budget gets exercised without the test driver gaming it.
- **Round-trip and arithmetic tests catch subtle errors.** "`parse(format(dt)) == dt` across 10,000 fuzz-generated inputs" is the kind of test that surfaces bugs the subagent didn't think about.
- **Hermetic** — no external services, stdlib only.
- **Scope-appropriate** — ~8 chunks, matches prior release scope.
- **Cross-chunk type contracts** (the `Duration` class is consumed by arithmetic, comparison, and intervals chunks) — replicates the F6-class surface that v0.8 addressed.

### Language scope

A `chrondel` library with:
- Core types: `Date`, `Time`, `DateTime`, `Duration`, `Interval`, `Timezone`
- Parsing: ISO-8601, RFC-3339, and a forgiving `parse_any()` that tries multiple formats
- Formatting: strftime-compatible + ISO-8601 + custom format strings
- Arithmetic: add/subtract Durations, respecting DST transitions
- Comparison: total ordering, including across timezones
- Intervals: contains, overlaps, union/intersection (pairwise only)
- Timezone operations: conversion, "wall time" vs "instant" semantics
- CLI: `chrondel parse <str>`, `chrondel diff <a> <b>`, `chrondel convert <dt> --tz <tz>`

### Strict acceptance criteria (the key design choice)

Unlike minischeme's "works if expected output appears," chrondel's acceptance gates are strict enough to force genuine iteration:

- **Round-trip property:** `parse(format(dt, iso_8601)) == dt` for all valid DateTimes across 500 fuzz-generated inputs.
- **DST transition test:** adding 1 day to 2026-11-01T01:30 America/Los_Angeles produces 2026-11-02T01:30 (not 2026-11-02T00:30 — wall-time semantics).
- **Timezone-agnostic equality:** `DateTime(2026, 4, 1, tz="UTC") == DateTime(2026, 4, 1, tz="Europe/London")` is False (different instants, same wall time); but `.to_instant()` equality is True.
- **Interval arithmetic:** `Interval(a, b).overlaps(Interval(c, d))` must be correct for all 13 Allen relations (before, meets, overlaps, during, etc.).
- **Leap year / leap second:** 2000-02-29 is valid; 1900-02-29 raises; 2016-12-31T23:59:60 (actual leap second) is handled gracefully (reject or accept per spec choice).

First-iteration code WILL miss some of these. Budget gets exercised.

## Expected chunk decomposition (~8 chunks)

Approximate shape; final decomposition set by `clarify` + `plan`.

```
Wave 0 (1 chunk):  scaffold
Wave 1 (2 chunks): core_types, errors
Wave 2 (3 chunks): parser, formatter, timezone     (parallel; disjoint files)
Wave 3 (2 chunks): arithmetic, comparison           (both use core_types + duration)
Wave 4 (1 chunk):  intervals
Wave 5 (1 chunk):  cli
Wave 6 (1 chunk):  integration-examples
```

Total: ~10 chunks (possibly consolidated to 8 depending on planner output), max width 3. NOT a scale test — this is about FAILURE MODES, not wave width. A narrower DAG is fine.

## v0.9 hypotheses being tested

Each is falsifiable. Rejected hypotheses become v0.9 priorities.

| # | Hypothesis | Falsified by |
|---|---|---|
| H1 | Organic multi-iteration works: chunks that fail first time eventually pass within `max_attempts: 5` | A chunk hitting budget without genuine progress |
| H2 | `stalled` exit fires when `failure_signature` repeats | Identical failure 2× and loop doesn't detect stall |
| H3 | `/skillgoid:unstick <chunk> "<hint>"` actually unblocks a stalled chunk | Hint injected, chunk still stuck |
| H4 | `budget_exhausted` fires cleanly when `max_attempts` is hit | Infinite loop, or wrong exit reason written |
| H5 | SessionStart hook emits usable resume context after mid-wave interruption | Fresh session has no idea what state the project is in |
| H6 | `/skillgoid:build resume` correctly picks up partial state | Resume tries to redo completed chunks, or skips incomplete ones |
| H7 | `gate-guard.sh` blocks Stop mid-loop with failing gates + budget remaining | Stop succeeds despite failing gates |
| H8 | `integration_retries: 2` actually re-dispatches the suspect chunk with failure context | Integration failure is surfaced without retry, or retries don't inject context |
| H9 | `/skillgoid:build retrospect-only` finalizes a stuck project cleanly | Hangs, crashes, or refuses to retrospect partial state |
| H10 | v0.8's schema validation doesn't over-reject valid iteration records during recovery | A legitimate recovery-iteration JSON gets refused |

H5/H6 is especially interesting because **the SessionStart hook and resume logic have literally never been exercised in a real run.** Every prior test was single-session end-to-end. This is 4 releases of untested machinery.

## Scripted intervention scenarios

**This is the structural change from v0.7/v0.8.** Prior tests observed natural behavior. This test deliberately injects interventions to exercise specific failure-mode machinery.

### Scenario 1 — Organic iteration (no intervention)

Let chrondel run end-to-end. At least one chunk (likely `parser` or `timezone`) should need 2+ iterations naturally due to strict acceptance tests. Confirms H1.

### Scenario 2 — Forced stall

Pick one chunk (proposed: `formatter`). Let iteration 1 run. Before iteration 2, manually revert the subagent's output file so it produces the same failure as iter 1. Loop's `stall_check.py` should detect the repeated `failure_signature` and exit `stalled`. Confirms H2.

### Scenario 3 — Unstick injection

Following scenario 2's stall, invoke `/skillgoid:unstick formatter "the strftime %Z directive returns the tzname not the offset; use %z for the offset"`. Verify the re-dispatched subagent receives the hint and actually uses it to fix the code. Confirms H3.

### Scenario 4 — Budget exhaustion

For one chunk (proposed: `intervals` — Allen relations have 13 cases and LLMs often miss some), set `max_attempts: 2` in criteria override. If 2 iterations both fail, loop should exit `budget_exhausted`. Confirms H4.

### Scenario 5 — SessionStart resume

After scenario 1 completes wave 2 (parser+formatter+timezone all green), KILL the driver session. Start a fresh Claude Code session in the project directory. Verify:
- SessionStart hook (`detect-resume.sh`) emits an `additionalContext` payload mentioning chunks completed.
- `/skillgoid:build resume` picks up at wave 3 (not wave 0) and does not re-run completed chunks.
Confirms H5 + H6.

### Scenario 6 — Gate-guard block

At some mid-loop point with failing gates and budget remaining, attempt to end the Claude Code session normally (e.g., quit). Verify `gate-guard.sh` fires and blocks Stop with a helpful reason mentioning failing gates. Confirms H7.

### Scenario 7 — Integration retry

Write an integration gate that can fail: e.g., a subprocess command that tests the CLI end-to-end parsing. If the `parser` chunk's per-chunk tests pass but the CLI integration test fails (maybe strftime format divergence between chunks), `integration_retries: 2` should re-dispatch the suspected chunk. Track whether `integration_failure_context` actually propagates to the retry subagent. Confirms H8.

### Scenario 8 — retrospect-only

After scenario 4's `budget_exhausted`, instead of fixing manually, invoke `/skillgoid:build retrospect-only`. Verify it writes `retrospective.md` and `metrics.jsonl` entry despite incomplete gates. Confirms H9.

Scenarios sequence across ONE run. Each scenario's precondition is either natural (waits for organic failure) or manufactured (revert file, set max_attempts, kill session). The test driver (me) orchestrates interventions at the right moments.

## Methodology

Same driver pattern as minischeme: this Claude session manually interprets `skills/*/SKILL.md` and dispatches parallel-wave subagents via the `Agent` tool. Subagents do real work: build, run gates, write iterations, commit.

**New for this experiment:** the driver also performs **out-of-band interventions** between subagent dispatches — file reverts, max_attempts tightening, process kills, hint injections. These are scripted in the findings log as they happen so the sequence is reconstructable.

**Two-session requirement for scenario 5.** The test driver must run across at least two Claude Code sessions to legitimately exercise SessionStart resume. This means the experiment can't complete in a single uninterrupted execution — we need a mid-run pause where the user starts a fresh session.

Working directory: `~/Development/skillgoid-test/chrondel/` — sibling to existing projects.

Findings: append-only `~/Development/skillgoid-test/v0.9-findings.md`, same format as v0.7/v0.8.

## Stopping criteria

Stop and retrospect when ANY of:

1. All 8 scenarios exercised (whether they pass or fail). This is the main success criterion — we want DATA on all 8, not necessarily passing gates on all 8.
2. 🔴 finding that makes further scenarios impossible to exercise.
3. 5+ 🟡 findings accumulated — enough to spec v0.9.
4. Iteration budget exhausted across 4+ chunks — suggests the strict-acceptance approach went too aggressive; stop and retrospect.

Unlike the minischeme run (which had a "stop after wave 6 — the headline" criterion), this run's stopping criterion is **coverage of the scenario matrix**, not pipeline progress. We care about exercising the failure machinery, not shipping a working date/time library. A chrondel that never compiles end-to-end is fine if we got H1–H9 data.

## Outputs

- **`chrondel/.skillgoid/retrospective.md`** — hypotheses table with confirmed/falsified status for each H1–H10.
- **`~/Development/skillgoid-test/v0.9-findings.md`** — findings with severities + scripted-scenario cross-reference.
- **One JSON line in `~/.claude/skillgoid/metrics.jsonl`** — per retrospect SKILL.md.
- **A v0.9 prioritization recommendation** — same ROI-ordered format as v0.7/v0.8 retrospectives.

## Anti-goals

- **Polyglot.** Still waiting on organic evidence.
- **Scale (more chunks).** minischeme already proved width-6.
- **Shipping chrondel.** We don't care if the library actually works end-to-end. We care about what failure-mode machinery fires correctly.
- **Testing v0.8 features directly.** v0.8's schema validation, blueprint slicing, gate_overrides, etc. are ambient infrastructure. If they break during recovery, that's a regression finding, but the experiment isn't designed around them.

## Risks

**Primary risk: strict acceptance produces *too much* iteration, burning budget without useful signal.** If every chunk hits `budget_exhausted`, the test becomes a pure infrastructure check with little subagent-behavior data. Mitigation: if this happens after 3 chunks, loosen acceptance criteria in `criteria.yaml` and restart. Document the loosening in findings.

**Secondary risk: SessionStart + resume (scenario 5) may require specific multi-session coordination that's awkward in this driver pattern.** The test driver (me) needs to genuinely terminate and restart — not just simulate. If the multi-session requirement breaks the experiment, fall back to simulating resume state (manually construct the `.skillgoid/iterations/` directory to look post-wave-2) and note as a methodology deviation.

**Tertiary risk: same-driver bias.** Same as v0.7/v0.8. Some findings reflect "what SKILL.md literally says" rather than "what a plugin runtime does." F5/F7/F10 from v0.8 were susceptible to this; here, interventions are scripted explicitly so the bias should be lower.

## What this spec is NOT

An experiment design, not a feature implementation spec. The plan that follows is an execution plan for the experiment (interventions at specific points), not a v0.9 feature plan. The v0.9 feature spec will be written AFTER this experiment yields findings.
