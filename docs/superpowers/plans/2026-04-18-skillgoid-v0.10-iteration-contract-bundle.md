# Skillgoid v0.10 Iteration Contract Bundle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `skills/loop/SKILL.md` the authoritative, unambiguous source for iteration record shape — eliminating the subagent drift that caused v0.9 findings F1, F4, F5.

**Architecture:** Three prose edits to `skills/loop/SKILL.md` (concrete `gate_report` template, hardened `failure_signature` rule, inline `exit_reason` enum table); a documentation-only schema addition for `status` deprecation; two lock-in pytest tests covering the H9 retrospect-only path and the canonical object-form stall signature.

**Tech Stack:** Python 3.11+, pytest, JSON Schema draft 2020-12, markdown. Tests run via the project's existing `pytest` suite (`make test`).

---

## Spec Reference

Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.10-iteration-contract-bundle.md`

Deliverables:
1. `skills/loop/SKILL.md` — Edits A, B, C (gate_report template, failure_signature hard rule, exit_reason table)
2. `schemas/iterations.schema.json` — add `status` as deprecated alias (documentation only)
3. `tests/test_v10_bundle.py` — Test A (H9 retrospect-only) and Test B (stall detection object-form contract)

Success: SKILL.md has concrete JSON example; `failure_signature` described as hard rule with one-liner; `exit_reason` enum table inline; note "write `exit_reason`, not `status`"; schema documents `status` deprecation; `tests/test_v10_bundle.py` passes; existing suite still passes.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tests/test_v10_bundle.py` | create | Two lock-in tests: H9 retrospect-only outcome classification, stall detection object-form contract |
| `skills/loop/SKILL.md` | modify | Three targeted prose edits (A/B/C) at specified line ranges |
| `schemas/iterations.schema.json` | modify | Add `status` property with deprecation description |

Tests exist to lock in existing v0.9 behavior against the newly-documented v0.10 contract. No new production code — the machinery fixes shipped in v0.9. v0.10 is a contract / documentation correctness bundle.

---

## Task 1: Test B — stall detection object-form contract

Creates `tests/test_v10_bundle.py` with a single test verifying `stall_check.signature()` handles the canonical object-form `gate_report` correctly. This is a lock-in test: v0.9's `stall_check.py` already handles both array and object forms (line 34–37 of `scripts/stall_check.py`). The test proves the contract is intact so future edits to `stall_check.py` can't silently break the object-form path without failing this test.

**Files:**
- Create: `tests/test_v10_bundle.py`

- [ ] **Step 1: Write the failing test**

Create `/home/flip/Development/skillgoid/skillgoid-plugin/tests/test_v10_bundle.py` with:

```python
"""End-to-end tests for v0.10 iteration contract bundle.

Locks in the v0.10 contract:
  - stall_check.signature() works with canonical object-form gate_report
  - metrics_append classifies budget_exhausted chunks as 'partial' outcome

These are lock-in tests. The behavior they assert shipped in v0.9; v0.10's
contribution is making the contract authoritative in skills/loop/SKILL.md prose.
If either test ever fails, the v0.10 contract has been broken.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.stall_check import signature

ROOT = Path(__file__).resolve().parents[1]
METRICS_CLI = [sys.executable, str(ROOT / "scripts" / "metrics_append.py")]


def test_stall_signature_object_form_contract():
    """Test B: canonical object-form gate_report produces stable, discriminating signatures.

    Object form is {"passed": bool, "results": [...]} — the shape measure_python.py
    emits and the shape the v0.10 SKILL.md template documents. Same failing stderr
    across iterations must yield the same 16-char hex signature; different stderr
    must yield a different signature.
    """
    record = {
        "chunk_id": "parser",
        "iteration": 2,
        "gate_report": {
            "passed": False,
            "results": [
                {
                    "gate_id": "pytest_unit",
                    "passed": False,
                    "stderr": "FAILED tests/test_parser.py::test_dst - AssertionError",
                },
            ],
        },
        "failure_signature": "",
    }

    sig = signature(record)
    assert len(sig) == 16
    assert all(c in "0123456789abcdef" for c in sig), \
        f"signature must be lowercase hex: {sig!r}"

    # Same failure on a later iteration → same signature (stall detection).
    sig_next = signature({**record, "iteration": 3})
    assert sig == sig_next, "identical failing gate_report must produce identical signature"

    # Different failure → different signature.
    different = {
        **record,
        "gate_report": {
            "passed": False,
            "results": [
                {
                    "gate_id": "pytest_unit",
                    "passed": False,
                    "stderr": "FAILED tests/test_parser.py::test_leap - OverflowError",
                },
            ],
        },
    }
    assert signature(different) != sig, \
        "different failing stderr must produce different signature"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && pytest tests/test_v10_bundle.py::test_stall_signature_object_form_contract -v`

