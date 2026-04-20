# skillgoid v0.12 — Context7 Advisory Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `plan` and `build` subagents a concise, framework-specific advisory grounding file derived from the `context7` MCP, so blueprints and per-chunk code prefer current idioms. Grounding is advisory — subagents may deviate. Missing MCP → graceful skip.

**Architecture:** `plan` dispatches a **one-shot context7 fetcher subagent** before writing `blueprint.md`. The fetcher infers the primary framework from `goal.md` + manifest files, queries the `context7` MCP, and writes `.skillgoid/context7/framework-grounding.md` (≤2000 tokens, three sections). If anything goes wrong, it writes `.skillgoid/context7/SKIPPED` instead — the pipeline continues unaffected. `plan` reads the file when drafting the blueprint; `build` attaches it to every per-chunk subagent dispatch. A new `--refresh-context7` flag on `plan` forces regeneration. No Python source changes; all behavior lives in skill prose and a new fetcher prompt.

**Tech Stack:** Python 3.11+ (pytest for prose-contract tests), Markdown (SKILL.md + fetcher prompt), Claude Code Agent tool (fetcher + per-chunk dispatch paths, not code).

**Spec:** `docs/superpowers/specs/2026-04-19-skillgoid-v0.12-context7-advisory-grounding-design.md`

---

## File Map

- `tests/test_plan_skill.py` — **create**: grep-contract tests for the new step 2.5 prose, the blueprint-bullet reference, and the `--refresh-context7` flag handling.
- `tests/test_build_skill.py` — **create**: grep-contract test that the per-chunk dispatch prose references `.skillgoid/context7/framework-grounding.md` as an attachment.
- `tests/test_context7_fetcher_prompt.py` — **create**: grep-contract tests that the new fetcher prompt contains goal/manifest reading instructions, the MCP name, the `SKIPPED:` signal, and the three-section output schema.
- `skills/plan/prompts/context7-fetcher.md` — **create new file** (and new `skills/plan/prompts/` subdirectory). Prompt body for the one-shot context7 fetcher subagent.
- `skills/plan/SKILL.md` — **modify**: add step 2.5 (fetcher dispatch + SKIPPED handling), add bullet to step 3 (prefer idioms when drafting blueprint), add `--refresh-context7` flag semantics.
- `skills/build/SKILL.md` — **modify**: step 3b / 3c — attach `.skillgoid/context7/framework-grounding.md` to each chunk's subagent prompt when present, with advisory wording.
- `.claude-plugin/plugin.json` — **modify**: version `0.11.1` → `0.12.0`.
- `CHANGELOG.md` — **modify**: add v0.12.0 entry above the 0.11.1 entry.

No Python source changes. No schema changes. No fixture changes.

---

## Task 1: Add contract tests for plan, build, and fetcher prose

**Files:**
- Create: `tests/test_plan_skill.py`
- Create: `tests/test_build_skill.py`
- Create: `tests/test_context7_fetcher_prompt.py`

These tests encode the prose contract: the new plan step references context7 + the grounding file + the SKIPPED sentinel + the fetcher prompt, build's dispatch mentions the grounding attachment, and the fetcher prompt covers goal reading, manifest reading, the MCP name, the SKIPPED signal, and the three-section output schema. Writing them first and watching them fail is the TDD marker for the file creations in Tasks 2–4.

- [ ] **Step 1: Create `tests/test_plan_skill.py`**

Write to `tests/test_plan_skill.py`:

```python
"""Prose-contract tests for skills/plan/SKILL.md (v0.12: context7 grounding)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).parent.parent / "skills" / "plan" / "SKILL.md"


def test_plan_skill_references_context7():
    text = SKILL.read_text()
    assert "context7" in text, (
        "SKILL.md must reference context7 in the new step 2.5. See v0.12 spec."
    )


def test_plan_skill_references_grounding_file_path():
    text = SKILL.read_text()
    assert ".skillgoid/context7/framework-grounding.md" in text, (
        "SKILL.md must name the grounding file path explicitly. See v0.12 spec."
    )


def test_plan_skill_references_skipped_sentinel():
    text = SKILL.read_text()
    assert ".skillgoid/context7/SKIPPED" in text, (
        "SKILL.md must name the SKIPPED sentinel path explicitly. See v0.12 spec."
    )


def test_plan_skill_dispatches_context7_fetcher():
    text = SKILL.read_text()
    assert "context7-fetcher" in text, (
        "SKILL.md step 2.5 must reference the fetcher prompt path (context7-fetcher.md). "
        "See v0.12 spec."
    )


def test_plan_skill_documents_refresh_flag():
    text = SKILL.read_text()
    assert "--refresh-context7" in text, (
        "SKILL.md must document the --refresh-context7 flag. See v0.12 spec."
    )
```

