# Skillgoid v0.10 — Iteration Contract Bundle

**Status:** spec
**Date:** 2026-04-18
**Predecessor:** v0.9.0 (Recovery + Resume Machinery Fixes, tag v0.9.0)
**Purpose:** Fix the root cause of v0.9 findings F1, F4, and F5 — all three traced to the same gap: `skills/loop/SKILL.md` does not specify the iteration record schema precisely enough, causing subagents to invent wrong field names and formats.

## Problem statement

v0.9's recovery stress test found four bugs in the recovery machinery. Three of them (F1, F4, F5) shared one root cause:

- **F1**: `stall_check.py` crashed on flat-list `gate_report` — subagents wrote `[{"gate_id": ...}]` instead of `{"passed": bool, "results": [...]}`.
- **F4**: `gate-guard.sh` had the same crash. Also used alphabetical sort instead of mtime.
- **F5**: Hooks checked `exit_reason` but subagents wrote `status`.

All three were fixed defensively in the scripts (v0.9). But the root cause — `loop/SKILL.md` prose — still describes the iteration record with:

```
"gate_report": { ... verbatim from adapter ... }
```

This placeholder only works if the subagent actually invokes the language-adapter skill. When subagents run gates manually (driver-pattern runs, or real runs where the subagent skips the adapter), there is no authoritative example to follow. Subagents invent flat-list gate_reports, use `status` instead of `exit_reason`, and skip `failure_signature`.

The v0.9 script fixes are backward-compat safety nets. v0.10 fixes the contract itself.

## Deliverables

### 1. `skills/loop/SKILL.md` — three targeted edits

#### Edit A — Concrete gate_report template (replaces `{ ... verbatim from adapter ... }`)

Replace the vague placeholder with the explicit adapter-output object form:

```json
"gate_report": {
  "passed": false,
  "results": [
    {
      "gate_id": "pytest_unit",
      "passed": false,
      "stdout": "",
      "stderr": "FAILED tests/test_foo.py::test_bar - AssertionError",
      "hint": "check the return value of parse_iso8601 for fixed offsets"
    },
    {
      "gate_id": "ruff_lint",
      "passed": true,
      "stdout": "All checks passed!",
      "stderr": "",
      "hint": ""
    }
  ]
}
```

Add an inline note:

> This is the adapter-output shape. If you invoked `skillgoid:python-gates`, use its output verbatim here — it already has this shape. If running gates manually without invoking the adapter, construct this exact object shape. Do **not** use a flat list `[{...}]`. The scripts accept flat-lists for backward compatibility with legacy records, but this object form is the contract.

#### Edit B — failure_signature made non-skippable

Strengthen the current soft reminder to a hard rule. Replace:

> Include the returned 16-char hex value directly in `failure_signature` on initial write — do not leave a placeholder.

With:

> Compute `failure_signature` **before** writing the file — never after, never empty, never `""`. Empty or missing signatures silently break stall detection. One-liner:
>
> ```bash
> failure_signature=$(python <plugin-root>/scripts/stall_check.py /tmp/gate_report.json)
> ```
>
> The schema rejects any value that is not a 16-char lowercase hex string (pattern `^[0-9a-f]{16}$`).

Also update the existing temp-file Python pattern (lines 81–92) to show `failure_signature` being captured and inserted, not just computed and discarded.

#### Edit C — exit_reason enum table (inline, adjacent to the template)

Add a small table immediately after the iteration record JSON template:

| `exit_reason` value | When to write it |
|---|---|
| `"in_progress"` | Gates failed, budget remains, no stall detected |
| `"success"` | All gates passed (`gate_report.passed == true`) |
| `"budget_exhausted"` | This was iteration N and N ≥ max_attempts |
| `"stalled"` | `failure_signature` matches the previous iteration's value |

Add a note: *"Write `exit_reason`, not `status`. The field is named `exit_reason` in the schema, in `stall_check.py`, and in `gate-guard.sh`. Using `status` will cause hooks to silently miss completed chunks."*