Expected: PASS. If it fails, either `stall_check.py` has regressed (check `git log scripts/stall_check.py`) or the `gate_report` key name has changed.

- [ ] **Step 3: Commit**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git add tests/test_v10_bundle.py
git commit -m "$(cat <<'EOF'
test(v10): lock in stall_check object-form gate_report contract

Verifies signature() handles {"passed": bool, "results": [...]} correctly —
the shape measure_python.py emits and the shape v0.10 SKILL.md will document
as canonical. Same failure → same signature; different stderr → different signature.

EOF
)"
```

---

## Task 2: Test A — H9 retrospect-only partial-state classification

Adds a second test to `tests/test_v10_bundle.py` covering the retrospect-only code path (hypothesis H9) that was never organically triggered during the v0.9 chrondel stress run. A synthetic `.skillgoid/` with one success chunk and one budget-exhausted chunk drives `metrics_append.py` and asserts the resulting metrics line has `outcome: "partial"` and the correct counts.

**Files:**
- Modify: `tests/test_v10_bundle.py` (append second test + helper)

- [ ] **Step 1: Add the Test A helper and test**

Append to `/home/flip/Development/skillgoid/skillgoid-plugin/tests/test_v10_bundle.py`:

```python


def _write_iter(iters_dir: Path, filename: str, *, chunk_id: str, iteration: int,
                exit_reason: str) -> None:
    """Write a synthetic iteration record. Mirrors the shape metrics_append reads."""
    (iters_dir / filename).write_text(json.dumps({
        "iteration": iteration,
        "chunk_id": chunk_id,
        "started_at": "2026-04-17T12:00:00Z",
        "ended_at": "2026-04-17T12:05:00Z",
        "gate_report": {"passed": exit_reason == "success", "results": []},
        "exit_reason": exit_reason,
        "failure_signature": "0" * 16,
    }))


