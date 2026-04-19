# skillgoid v0.11.1 — Subagent Auto-Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When Stage 2 of `synthesize-gates` rejects subagent output, re-dispatch the subagent once with the rejection reason appended, accept the retry on success, STOP on second failure.

**Architecture:** The retry lives in `skills/synthesize-gates/SKILL.md` prose (step 6), not in Python — the synthesis subagent is dispatched via the Agent tool from within the skill. `scripts/synthesize/synthesize.py` is unchanged; its existing stderr becomes the retry signal. Tests assert the prose contract (grep-style) because the retry itself is only reachable in a live skill invocation.

**Tech Stack:** Python 3.11+ (pytest for contract tests), Markdown (SKILL.md), Claude Code Agent tool (dispatch path, not code).

**Spec:** `docs/superpowers/specs/2026-04-19-skillgoid-v0.11.1-subagent-retry-design.md`

---

## File Map

- `tests/test_synthesize_gates_skill.py` — **modify**: add three grep-contract tests for the retry prose.
- `skills/synthesize-gates/SKILL.md` — **modify**: rewrite step 6 as a two-attempt loop; update "Phase 1 / 2 progress" section.
- `.claude-plugin/plugin.json` — **modify**: version `0.11.0` → `0.11.1`.
- `CHANGELOG.md` — **modify**: add v0.11.1 entry above the 0.11.0 entry.

No new files. No Python source changes. No schema changes.

---

## Task 1: Add contract tests for retry prose

**Files:**
- Modify: `tests/test_synthesize_gates_skill.py`

These three tests encode the prose contract: the retry prompt text is present, the two-failure STOP message is present, and the stale Phase-1 note is gone. Writing them first and watching them fail is the TDD marker for the SKILL.md edit in Task 2.

- [ ] **Step 1: Add the three failing assertions**

Append to `tests/test_synthesize_gates_skill.py` (after the existing `test_skill_phase2_limitations_reflect_v011_oracle` function):

```python


def test_skill_documents_stage2_retry_prompt():
    text = SKILL.read_text()
    assert "Your previous output failed Stage 2 validation" in text, (
        "SKILL.md step 6 must instruct the retry to surface the Stage 2 stderr "
        "to the subagent. See v0.11.1 spec."
    )


def test_skill_documents_retry_stop_condition():
    text = SKILL.read_text()
    assert "failed Stage 2 validation twice" in text, (
        "SKILL.md step 6 must document the STOP condition after two failed attempts."
    )


def test_skill_removes_stale_phase1_no_retry_text():
    text = SKILL.read_text()
    assert "Phase 2 will add a single auto-retry" not in text, (
        "Stale pre-v0.11.1 note must be removed when retry ships."
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
pytest tests/test_synthesize_gates_skill.py -v
```

Expected: the three new tests FAIL; the four pre-existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_synthesize_gates_skill.py
git commit -m "test(synthesize-gates): contract tests for Stage 2 retry prose"
```

---

## Task 2: Rewrite SKILL.md step 6 as a two-attempt loop

**Files:**
- Modify: `skills/synthesize-gates/SKILL.md` (step 6, around lines 63–68)

Step 6 currently says "Do not retry the subagent in Phase 1 — surface the failure so the user can re-run or hand-author. Phase 2 will add a single auto-retry." This task replaces that sentence with the retry loop specified in the design.

- [ ] **Step 1: Replace step 6**

Find in `skills/synthesize-gates/SKILL.md`:

```markdown
6. **Run Stage 2 (parse + validate).** Shell out:
   ```bash
   echo "$subagent_stdout" | python <plugin-root>/scripts/synthesize/synthesize.py \
     --skillgoid-dir .skillgoid
   ```
   If the parser exits non-zero, surface its stderr (which names the violated rule) and STOP. Do not retry the subagent in Phase 1 — surface the failure so the user can re-run or hand-author. Phase 2 will add a single auto-retry.
```

Replace with:

````markdown
6. **Run Stage 2 (parse + validate), with one auto-retry.**

   **Attempt 1.** Shell out:
   ```bash
   echo "$subagent_stdout" | python <plugin-root>/scripts/synthesize/synthesize.py \
     --skillgoid-dir .skillgoid
   ```
   On exit 0, proceed to step 7. On exit 1, capture the parser's stderr as `attempt1_stderr` and proceed to Attempt 2.

   **Attempt 2.** Re-dispatch the synthesis subagent with the **same** Agent-tool invocation as step 5, but append this block to the end of the `prompt` string (after the two `<attachment>` blocks):

   > Your previous output failed Stage 2 validation with:
   > ```
   > {attempt1_stderr}
   > ```
   > Re-emit the drafts JSON with this problem fixed. Do not include any prose — only valid JSON.

   Capture the retry's final text output as `retry_stdout`. Shell out:
   ```bash
   echo "$retry_stdout" | python <plugin-root>/scripts/synthesize/synthesize.py \
     --skillgoid-dir .skillgoid
   ```
   On exit 0, proceed to step 7 (the retry is the canonical drafts.json). On exit 1, capture stderr as `attempt2_stderr`, surface both messages to the user, and STOP:

   > Synthesis subagent failed Stage 2 validation twice. Re-run the skill or hand-author `.skillgoid/criteria.yaml`.
   >
   > Attempt 1 stderr:
   > {attempt1_stderr}
   >
   > Attempt 2 stderr:
   > {attempt2_stderr}
````

- [ ] **Step 2: Update the "Phase 1 / 2 progress" section**

In `skills/synthesize-gates/SKILL.md`, find the bullet:

```markdown
- **Remaining Phase 2 work (v0.13/v0.14)**: context7 grounding; curated template fallback for cold-start projects; oracle for context7/template-sourced gates; subagent auto-retry on Stage 2 validation failure.
```

Replace with:

```markdown
- **Remaining Phase 2 work (v0.13/v0.14)**: context7 grounding; curated template fallback for cold-start projects; oracle for context7/template-sourced gates.
- **v0.11.1**: one auto-retry on Stage 2 validation failure. If the subagent emits invalid drafts, the skill re-dispatches once with the rejection reason appended, then STOPs if the retry also fails.
```

- [ ] **Step 3: Run the contract tests to verify they pass**

Run:
```bash
pytest tests/test_synthesize_gates_skill.py -v
```

Expected: all 7 tests PASS (4 original + 3 new from Task 1).

- [ ] **Step 4: Run the full suite**

Run:
```bash
pytest
```

Expected: 355/355 pass (352 from v0.11 + 3 new contract tests). No regressions.

- [ ] **Step 5: Lint**

Run:
```bash
ruff check .
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add skills/synthesize-gates/SKILL.md
git commit -m "feat(synthesize-gates): one auto-retry on Stage 2 validation failure"
```

---

## Task 3: Version bump + CHANGELOG entry

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump version in plugin.json**

In `.claude-plugin/plugin.json`, change:

```json
  "version": "0.11.0",