- [ ] **Step 2: Create `tests/test_build_skill.py`**

Write to `tests/test_build_skill.py`:

```python
"""Prose-contract tests for skills/build/SKILL.md (v0.12: context7 grounding attachment)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).parent.parent / "skills" / "build" / "SKILL.md"


def test_build_skill_attaches_context7_grounding():
    text = SKILL.read_text()
    assert ".skillgoid/context7/framework-grounding.md" in text, (
        "SKILL.md step 3b/3c must reference the grounding file as a per-chunk "
        "subagent attachment. See v0.12 spec."
    )


def test_build_skill_marks_grounding_advisory():
    text = SKILL.read_text()
    assert "advisory" in text.lower(), (
        "SKILL.md must label the context7 grounding attachment as advisory so the "
        "chunk subagent doesn't treat it as a requirements document. See v0.12 spec."
    )
```

- [ ] **Step 3: Create `tests/test_context7_fetcher_prompt.py`**

Write to `tests/test_context7_fetcher_prompt.py`:

```python
"""Prose-contract tests for skills/plan/prompts/context7-fetcher.md (v0.12)."""
from __future__ import annotations

from pathlib import Path

PROMPT = (
    Path(__file__).parent.parent
    / "skills"
    / "plan"
    / "prompts"
    / "context7-fetcher.md"
)


def test_fetcher_prompt_exists():
    assert PROMPT.exists(), (
        "skills/plan/prompts/context7-fetcher.md must exist (new file in v0.12)."
    )


def test_fetcher_prompt_reads_goal():
    text = PROMPT.read_text()
    assert "goal.md" in text, (
        "Fetcher prompt must instruct the subagent to read .skillgoid/goal.md."
    )


def test_fetcher_prompt_reads_manifest():
    text = PROMPT.read_text()
    assert "pyproject.toml" in text, (
        "Fetcher prompt must instruct the subagent to read at least one manifest "
        "file (pyproject.toml as the canonical example)."
    )


def test_fetcher_prompt_names_context7_mcp():
    text = PROMPT.read_text()
    assert "context7" in text, (
        "Fetcher prompt must reference the context7 MCP by name."
    )


def test_fetcher_prompt_documents_skipped_signal():
    text = PROMPT.read_text()
    assert "SKIPPED:" in text, (
        "Fetcher prompt must document the 'SKIPPED: <reason>' stdout signal for "
        "graceful failure."
    )


def test_fetcher_prompt_documents_output_schema():
    text = PROMPT.read_text()
    assert "Project structure" in text, (
        "Fetcher prompt must require a '## Project structure' output section."
    )
    assert "Testing patterns" in text, (
        "Fetcher prompt must require a '## Testing patterns' output section."
    )
    assert "Common pitfalls" in text, (
        "Fetcher prompt must require a '## Common pitfalls' output section."
    )
```

- [ ] **Step 4: Run the tests to verify they fail**

Run:
```bash
pytest tests/test_plan_skill.py tests/test_build_skill.py tests/test_context7_fetcher_prompt.py -v
```

Expected: every new test FAILS — plan tests fail because SKILL.md has no context7 prose yet, build test fails because the attachment isn't wired, fetcher-prompt tests fail because the file doesn't exist.

- [ ] **Step 5: Commit**

```bash
git add tests/test_plan_skill.py tests/test_build_skill.py tests/test_context7_fetcher_prompt.py
git commit -m "test(plan,build): contract tests for context7 advisory grounding prose"
```

---

## Task 2: Create the context7 fetcher prompt

**Files:**
- Create: `skills/plan/prompts/context7-fetcher.md` (also creates `skills/plan/prompts/` directory)

The fetcher prompt is the body dispatched to a one-shot subagent from plan step 2.5. It must instruct the subagent to (1) read the goal + manifests, (2) infer the primary framework, (3) query the context7 MCP, (4) emit three-section Markdown ≤2000 tokens, (5) emit `SKIPPED: <reason>` on any failure. This task satisfies `tests/test_context7_fetcher_prompt.py` from Task 1.

- [ ] **Step 1: Write `skills/plan/prompts/context7-fetcher.md`**