def test_h9_retrospect_only_partial_outcome(tmp_path, monkeypatch):
    """Test A: metrics_append classifies budget_exhausted chunks as 'partial' outcome.

    Synthetic 3-chunk project:
      - chunk-a: success (1 iteration)
      - chunk-b: terminal budget_exhausted (iteration 2 after in_progress iteration 1)
      - chunk-c: no iterations (never ran)

    Assertions:
      - CLI exit 0
      - metrics.jsonl appended with outcome="partial" (not "success")
      - budget_exhausted_count == 1 (only terminal iteration)
      - stall_count == 0
    """
    # Redirect HOME so metrics.jsonl writes to tmp_path, not the user's real ~/.claude.
    monkeypatch.setenv("HOME", str(tmp_path))

    sg = tmp_path / "project" / ".skillgoid"
    iters_dir = sg / "iterations"
    iters_dir.mkdir(parents=True)

    (sg / "chunks.yaml").write_text(
        "chunks:\n"
        "  - id: chunk-a\n    paths: [src/a.py]\n"
        "  - id: chunk-b\n    paths: [src/b.py]\n"
        "  - id: chunk-c\n    paths: [src/c.py]\n"
    )
    (sg / "criteria.yaml").write_text(
        "language: python\n"
        "gates:\n"
        "  - id: pytest_unit\n    type: pytest\n    args: []\n"
    )

    _write_iter(iters_dir, "chunk-a-001.json",
                chunk_id="chunk-a", iteration=1, exit_reason="success")
    _write_iter(iters_dir, "chunk-b-001.json",
                chunk_id="chunk-b", iteration=1, exit_reason="in_progress")
    _write_iter(iters_dir, "chunk-b-002.json",
                chunk_id="chunk-b", iteration=2, exit_reason="budget_exhausted")

    result = subprocess.run(
        METRICS_CLI + ["--skillgoid-dir", str(sg), "--slug", "test-partial"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, \
        f"metrics_append exited {result.returncode}: {result.stderr}"

    metrics_path = tmp_path / ".claude" / "skillgoid" / "metrics.jsonl"
    assert metrics_path.exists(), "metrics.jsonl was not created"

    lines = metrics_path.read_text().strip().splitlines()
    assert len(lines) == 1, f"expected 1 metrics line, got {len(lines)}"
    entry = json.loads(lines[0])

    assert entry["slug"] == "test-partial"
    assert entry["outcome"] == "partial", \
        f"expected outcome=partial for budget_exhausted chunk, got {entry['outcome']!r}"
    assert entry["budget_exhausted_count"] == 1, \
        f"expected 1 terminal budget_exhausted iteration, got {entry['budget_exhausted_count']}"
    assert entry["stall_count"] == 0
    assert entry["chunks"] == 3
```

- [ ] **Step 2: Run the new test to verify it passes**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && pytest tests/test_v10_bundle.py::test_h9_retrospect_only_partial_outcome -v`

Expected: PASS. If `outcome` comes back as `"success"`, `_outcome()` in `scripts/metrics_append.py` has regressed. If `budget_exhausted_count` comes back as 2, the test fixture got miswritten — only `chunk-b-002.json` should carry `budget_exhausted`.

- [ ] **Step 3: Run the whole new test file to confirm both tests pass together**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && pytest tests/test_v10_bundle.py -v`

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git add tests/test_v10_bundle.py
git commit -m "$(cat <<'EOF'
test(v10): lock in H9 retrospect-only partial-outcome classification

metrics_append classifies budget_exhausted chunks as outcome="partial", with
budget_exhausted_count counting terminal iterations only. H9 was never organically
triggered in the v0.9 chrondel stress run — this is the first unit test for the
retrospect-only code path.

EOF
)"
```

---

## Task 3: Edit A — concrete `gate_report` template in `skills/loop/SKILL.md`

Replace the vague placeholder `{ ... verbatim from adapter ... }` at line 64 with the explicit object-form template. Add an inline note explaining the adapter-output shape is canonical and flat-list is accepted only for backward compatibility.

**Files:**
- Modify: `skills/loop/SKILL.md:56-72` (iteration record JSON block and closing paragraph)

- [ ] **Step 1: Replace the iteration record JSON block**

Edit `/home/flip/Development/skillgoid/skillgoid-plugin/skills/loop/SKILL.md`. Replace the block at lines 56–72 (the JSON template and the paragraph that follows):

Find:

```markdown
   The iteration record JSON:
   ```json
   {
     "iteration": N,
     "chunk_id": "<id>",
     "started_at": "ISO-8601",
     "ended_at": "ISO-8601",
     "gates_run": ["pytest", "ruff"],
     "gate_report": { ... verbatim from adapter ... },
     "reflection": "<1–3 paragraphs: what was tried, what failed, hypothesis for next attempt>",
     "notable": false,
     "failure_signature": "<16-char hex from stall_check.py>",
     "changes": {"files_touched": [...], "net_lines": <int>, "diff_summary": "..."},
     "exit_reason": "in_progress"
   }
   ```
   Mark `notable: true` when the reflection surfaces a non-obvious lesson (unexpected tool behavior, surprising library edge case, a design decision that changed the plan). Boring iterations stay `notable: false`. The final written file must have a real 16-char hex in `failure_signature` — the schema will reject a placeholder.
```

Replace with:

````markdown
   The iteration record JSON:
   ```json
   {
     "iteration": N,
     "chunk_id": "<id>",
     "started_at": "ISO-8601",
     "ended_at": "ISO-8601",
     "gates_run": ["pytest", "ruff"],
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
     },
     "reflection": "<1–3 paragraphs: what was tried, what failed, hypothesis for next attempt>",
     "notable": false,
     "failure_signature": "<16-char hex from stall_check.py>",
     "changes": {"files_touched": [...], "net_lines": <int>, "diff_summary": "..."},
     "exit_reason": "in_progress"
   }
   ```

   This is the adapter-output shape. If you invoked `skillgoid:python-gates` (or any language-gates adapter), use its stdout object verbatim as `gate_report` — it already has this shape. If you are running gates manually without invoking an adapter, construct this exact object form. Do **not** use a flat list like `[{"gate_id": ..., "passed": ...}]`. The scripts accept flat-lists for backward compatibility with legacy iteration records, but this object form is the contract.

   Mark `notable: true` when the reflection surfaces a non-obvious lesson (unexpected tool behavior, surprising library edge case, a design decision that changed the plan). Boring iterations stay `notable: false`. The final written file must have a real 16-char hex in `failure_signature` — the schema will reject a placeholder.
````

- [ ] **Step 2: Verify the edit lands at the intended location**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && grep -n '"gate_report"' skills/loop/SKILL.md`

Expected: one match, pointing into the new object-form template (not `{ ... verbatim from adapter ... }`).

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && grep -n "adapter-output shape\|flat list\|backward compatibility" skills/loop/SKILL.md`

Expected: the note block is present.

- [ ] **Step 3: Run existing tests to confirm no regressions**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && pytest -x`

Expected: all tests pass. SKILL.md prose edits don't affect any test, so this is a paranoia check.

- [ ] **Step 4: Commit**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git add skills/loop/SKILL.md
git commit -m "$(cat <<'EOF'
loop: concrete gate_report template in SKILL.md (v0.10 edit A)

Replaces "{ ... verbatim from adapter ... }" placeholder with the explicit
object-form {"passed": bool, "results": [...]} shape that measure_python.py
emits. v0.9 stress test (F1/F4) showed subagents defaulted to flat-list when
the prose was vague — this locks the contract.

EOF
)"
```

---

## Task 4: Edit B — hardened `failure_signature` rule + updated temp-file pattern

Strengthen the soft reminder at line 54 into a hard rule, add the explicit one-liner, and update the canonical temp-file pattern at lines 81–92 to show `failure_signature` being captured from `stall_check.py` rather than discarded.

**Files:**
- Modify: `skills/loop/SKILL.md:54` (reflect-step prose)
- Modify: `skills/loop/SKILL.md:80-92` (canonical Python pattern)

- [ ] **Step 1: Replace the reflect-step prose**

Edit `/home/flip/Development/skillgoid/skillgoid-plugin/skills/loop/SKILL.md`. Find line 54:

```
8. **Reflect step.** Before writing the iteration file, compute the stall signature by running `python <plugin-root>/scripts/stall_check.py` against the gate_report (write the gate_report to a temp file if needed, then pass the temp file path as the argument). Include the returned 16-char hex value directly in `failure_signature` on initial write — do not leave a placeholder. Then write `.skillgoid/iterations/<chunk_id>-NNN.json` with (v0.7 convention — one filename namespace per chunk, so parallel chunks never contend). `<chunk_id>` is this chunk's id from chunks.yaml; `NNN` is this chunk's own iteration count, zero-padded to 3 digits (first iteration is 001). Example: `scaffold-001.json`, `py_db-001.json`, `py_db-002.json`. Back-compat note: older projects (pre-v0.7) used unprefixed `NNN.json`. Both conventions coexist in the same iterations dir when a project is resumed across the upgrade; readers handle both.
```

Replace with:

````
8. **Reflect step.** Compute `failure_signature` **before** writing the iteration file — never after, never empty, never `""`. Empty or missing signatures silently break stall detection. The schema rejects any value that is not a 16-char lowercase hex string (pattern `^[0-9a-f]{16}$`). One-liner:

   ```bash
   failure_signature=$(python <plugin-root>/scripts/stall_check.py <path-to-gate-report.json>)
   ```

   Write the gate_report to a temp file first (see canonical pattern below), pass that path as the argument, capture stdout as the signature. Then write `.skillgoid/iterations/<chunk_id>-NNN.json` with the captured signature embedded directly — do not leave a placeholder. `<chunk_id>` is this chunk's id from chunks.yaml; `NNN` is this chunk's own iteration count, zero-padded to 3 digits (first iteration is 001). Example: `scaffold-001.json`, `py_db-001.json`, `py_db-002.json`. (v0.7 convention — one filename namespace per chunk, so parallel chunks never contend.) Back-compat note: older projects (pre-v0.7) used unprefixed `NNN.json`. Both conventions coexist in the same iterations dir when a project is resumed across the upgrade; readers handle both.
````

- [ ] **Step 2: Update the canonical Python temp-file pattern**

Still in `/home/flip/Development/skillgoid/skillgoid-plugin/skills/loop/SKILL.md`, find the code block at lines 80–92:

```markdown
Canonical pattern:

```python
import tempfile, json
from pathlib import Path

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                  dir=tempfile.gettempdir()) as tf:
    tf.write(json.dumps(gate_report))
    scratch = Path(tf.name)
try:
    # use scratch
finally:
    scratch.unlink(missing_ok=True)
```
```

Replace with:

````markdown
Canonical pattern — write gate_report to a tempfile, call `stall_check.py`, capture the signature, insert it into the iteration record, then clean up:

```python
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path("<plugin-root>")  # resolve from CLAUDE_PLUGIN_ROOT or similar

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                  dir=tempfile.gettempdir()) as tf:
    tf.write(json.dumps({"gate_report": gate_report}))
    scratch = Path(tf.name)
try:
    proc = subprocess.run(
        [sys.executable, str(PLUGIN_ROOT / "scripts/stall_check.py"), str(scratch)],
        capture_output=True, text=True, check=True,
    )
    failure_signature = proc.stdout.strip()  # 16-char lowercase hex
    iteration_record["failure_signature"] = failure_signature
    # ... then write iteration_record to .skillgoid/iterations/<chunk_id>-NNN.json
finally:
    scratch.unlink(missing_ok=True)
```
````

- [ ] **Step 3: Verify edits landed**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && grep -n "never empty, never\|failure_signature=\\\$(\\|proc.stdout.strip" skills/loop/SKILL.md`

Expected: three matches confirming both the hard-rule prose, the shell one-liner, and the Python pattern's signature capture are in place.

- [ ] **Step 4: Run existing tests**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && pytest -x`

Expected: all tests pass (prose-only edit).

- [ ] **Step 5: Commit**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git add skills/loop/SKILL.md
git commit -m "$(cat <<'EOF'
loop: failure_signature is a hard rule (v0.10 edit B)

Reflect step must compute failure_signature via stall_check.py and embed it
directly in the iteration record — never empty, never a placeholder. Canonical
Python pattern now shows the subprocess capture and record insertion, not just
the temp-file lifecycle. The schema rejects non-hex values.

EOF
)"
```

---

## Task 5: Edit C — `exit_reason` enum table + "not `status`" note

Add a small markdown table immediately after the iteration record JSON template, enumerating the four legal `exit_reason` values and when to write each. Follow with a note making the field-name distinction explicit so subagents don't default to `status`.

**Files:**
- Modify: `skills/loop/SKILL.md` — insert new section after the iteration record template (after Task 3's new "adapter-output shape" paragraph, before the `notable: true` paragraph).

- [ ] **Step 1: Insert the enum table**

After Task 3's edits, the SKILL.md should have the "adapter-output shape" paragraph followed by the `notable: true` paragraph. Insert the enum table BETWEEN them.

Find the section (post-Task-3) containing:

```markdown
   ...The scripts accept flat-lists for backward compatibility with legacy iteration records, but this object form is the contract.

   Mark `notable: true` when the reflection surfaces a non-obvious lesson...
