# skillgoid v0.12: Context7 Advisory Grounding for plan + build

**Status:** Draft
**Version target:** 0.12.0
**Audience:** Engineer implementing the feature

## Problem

`plan` and `build` subagents work from `goal.md`, `criteria.yaml`, and prior
iteration state. They have no systematic access to current docs for the
framework being used. As a result, generated blueprints and code can drift
from idiomatic patterns (Flask app factory, FastAPI dependency injection,
Express middleware ordering, Cobra subcommand composition) — even when those
patterns are well-documented and the subagent could apply them if reminded.

## Goal

Give the `plan` and `build` subagents a concise, framework-specific
**advisory** grounding file derived from the `context7` MCP server, so they
prefer current idioms when drafting blueprints and writing code. Grounding
is injected into prompts only; it does not gate or block any step.

## Non-goals

- No blocking reviews. Context7 output is advisory; subagents may
  deliberately deviate.
- No post-plan or per-iteration review step.
- No fixture repos.
- No changes to `synthesize-gates` — context7 grounding for criteria
  synthesis is a separate roadmap item (future v0.13+).
- No cross-project framework-level cache — each project's
  `.skillgoid/context7/` is self-contained.
- No automatic refresh mid-build. User drives refresh via flag.

## Architecture

### Single fetch at plan time, reused through build

1. The `plan` skill introduces a new step (before the "write `blueprint.md`"
   step): dispatch a **one-shot context7 fetcher subagent** whose job is to
   (a) infer the primary framework from `goal.md` + `pyproject.toml` /
   `package.json` / `go.mod` / `Cargo.toml`, and (b) query the `context7`
   MCP for that framework's idioms relevant to the goal.
2. The fetcher writes its output to
   **`.skillgoid/context7/framework-grounding.md`** — a Markdown summary
   ≤2000 tokens covering: project structure, testing patterns, and common
   pitfalls.
3. The `plan` skill is run **by the controlling Claude in the user's
   session** (no planner subagent is dispatched — the skill is prose
   instructions for the controller itself). Plan's next step gains a
   sentence: "If `.skillgoid/context7/framework-grounding.md` exists, read
   it and prefer its idioms when drafting `blueprint.md` and `chunks.yaml`."
4. `build` attaches this file to every per-chunk subagent dispatch (via
   the inline prompt text the orchestrator passes to `Agent(...)` in
   `skills/build/SKILL.md` step 3c).
5. The builder subagents treat the attachment as **advisory** via explicit
   prompt wording: "prefer these idioms when they apply; don't fight the
   framework."

### Graceful skip

If the fetcher cannot produce a usable result — MCP missing, query failed,
framework inference inconclusive — it writes `.skillgoid/context7/SKIPPED`
(a short plain-text file naming the reason) instead of
`framework-grounding.md`. Plan and build check for the presence of
`framework-grounding.md`:

- File exists and non-empty → attach it.
- File missing (or `SKIPPED` exists) → attach nothing; proceed normally.

Fetcher failure is a warning, not an error. The build pipeline is unaffected.

### Cache + refresh

- The fetcher runs **only when `.skillgoid/context7/framework-grounding.md`
  does not already exist** (the common case for a fresh project). Re-running
  `plan` reuses the existing file.
- `plan` accepts a new flag **`--refresh-context7`** that deletes both the
  grounding file and the `SKIPPED` sentinel (if present) before dispatching
  the fetcher, forcing a re-fetch. The flag lives on `plan` rather than
  `build` because `build resume` does not re-invoke `plan`, so a flag on
  `build` would not consistently trigger the fetcher.
- A user who edits `framework-grounding.md` by hand overrides the fetcher:
  edits are preserved because the fetcher only writes if the file is
  missing. `plan --refresh-context7` discards hand edits.
- **Mid-build refresh:** users run `plan --refresh-context7` in the same
  project; the grounding file regenerates. Any in-flight `build resume` run
  afterward will attach the refreshed file on its next chunk dispatch.

### Framework detection lives in the fetcher

Rather than add framework detection to Python code, the fetcher prompt asks
the subagent to infer the framework from on-disk signals (manifests, goal
text). This keeps detection judgment-based and extensible — new frameworks
don't need a code change.

## Files changed

### Skill prose

- `skills/plan/SKILL.md`
  - Add a new procedure step between current step 2 ("Read the goal,
    criteria, and any past-lesson summary") and current step 3 ("Write
    `blueprint.md`"): **Step 2.5 — context7 grounding**. Procedure:
    1. If `.skillgoid/context7/framework-grounding.md` exists → skip.
    2. If `.skillgoid/context7/SKIPPED` exists → skip.
    3. Otherwise the controller dispatches the context7 fetcher subagent
       (prompt body: `skills/plan/prompts/context7-fetcher.md`).
    4. Capture fetcher stdout. If it starts with `SKIPPED:`, write the line
       (minus the `SKIPPED:` prefix) to
       `.skillgoid/context7/SKIPPED`. Otherwise write the full stdout to
       `.skillgoid/context7/framework-grounding.md`.
  - Modify step 3 ("Write `blueprint.md`"): add a bullet at the end: "If
    `.skillgoid/context7/framework-grounding.md` exists, read it and prefer
    the idioms it surfaces when drafting the blueprint — it is advisory
    framework guidance, not a requirements document."
  - Add `--refresh-context7` to the skill's flag/argument parsing section
    (currently `plan` takes no arguments — introduce the convention).
    Semantics: delete `.skillgoid/context7/framework-grounding.md` and
    `.skillgoid/context7/SKIPPED` (if present) before step 2.5.
- `skills/build/SKILL.md`
  - Modify the per-chunk `loop` dispatch: if
    `.skillgoid/context7/framework-grounding.md` exists, attach it to each
    chunk's subagent prompt. No flag changes here — refresh lives on
    `plan`.

### Prompts

- `skills/plan/prompts/context7-fetcher.md` — **new file.** (`skills/plan/`
  currently has no `prompts/` subdirectory; this creates it, following the
  precedent in `skills/synthesize-gates/prompts/`.) Instructs the fetcher
  subagent to:
  1. Read `.skillgoid/goal.md` and top-level manifest files (whichever
     exist: `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`).
  2. Infer the primary framework (Flask, FastAPI, Express, Cobra, Django,
     etc.) or report inconclusive.
  3. Query the `context7` MCP for current docs on that framework's
     project structure, testing patterns, and common pitfalls. Target:
     combined output ≤2000 tokens.
  4. Emit Markdown with three sections: `## Project structure`,
     `## Testing patterns`, `## Common pitfalls`. No prose preamble.
  5. On failure (MCP missing, framework unclear, query errors), emit a
     single line starting with `SKIPPED: <reason>` to stdout.
- The **inline per-chunk dispatch prompt** in `skills/build/SKILL.md` step
  3c — add one paragraph: "If the `framework-grounding.md` attachment is
  present, treat it as advisory — prefer its idioms when they apply;
  don't fight the framework. It is not a requirements document." (The
  plan-side equivalent is folded into the bullet added to plan's step 3
  above — no separate planner-subagent prompt to update.)