Write to `skills/plan/prompts/context7-fetcher.md`:

````markdown
# context7 fetcher — one-shot subagent

You are a one-shot subagent dispatched from `skills/plan/SKILL.md` step 2.5.
Your job is to produce a short, framework-specific advisory grounding file
(or gracefully decline) that the plan + build pipeline will attach to later
subagent prompts. Your output is **advisory** — downstream agents may
deviate. Your output is **not** a requirements document.

## Procedure

1. Read `.skillgoid/goal.md`.
2. Read whichever of these manifest files exist at the project root:
   - `pyproject.toml`
   - `package.json`
   - `go.mod`
   - `Cargo.toml`
3. Infer the **primary application framework** (e.g. Flask, FastAPI,
   Django, Express, Next.js, Cobra, Axum). Prefer the framework that the
   goal is actually building against; a transitive dependency listed only
   in the manifest is not the primary framework.
   - If you cannot identify a primary framework with reasonable confidence,
     emit `SKIPPED: framework inference inconclusive` to stdout and stop.
4. Query the `context7` MCP for current documentation on that framework's:
   - idiomatic project structure,
   - testing patterns,
   - common pitfalls.
   Target: combined grounding ≤2000 tokens. Prefer density over breadth.
   - If the `context7` MCP is not available in this session, emit
     `SKIPPED: context7 MCP not available` to stdout and stop.
   - If every context7 query errors, emit
     `SKIPPED: context7 queries failed` to stdout and stop.
5. Emit Markdown to stdout with exactly three top-level sections, in this
   order, and no prose preamble:

   ```markdown
   ## Project structure

   <framework-idiomatic layout notes, ≤600 tokens>

   ## Testing patterns

   <framework-idiomatic testing notes, ≤600 tokens>

   ## Common pitfalls

   <non-obvious gotchas worth flagging, ≤600 tokens>
   ```

## Failure contract

Any failure (manifest missing, framework unclear, MCP unreachable, query
errors) → emit a single line starting with `SKIPPED: <reason>` to stdout
and stop. The caller interprets that prefix as a graceful skip and the
pipeline continues unaffected. Do **not** emit partial grounding + a
SKIPPED line — pick one.

## Style