```

Insert the following between the two paragraphs:

```markdown

   **`exit_reason` values** — write exactly one per iteration record:

   | `exit_reason` value | When to write it |
   |---|---|
   | `"in_progress"` | Gates failed, budget remains, no stall detected. The loop will continue to iteration N+1. |
   | `"success"` | All gates passed (`gate_report.passed == true`). Terminal. |
   | `"budget_exhausted"` | This is iteration N and N ≥ `max_attempts`. Terminal with failure. |
   | `"stalled"` | `failure_signature` equals the previous iteration's `failure_signature`. Terminal with failure. |

   Write the field as `exit_reason`, not `status`. The schema, `scripts/stall_check.py`, `hooks/detect-resume.sh`, and `hooks/gate-guard.sh` all key off `exit_reason`. Using `status` will cause hooks to silently miss completed chunks and gate-guard to miss failing iterations. (The hooks do fall back to `status` for backward compatibility with pre-v0.10 records, but that fallback exists to rescue legacy data, not to license new drift.)

```

- [ ] **Step 2: Verify the table landed in the right place**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && grep -n "exit_reason. values\|Write the field as .exit_reason" skills/loop/SKILL.md`

Expected: two matches, both appearing between the "adapter-output shape" paragraph and the `notable: true` paragraph.