### 2. `schemas/iterations.schema.json` — minor

Add `status` as an explicitly-documented deprecated alias:

```json
"status": {
  "type": "string",
  "description": "Deprecated alias for exit_reason. Hooks fall back to this field if exit_reason is absent, but new records should use exit_reason."
}
```

This makes the deprecation visible in the schema rather than only in hook source code. No validation change — `additionalProperties: true` already accepts it.

### 3. `tests/test_v10_bundle.py` — two new tests

#### Test A — H9 coverage: retrospect-only with partial state

Create a synthetic `.skillgoid/` in `tmp_path` containing:
- `chunks.yaml` with 3 chunks (A, B, C)
- `criteria.yaml` with `language: python` and basic gates
- `iterations/chunk-a-001.json` — `exit_reason: success`
- `iterations/chunk-b-001.json` — `exit_reason: in_progress` (first attempt, gates failing, budget remains)
- `iterations/chunk-b-002.json` — `exit_reason: budget_exhausted` (N=2 ≥ max_attempts=2, terminal)

This matches SKILL.md exit logic: only the terminal iteration of a budget-exhausted chunk writes `budget_exhausted`; prior iterations stay `in_progress`.

Run `metrics_append.py --skillgoid-dir <tmp> --slug test-partial`. Assert:
- Exit 0
- Appended JSON line has `outcome: "partial"` (not `"success"`)
- `budget_exhausted_count: 1` (one iteration terminated by budget)
- `stall_count: 0`

This is the first unit test for the retrospect-only code path (H9 was never triggered in the stress run).

#### Test B — stall detection contract with object-form gate_report

Verify `stall_check.signature()` works correctly with the canonical object form (not just the flat-list handled in v0.9):

```python
record = {
    "chunk_id": "parser",
    "iteration": 2,
    "gate_report": {
        "passed": False,
        "results": [
            {"gate_id": "pytest_unit", "passed": False,
             "stderr": "FAILED tests/test_parser.py::test_dst - AssertionError"},
        ]
    },
    "failure_signature": "",
}
sig = signature(record)
assert len(sig) == 16
assert sig == signature({**record, "iteration": 3})   # same failure → same sig
```

Also confirm that a different failure produces a different signature. This locks in the canonical contract and ensures the object-form path in `stall_check.py` (the `report.get("results")` branch) is explicitly tested — currently it's only tested via the integration tests.

## What this does NOT change

- No changes to `gate-guard.sh`, `detect-resume.sh`, or `stall_check.py` — those were fixed in v0.9 and are correct.
- No changes to `schemas/criteria.schema.json` or `schemas/chunks.schema.json`.
- No new scripts. No new skills.
- The flat-list backward-compatibility in the scripts stays — older iteration records from pre-v0.10 runs remain valid.
- H8 (integration retry dispatch) remains untested by unit tests — the dispatch logic is in SKILL.md prose and cannot be unit-tested without a full plugin invocation. Documented as a known gap, not addressed here.

## Success criteria

1. `skills/loop/SKILL.md` contains a concrete JSON example for `gate_report` with all field names spelled out.
2. `failure_signature` computation is described as a hard requirement with a one-liner.
3. `exit_reason` enum table is present inline in the template.
4. A note explicitly says "write `exit_reason`, not `status`".
5. `schemas/iterations.schema.json` documents `status` as deprecated.
6. `tests/test_v10_bundle.py` passes: H9 retrospect-only outcome classification, stall detection object-form contract.
7. Existing test suite still passes (no regressions).

## Why this is v0.10 and not a patch

v0.9 fixed the machinery defensively — the scripts now handle both formats. v0.10 fixes the contract — the SKILL.md prose becomes authoritative. Together they close the loop: the scripts are robust to legacy records, and new records are written correctly. Without v0.10, every future stress test will produce the same drift.

This follows the v0.7→v0.8→v0.9 pattern: stress test finds bugs → correctness bundle fixes root causes. v0.10 is the correctness bundle for v0.9's findings.