- No preamble, no prose framing, no "here is the grounding" intro.
- Bullet-heavy. Short declarative sentences.
- Name specific idioms (e.g. "Flask uses an app factory in
  `app/__init__.py`"), not generic advice.
- If a section would be empty or vague, say so in one bullet rather than
  padding.
````

- [ ] **Step 2: Run the fetcher-prompt tests to verify they pass**

Run:
```bash
pytest tests/test_context7_fetcher_prompt.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add skills/plan/prompts/context7-fetcher.md
git commit -m "feat(plan): context7 fetcher prompt (new subagent body for v0.12)"
```

---

## Task 3: Wire context7 grounding into plan

**Files:**
- Modify: `skills/plan/SKILL.md`

Add step 2.5 (fetcher dispatch + SKIPPED handling), add a bullet to step 3 that tells the controlling Claude to prefer the grounding's idioms when drafting `blueprint.md`, and introduce `--refresh-context7` flag parsing. This task satisfies `tests/test_plan_skill.py` from Task 1.

- [ ] **Step 1: Insert a new step 2.5 between current steps 2 and 3**

Open `skills/plan/SKILL.md`. Find this sequence in the Procedure:

```markdown
2. **Read** the goal, criteria, and any past-lesson summary still in context from `skillgoid:retrieve`.
3. **Write `blueprint.md`** covering:
```

Replace with:

````markdown
2. **Read** the goal, criteria, and any past-lesson summary still in context from `skillgoid:retrieve`.

2.5. **context7 grounding (advisory).** Before drafting the blueprint, make one lightweight attempt to produce a framework-specific advisory grounding file. This is best-effort and never blocks progress.

   Procedure:
   1. If `--refresh-context7` was passed to this skill, delete `.skillgoid/context7/framework-grounding.md` and `.skillgoid/context7/SKIPPED` if either exists. Then continue.
   2. If `.skillgoid/context7/framework-grounding.md` already exists (non-empty), skip the rest of step 2.5 — reuse the existing file.
   3. If `.skillgoid/context7/SKIPPED` exists, skip the rest of step 2.5 — honour the prior skip.
   4. Otherwise, ensure `.skillgoid/context7/` exists and dispatch the context7 fetcher subagent via the Agent tool. Use the prompt body at `skills/plan/prompts/context7-fetcher.md` (read the file and pass its contents as the `prompt` field).
      ```
      Agent(
        subagent_type="general-purpose",
        description="Fetch context7 framework grounding",
        prompt=<contents of skills/plan/prompts/context7-fetcher.md>,
      )
      ```
   5. Capture the fetcher subagent's final text output.
      - If it starts with `SKIPPED:`, write the remainder of the line (after `SKIPPED: `) to `.skillgoid/context7/SKIPPED` and continue to step 3 — do not create `framework-grounding.md`.
      - Otherwise, write the full output to `.skillgoid/context7/framework-grounding.md`.
   6. Treat any fetcher-side error (subagent failure, tool errors) as a graceful skip: write `.skillgoid/context7/SKIPPED` with a one-line reason (e.g. `fetcher dispatch failed`) and continue.

   Fetcher failures are warnings, not errors. Never abort `plan` because of step 2.5.
3. **Write `blueprint.md`** covering:
````

- [ ] **Step 2: Add a bullet to step 3 referencing the grounding file**

Still in `skills/plan/SKILL.md`, find the existing list of bullets under `3. **Write `blueprint.md`** covering:`. The list currently ends with:

```markdown
   - External dependencies
```

Add **one more bullet** immediately after:

```markdown
   - **Context7 grounding (if present).** If `.skillgoid/context7/framework-grounding.md` exists and is non-empty, read it before drafting the blueprint and prefer the idioms it surfaces (project structure, testing patterns, common pitfalls). It is **advisory framework guidance**, not a requirements document — deviate when the goal or criteria demand it. If the file is missing or `.skillgoid/context7/SKIPPED` exists, proceed without it.
```

- [ ] **Step 3: Document the `--refresh-context7` flag**

Still in `skills/plan/SKILL.md`, find the `## Inputs` section:

```markdown
## Inputs

- `.skillgoid/goal.md`
- `.skillgoid/criteria.yaml`
```

Immediately after it, insert a new section:

```markdown
## Flags

- `--refresh-context7` — delete `.skillgoid/context7/framework-grounding.md` and `.skillgoid/context7/SKIPPED` (if present) before step 2.5, forcing the fetcher to re-run and regenerate the grounding. Use this when the framework changed, the goal changed in a way that needs fresh docs, or hand-edits to the grounding file should be discarded. This flag lives on `plan` (not `build`) because `build resume` does not re-invoke `plan`.
```

- [ ] **Step 4: Run the plan tests to verify they pass**

Run:
```bash
pytest tests/test_plan_skill.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Run the full suite**

Run:
```bash
pytest
```

Expected: no regressions. All pre-existing tests plus the v0.12 tests added so far (Task 1 fetcher tests + Task 3 plan tests) pass. Build tests from Task 1 may still fail — that's addressed in Task 4.

- [ ] **Step 6: Commit**

```bash
git add skills/plan/SKILL.md
git commit -m "feat(plan): context7 advisory grounding + --refresh-context7 flag"
```

---

## Task 4: Attach grounding to per-chunk subagent dispatch in build

**Files:**
- Modify: `skills/build/SKILL.md`

Extend step 3b (context assembly) and step 3c (dispatch) so the per-chunk subagent prompt includes `.skillgoid/context7/framework-grounding.md` as an advisory attachment when the file is present. This task satisfies `tests/test_build_skill.py` from Task 1.

- [ ] **Step 1: Add a new context slice entry in step 3b**

Open `skills/build/SKILL.md`. Find the bulleted list inside step 3b:

```markdown
   3b. Build the subagent prompt with the curated context slice:
      - The chunk entry as YAML (id, description, gate_ids, language, depends_on, paths, gate_overrides). The `paths:` field is consumed by `git_iter_commit.py` at commit time. `gate_overrides` (v0.8) is consumed by the subagent when building its criteria subset per `skills/loop/SKILL.md` step 3.1. Pass both through verbatim.
      - `retrieve_summary` verbatim
```

Insert a new bullet immediately after `retrieve_summary verbatim`:

```markdown
      - **Context7 grounding (advisory, v0.12).** If `.skillgoid/context7/framework-grounding.md` exists and is non-empty, attach its full contents as an advisory section of the subagent prompt labelled "Framework grounding (advisory — context7)". If the file is missing or `.skillgoid/context7/SKIPPED` exists, omit the section entirely. The grounding is a best-effort snapshot of idiomatic framework patterns — the chunk subagent should **prefer** the idioms when they apply but must not treat the attachment as a requirements document and must not fight the framework's actual APIs.
```

- [ ] **Step 2: Reinforce the advisory framing in step 3c's prompt guidance**

Still in `skills/build/SKILL.md`, find this sentence in step 3c (right after the `Agent(...)` block):

```markdown
      When multiple chunks are in the same wave, these dispatches run in parallel. Claude Code's `Agent` tool supports concurrent subagent invocation — issue all the wave's `Agent()` tool calls in a single message so they execute in parallel.
```

Immediately **after** that paragraph, add:

```markdown
      If the prompt includes the "Framework grounding (advisory — context7)" section from step 3b, the prompt must also instruct the subagent: "Treat the framework grounding as advisory — prefer its idioms when they apply; don't fight the framework. It is not a requirements document." This keeps the chunk subagent from over-indexing on grounding that may be slightly out of date or off-topic for the specific chunk.
```

- [ ] **Step 3: Run the build tests to verify they pass**

Run:
```bash
pytest tests/test_build_skill.py -v
```

Expected: both tests PASS.

- [ ] **Step 4: Run the full suite**

Run:
```bash
pytest
```

Expected: no regressions.

- [ ] **Step 5: Lint**

Run:
```bash
ruff check .
```

Expected: clean. (If `ruff` isn't on PATH, `uv run ruff check .` also works.)

- [ ] **Step 6: Commit**

```bash
git add skills/build/SKILL.md
git commit -m "feat(build): attach context7 advisory grounding to per-chunk subagent dispatch"
```

---

## Task 5: Version bump + CHANGELOG entry

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump version in `.claude-plugin/plugin.json`**

Open `.claude-plugin/plugin.json`. Change:

```json
  "version": "0.11.1",
```

to:

```json
  "version": "0.12.0",
```

- [ ] **Step 2: Add CHANGELOG entry**

Open `CHANGELOG.md`. Insert a new section above the existing `## 0.11.1 (2026-04-19)` heading:

```markdown
## 0.12.0 (2026-04-19)

### Features

- `plan` now dispatches a one-shot **context7 fetcher subagent** before drafting the blueprint. The fetcher infers the primary application framework from `goal.md` + manifest files (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`), queries the `context7` MCP for current docs, and writes `.skillgoid/context7/framework-grounding.md` (≤2000 tokens, three sections: project structure, testing patterns, common pitfalls).
- `plan` reads the grounding file (when present) as advisory guidance while drafting `blueprint.md` — preferring framework idioms where applicable.
- `build` attaches the grounding file to every per-chunk subagent dispatch as an **advisory** section. Chunk subagents prefer the idioms but may deviate.
- New `--refresh-context7` flag on `plan` deletes the grounding file and any `SKIPPED` sentinel, forcing the fetcher to re-run. The flag lives on `plan` (not `build`) because `build resume` does not re-invoke `plan`.
- Graceful skip: if the `context7` MCP is missing, the framework is inconclusive, or any query fails, the fetcher writes `.skillgoid/context7/SKIPPED` with a one-line reason and the pipeline continues unaffected.