Run (visual sanity check):

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
sed -n '70,115p' skills/loop/SKILL.md
```

Expected: table renders cleanly in markdown; four rows; the "write the field as `exit_reason`, not `status`" note follows.

- [ ] **Step 3: Run existing tests**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && pytest -x`

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git add skills/loop/SKILL.md
git commit -m "$(cat <<'EOF'
loop: exit_reason enum table + "not status" note (v0.10 edit C)

Adds an inline four-row table enumerating in_progress / success /
budget_exhausted / stalled directly adjacent to the iteration record template.
Explicit note says "write exit_reason, not status" — the field-name drift
underlying v0.9 finding F5 (hooks missing 5 of 6 completed chunks).

EOF
)"
```

---

## Task 6: Schema — document `status` as deprecated alias

Add a `status` property to `schemas/iterations.schema.json` with a description that marks it as deprecated in favor of `exit_reason`. This is documentation-only: `additionalProperties: true` already accepts `status`. The explicit property makes the deprecation visible to anyone reading the schema without having to dig into hook source.

**Files:**
- Modify: `schemas/iterations.schema.json:71-75` (just after the `exit_reason` property)

- [ ] **Step 1: Add the deprecated `status` property**

Edit `/home/flip/Development/skillgoid/skillgoid-plugin/schemas/iterations.schema.json`. Find:

```json
    "exit_reason": {
      "type": "string",
      "enum": ["in_progress", "success", "budget_exhausted", "stalled"]
    }
  },
  "additionalProperties": true
}
```

Replace with:

```json
    "exit_reason": {
      "type": "string",
      "enum": ["in_progress", "success", "budget_exhausted", "stalled"]
    },
    "status": {
      "type": "string",
      "deprecated": true,
      "description": "Deprecated alias for exit_reason. Hooks (detect-resume.sh, gate-guard.sh) fall back to this field if exit_reason is absent, preserving legacy records. New records must use exit_reason; this entry documents the deprecation so readers don't rely on status."
    }
  },
  "additionalProperties": true
}
```

- [ ] **Step 2: Confirm the schema still parses as valid JSON**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && python -c "import json; json.loads(open('schemas/iterations.schema.json').read()); print('ok')"`

