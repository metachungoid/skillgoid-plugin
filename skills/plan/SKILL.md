---
name: plan
description: Use after `clarify` completes (or when the user says "plan the implementation") to turn `.skillgoid/goal.md` + `.skillgoid/criteria.yaml` into a concrete `.skillgoid/blueprint.md` and an ordered `.skillgoid/chunks.yaml`. Each chunk names the gate IDs it must satisfy.
---

# plan

## What this skill does

Produces two files:
1. `.skillgoid/blueprint.md` — architecture, key modules and their responsibilities, interface signatures, data model.
2. `.skillgoid/chunks.yaml` — ordered list of build chunks. Each chunk declares a subset of criteria gates that must pass before the chunk is considered complete. Validated against `schemas/chunks.schema.json`.

## Inputs

- `.skillgoid/goal.md`
- `.skillgoid/criteria.yaml`

## Flags

- `--refresh-context7` — delete `.skillgoid/context7/framework-grounding.md` and `.skillgoid/context7/SKIPPED` (if present) before step 2.5, forcing the fetcher to re-run and regenerate the grounding. Use this when the framework changed, the goal changed in a way that needs fresh docs, or hand-edits to the grounding file should be discarded. This flag lives on `plan` (not `build`) because `build resume` does not re-invoke `plan`.

## Procedure

1. **Verify** both input files exist. If not, stop and tell the caller to run `skillgoid:clarify` first.
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
   - Architecture overview (1–3 paragraphs)
   - **Cross-chunk types section** (v0.8, REQUIRED for multi-chunk type contracts). Immediately after the architecture overview, add a `## Cross-chunk types` section enumerating types that multiple chunks consume, with the canonical module each lives in. Example:

     ```markdown
     ## Cross-chunk types

     Types that multiple chunks consume. All chunks MUST import these from the listed module rather than re-define them locally.

     - `Nil` (sentinel) — defined in `src/mypkg/values.py`.
     - `SExpr` (ADT: Atom, Symbol, Pair, Nil) — defined in `src/mypkg/parser.py`.
     - `Environment` — defined in `src/mypkg/environment.py`.

     Do not re-define these types in any other module.
     ```

     Omitting this section is not a hard error but surfaces as a slicer warning at build time (F6 from v0.8 findings: parser subagent invented its own Nil singleton because the blueprint didn't declare the shared one). The blueprint slicer always includes this section in every subagent's prompt when present.
   - Module layout and responsibilities — use `## <module-name>` headings for each module/chunk so the blueprint slicer (v0.8) can extract per-chunk sections cleanly. Each heading should match (or obviously relate to) a chunk id in `chunks.yaml`. Build-time dispatch passes only the chunk's section + architecture overview + cross-chunk types to each subagent — NOT the whole blueprint.
   - Public interfaces / function signatures for the main entry points
   - Data model (types, storage, or schema) if applicable
   - External dependencies
   - **Context7 grounding (if present).** If `.skillgoid/context7/framework-grounding.md` exists and is non-empty, read it before drafting the blueprint and prefer the idioms it surfaces (project structure, testing patterns, common pitfalls). It is **advisory framework guidance**, not a requirements document — deviate when the goal or criteria demand it. If the file is missing or `.skillgoid/context7/SKIPPED` exists, proceed without it.
4. **Write `chunks.yaml`** decomposing implementation into 3–8 chunks. Each chunk:
   - Has a short `id` (kebab-case)
   - Has a concrete `description` (what code will land in this chunk)
   - Has a `gate_ids` list — the subset of criteria gates that must pass for this chunk to count as done. Early chunks typically need only lint / import-clean. Later chunks add pytest and cli gates.
   - Optional `depends_on` — IDs of chunks that must finish first.
   - Optional `language` override (for polyglot projects).
   - Optional `paths: [<project-relative-paths-or-globs>, ...]`. Declares which project paths this chunk owns. `git_iter_commit.py` uses this to stage only the chunk's own files per iteration — critical for parallel waves where sibling chunks would otherwise cross-contaminate each other's commits via `git add -A`. If two chunks in the same wave would touch overlapping paths, that's a sign they should be sequenced (add `depends_on:`) rather than parallelized.
   - Optional `gate_overrides: {<gate_id>: {args: [...]}}`. Per-chunk gate argument narrowing (v0.8). Propose this when a chunk owns a test file matching `tests/test_<chunk_id>.py` or a source subdirectory predictable from the chunk's `paths:`. Prevents sibling-in-flight test failures in parallel waves.
     Example: `gate_overrides: {pytest_chunk: {args: ["tests/test_<chunk_id>.py"]}, lint: {args: ["check", <chunk_paths>...]}}`.
5. **Enforce sequencing:** gate_ids must be real IDs from `criteria.yaml`. If a chunk references a nonexistent gate, fix it.
6. **Validate** `chunks.yaml` against `schemas/chunks.schema.json` (same pattern as `clarify` step 7).
7. **Show both files to the user** and ask for sign-off before returning. Adjust ordering, split/merge chunks if requested.

## Principles

- **Small chunks.** A chunk should be 30–90 minutes of work for a focused engineer. If a chunk needs 3+ modules changed, split it.
- **Gate early, gate often.** Don't reserve all gates for the last chunk. The whole point of the loop is to fail fast.
- **Dependency-order the list.** `chunks[0]` has no dependencies; each later chunk can reference earlier ones in `depends_on`.
- **Heading discipline.** Blueprint module headings (`##`) should map 1:1 to chunks in `chunks.yaml`. This keeps each chunk's subagent focused on the right section of the blueprint.
- **Declare `paths:` for every chunk.** It costs one line per chunk in `chunks.yaml` and prevents the parallel-wave commit-scope failure mode. A chunk that genuinely touches the whole repo (rare — usually only a `scaffold` chunk) can omit `paths:` and accept `git add -A` fallback; for anything smaller, declare the paths.
- **Avoid same-file chunks in the same wave.** Two chunks that modify overlapping `paths:` cannot safely commit in parallel — one's changes get committed under the other's chunk message. `chunk_topo` auto-serializes these (v0.8), but a clean blueprint avoids the overlap in the first place. Either split the work into disjoint files, or add explicit `depends_on` to serialize by dependency.

## Output

```
plan complete:
- blueprint.md (N modules)
- chunks.yaml (M chunks, first: <chunk_id>)
```