### Notes

- Hand-edits to `.skillgoid/context7/framework-grounding.md` are preserved across re-runs of `plan` — the fetcher only writes when the file is missing. Use `--refresh-context7` to discard hand-edits.
- The fetcher is a subagent dispatch, not Python code. `plan` itself remains a prose skill run by the controlling Claude.
- Token cost: attaching a 2k-token grounding to every chunk dispatch × N chunks × M iterations adds up quickly. Acceptable at the current per-project chunk scale; revisit if projects routinely exceed 30+ chunks per build.
- No breaking changes. Projects without the `context7` MCP installed get the graceful-skip path.

### Not changing

- `scripts/synthesize/synthesize.py` and all other Stage 1–4 scripts.
- `schemas/criteria.schema.json`, `schemas/chunks.schema.json`.
- The `synthesize-gates` skill — context7 grounding for criteria synthesis is a separate roadmap item (future release).
- Hooks (`hooks/gate-guard.sh`, `hooks/detect-resume.sh`).
```

- [ ] **Step 3: Run the full suite one more time**

Run:
```bash
pytest
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json CHANGELOG.md
git commit -m "chore(release): v0.12.0 — context7 advisory grounding for plan + build"
```

---

## Task 6: Release

**Files:** none

Manual verification of the full fetcher flow requires a real framework project and a live `context7` MCP; document the steps, then tag.

- [ ] **Step 1: Final lint + test check**

Run:
```bash
pytest && ruff check .
```

Expected: tests green, lint clean. (If `ruff` isn't on PATH, `uv run ruff check .` works.)

- [ ] **Step 2: Push main**

Run:
```bash
git push origin main
```

Expected: the new commits (tests, fetcher prompt, plan edits, build edits, release) land on origin.

- [ ] **Step 3: Tag v0.12.0 at the release commit**

The release commit is the most recent commit on `main` (the `chore(release)` commit from Task 5).

Run:
```bash
git tag -a v0.12.0 -m "v0.12.0: context7 advisory grounding for plan + build"
git push origin v0.12.0
```

Expected: remote shows tag `v0.12.0`.

- [ ] **Step 4: Manual verification (post-release smoke test)**

These steps are **manual** — they require a live framework project and the `context7` MCP installed in the user's Claude Code session. Perform once after tag:

1. In a scratch workspace, set up a minimal Flask (or FastAPI) project with a non-trivial `goal.md` that references the framework by name, plus a `pyproject.toml` listing it as a dependency.
2. Run `/skillgoid:clarify` to populate `goal.md` + `criteria.yaml` if not already done.
3. Run `/skillgoid:plan`. Confirm:
   - `.skillgoid/context7/framework-grounding.md` exists, non-empty, and has three top-level sections: `## Project structure`, `## Testing patterns`, `## Common pitfalls`.
   - `blueprint.md` references idioms from the grounding where applicable (or clearly chose to deviate).