### Config + metadata

- `CHANGELOG.md` — add a v0.12.0 entry.
- `.claude-plugin/plugin.json` — version bump `0.11.1` → `0.12.0`.

### Tests

The retry and context7 calls both happen inside Agent-tool dispatches from
skill prose, so they are not reachable from pytest. Tests assert the
**prose contract** — the SKILL.md and prompt files contain the right
instructions.

- `tests/test_plan_skill.py` (new or extend existing): assert
  `skills/plan/SKILL.md` contains:
  - `"context7"` (anywhere)
  - `".skillgoid/context7/framework-grounding.md"`
  - `".skillgoid/context7/SKIPPED"`
  - `"context7-fetcher"` or a reference to the fetcher prompt
- `tests/test_build_skill.py` (new or extend): assert
  `skills/build/SKILL.md` contains:
  - `".skillgoid/context7/framework-grounding.md"`
- Also add to `tests/test_plan_skill.py`:
  - `"--refresh-context7"`
- `tests/test_context7_fetcher_prompt.py` (new): assert
  `skills/plan/prompts/context7-fetcher.md` contains:
  - `"goal.md"` (reads the goal)
  - `"pyproject.toml"` (at least one manifest)
  - `"context7"` (the MCP)
  - `"SKIPPED:"` (graceful-skip signal)
  - `"Project structure"` and `"Testing patterns"` and `"Common pitfalls"`
    (output schema)

## Not changing

- `scripts/measure_python.py` and other language adapters.
- `schemas/criteria.schema.json`.
- The `synthesize-gates` skill and its scripts.
- `scripts/chunk_topo.py`, `scripts/stall_check.py`.
- Retrospect / vault plumbing.
- Hooks (`hooks/gate-guard.sh`, `hooks/detect-resume.sh`).

## Release checklist

- All pytest tests pass.
- `ruff check .` clean.
- **Manual verification (required):** on a real project with a known
  framework (e.g., Flask mini-demo), run `/skillgoid:plan` and confirm:
  1. `.skillgoid/context7/framework-grounding.md` is created with non-empty
     content covering the three sections.
  2. If context7 MCP is not installed, `.skillgoid/context7/SKIPPED` is
     created instead and `plan` proceeds normally.
  3. After `plan --refresh-context7`, the grounding file is regenerated.
- CHANGELOG v0.12.0 entry present.
- `.claude-plugin/plugin.json` is `"0.12.0"`.
- Tag `v0.12.0` at release commit; push tag.

## Risks and tradeoffs

- **Context7 MCP interface is not pinned.** The fetcher prompt says "query
  context7" generally rather than prescribing tool names. If the MCP
  changes its tool surface, the fetcher adapts via prompting — no code
  change needed. If it becomes unreachable, `SKIPPED` is written and the
  pipeline continues.
- **Summary quality is judgment-laden.** A bad summary misleads plan /
  build. Mitigation: the output file is a plain Markdown file at a known
  path — users can inspect and edit. Hand edits persist unless
  `--refresh-context7` is passed.
- **Token cost compounds.** A 2k-token grounding attached to every chunk
  dispatch × N chunks × M iterations grows quickly. 10 chunks × 3
  iterations × 2k = 60k extra input tokens per build. Acceptable at current
  scale; revisit if projects routinely exceed 30+ chunks.
- **Advisory subagents may ignore grounding.** Real risk. Retrospect
  already captures misalignment-based iterations; if empirical evidence
  shows high ignore rates, a future spec can add a review gate (option B
  or C from brainstorming).
- **Fetcher subagent needs MCP access at tool-use time.** Subagents run
  with the session's configured MCPs. If `context7` is installed in the
  user's Claude Code session, the subagent can reach it. If not, the
  subagent reports `SKIPPED: context7 MCP not available` and the pipeline
  degrades gracefully.

## Open questions

None. All design questions resolved during brainstorming:

- Placement: advisory grounding (A) — not post-plan review, not
  per-iteration review.
- Fetch timing: once at plan time, re-used through build.
- Refresh mechanism: `--refresh-context7` flag on `plan` (not `build`,
  because `build resume` does not re-invoke `plan`).
- Framework detection: subagent-inferred from goal + manifests.
- Failure handling: `SKIPPED` sentinel, graceful continuation.
- Test strategy: prose-contract (grep-style) + manual verification.