Expected: `ok`

- [ ] **Step 3: Confirm the schema still validates existing iteration records**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && pytest tests/test_schemas.py tests/test_validate_iteration.py -v`

Expected: all tests pass. Adding a sibling property under `properties` with `additionalProperties: true` already in place is strictly additive.

- [ ] **Step 4: Commit**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git add schemas/iterations.schema.json
git commit -m "$(cat <<'EOF'
schema: document status as deprecated alias for exit_reason

Adds status property to schemas/iterations.schema.json with deprecated: true
and a description. Documentation-only — additionalProperties: true already
accepted status. Makes the v0.9 hook fallback behavior visible to anyone
reading the schema instead of only in hook source.

EOF
)"
```

---

## Task 7: Full suite verification

Run the whole test suite to confirm no regressions across any component — prose edits shouldn't regress anything, but a prose-only release is still worth verifying end-to-end.

- [ ] **Step 1: Run the full suite**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && make test`

Expected: all tests pass, including the two new tests in `tests/test_v10_bundle.py`.

- [ ] **Step 2: Lint check**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && make lint`

Expected: no lint errors. The new test file uses `import subprocess, sys, json, pathlib` — all standard library, no `print` calls (T201 rule), no line-length issues.

- [ ] **Step 3: Verify git state is clean and commits are coherent**

Run:

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git status
git log --oneline -8
```

Expected:
- Clean working tree.
- Six commits since the v0.9.0 tag (or since `e7071f2` spec fix): Test B, Test A, Edit A, Edit B, Edit C, Schema. Task 7 itself does not commit — it is verification only.

- [ ] **Step 4: Tag v0.10.0**

Run:

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git tag -a v0.10.0 -m "v0.10 iteration contract bundle — SKILL.md is now authoritative"
git log --oneline v0.9.0..v0.10.0
```

Expected: tag created; log lists the six v0.10 commits.

---

## Self-Review Checklist

Coverage against spec success criteria:

1. ✅ Concrete JSON example for `gate_report` with field names spelled out → Task 3
2. ✅ `failure_signature` hard rule with one-liner → Task 4
3. ✅ `exit_reason` enum table inline → Task 5
4. ✅ "Write `exit_reason`, not `status`" note → Task 5
5. ✅ `status` documented as deprecated in schema → Task 6
6. ✅ `tests/test_v10_bundle.py` passes (H9 + stall contract) → Tasks 1, 2
7. ✅ Existing suite still passes → Tasks 3, 4, 5, 6 all run `pytest -x`; Task 7 runs full suite + lint

No placeholders, no TBDs, no "similar to Task N" — every task shows exact file paths, exact text, and exact commands with expected output.

Type/signature consistency:
- `signature(record: dict) -> str` imported from `scripts.stall_check` — matches `scripts/stall_check.py:29`.
- `metrics_append.py --skillgoid-dir <path> --slug <slug>` CLI — matches `scripts/metrics_append.py:158-160`.
- `gate_report` object form `{"passed": bool, "results": [...]}` — matches `scripts/measure_python.py:389-390` and `schemas/iterations.schema.json:30-53`.
- `exit_reason` enum values match `schemas/iterations.schema.json:73` exactly.