4. Run `/skillgoid:plan --refresh-context7`. Confirm the grounding file is regenerated (mtime changes, content may differ).
5. In a separate workspace **without** the `context7` MCP installed, run `/skillgoid:plan`. Confirm:
   - `.skillgoid/context7/SKIPPED` is created with a reason like `context7 MCP not available`.
   - `plan` proceeds and writes `blueprint.md` + `chunks.yaml` normally.
6. (Optional end-to-end) Run `/skillgoid:build` on the first project. Confirm each per-chunk subagent prompt includes the "Framework grounding (advisory — context7)" section when inspected via logs or resume summaries.

If any manual step fails, file a follow-up and iterate. Prose edits in SKILL.md or the fetcher prompt can ship as a patch release (v0.12.1) without re-opening the spec.

---

## Self-Review Checklist

**Spec coverage:**
- Spec "Single fetch at plan time, reused through build" → Task 3 step 1 (plan dispatch) + Task 4 steps 1–2 (build attachment).
- Spec "Graceful skip: SKIPPED sentinel" → Task 2 (fetcher prompt SKIPPED: contract) + Task 3 step 1 (plan's SKIPPED handling) + Task 4 step 1 (build's SKIPPED gating).
- Spec "Cache + refresh: `--refresh-context7` flag on `plan`" → Task 3 step 3.
- Spec "Framework detection lives in the fetcher" → Task 2 step 1 (fetcher prompt infers from goal + manifests).
- Spec "Files changed: `skills/plan/SKILL.md`" → Task 3.
- Spec "Files changed: `skills/build/SKILL.md`" → Task 4.
- Spec "Files changed: `skills/plan/prompts/context7-fetcher.md` (new file, new subdir)" → Task 2.
- Spec "Files changed: `CHANGELOG.md`" → Task 5 step 2.
- Spec "Files changed: `.claude-plugin/plugin.json`" → Task 5 step 1.
- Spec "Tests: test_plan_skill.py, test_build_skill.py, test_context7_fetcher_prompt.py" → Task 1.
- Spec "Release checklist: tag v0.12.0, push tag" → Task 6 steps 2–3.
- Spec "Manual verification (required)" → Task 6 step 4.
- Spec "Not changing: synthesize, schemas, hooks" → honored (no tasks touch them).

**Placeholder scan:** No TBD / TODO / "Similar to Task N" / vague steps present. Every code block contains the actual content the engineer will write.

**Type consistency:** File paths are consistent across tasks (`.skillgoid/context7/framework-grounding.md`, `.skillgoid/context7/SKIPPED`, `skills/plan/prompts/context7-fetcher.md`). Flag name `--refresh-context7` is identical everywhere. Output-section names (`Project structure`, `Testing patterns`, `Common pitfalls`) match between the fetcher prompt (Task 2) and the fetcher-prompt contract tests (Task 1).