```

to:

```json
  "version": "0.11.1",
```

- [ ] **Step 2: Add CHANGELOG entry**

In `CHANGELOG.md`, insert a new section above the `## 0.11.0 (2026-04-19)` heading:

```markdown
## 0.11.1 (2026-04-19)

### Features

- `synthesize-gates` Stage 2 now auto-retries the synthesis subagent **once** when draft validation fails. The parser's stderr (naming the violated rule — bad provenance ref, missing field, unsupported gate type, etc.) is appended to the subagent's prompt on the retry. If the second attempt also fails, both stderr messages are surfaced and the skill STOPs.

### Notes

- Retry budget is hardcoded at 1 (2 attempts total). Malformed output on both attempts is treated as a non-transient failure — re-run the skill or hand-author `criteria.yaml`.
- No behavioral change to `scripts/synthesize/synthesize.py`; its exit code and stderr format are unchanged.
- No breaking changes.
```

- [ ] **Step 3: Run the full suite one more time**

Run:
```bash
pytest
```

Expected: 355/355 pass.

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json CHANGELOG.md
git commit -m "chore(release): v0.11.1 — subagent auto-retry on Stage 2 failure"
```

---

## Task 4: Release

**Files:** none

Manual verification of the retry flow cannot be scripted (requires a live Agent-tool dispatch). Document that it is pending, then tag.

- [ ] **Step 1: Final lint + test check**

Run:
```bash
pytest && ruff check .
```

Expected: tests green, lint clean.

- [ ] **Step 2: Push main**

Run:
```bash
git push origin main
```

Expected: three new commits (tests, feature, release) land on origin.

- [ ] **Step 3: Tag v0.11.1 at the release commit**

The release commit is the most recent commit on `main` (the `chore(release)` commit from Task 3).

Run:
```bash
git tag -a v0.11.1 -m "v0.11.1: subagent auto-retry on Stage 2 validation failure"
git push origin v0.11.1
```

Expected: remote shows tag `v0.11.1`.

- [ ] **Step 4: Manual retry verification (post-release smoke test)**

This is a **manual** verification step — cannot be automated. Perform once after tag:

1. In a scratch workspace, set up a minimal grounding.json with one real observation.
2. Hand-craft a subagent-style stdout that cites a ref NOT in grounding.json (e.g., `"provenance": {"ref": "does/not/exist.py"}`).
3. Invoke `/skillgoid:synthesize-gates` with this contrived setup (or dry-run the retry block by feeding the crafted stdout through the skill manually).
4. Confirm: the skill detects exit 1, re-dispatches with the stderr in the prompt, and either succeeds (if the subagent corrects) or STOPs with both stderrs surfaced.

If the manual verification reveals prose issues (e.g., the subagent doesn't parse the instruction block correctly), file a follow-up and iterate.

---

## Self-Review Checklist

**Spec coverage:**
- Spec "Attempt 1" / "Attempt 2" flow → Task 2 step 1.
- Spec "Retry prompt shape: raw stderr appended verbatim" → Task 2 step 1 (the `{attempt1_stderr}` interpolation in the prompt block).
- Spec "STOP message" → Task 2 step 1 (the second blockquote).
- Spec "Files changed: SKILL.md step 6" → Task 2.
- Spec "Files changed: SKILL.md Phase 1 / 2 progress" → Task 2 step 2.
- Spec "Files changed: tests/test_synthesize_gates_skill.py" → Task 1.
- Spec "Files changed: CHANGELOG.md" → Task 3 step 2.
- Spec "Files changed: plugin.json" → Task 3 step 1.
- Spec "Release checklist: tag v0.11.1, push tag" → Task 4 steps 2–3.
- Spec "Manual retry verification" → Task 4 step 4.
- Spec "Not changing: synthesize.py" → honored (no source task).

**Placeholder scan:** No TBD / TODO / "Similar to Task N" / vague steps present.

**Type consistency:** Variable names (`attempt1_stderr`, `attempt2_stderr`, `retry_stdout`, `subagent_stdout`) are consistent between the prose and the STOP message template.
