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

## Procedure

1. **Verify** both input files exist. If not, stop and tell the caller to run `skillgoid:clarify` first.
2. **Read** the goal, criteria, and any past-lesson summary still in context from `skillgoid:retrieve`.
3. **Write `blueprint.md`** covering:
   - Architecture overview (1–3 paragraphs)
   - Module layout and responsibilities — use `## <module-name>` headings for each module/chunk so future blueprint-slicing tools can extract per-chunk sections cleanly. Each heading should match (or obviously relate to) a chunk id in `chunks.yaml`.
   - Public interfaces / function signatures for the main entry points
   - Data model (types, storage, or schema) if applicable
   - External dependencies
4. **Write `chunks.yaml`** decomposing implementation into 3–8 chunks. Each chunk:
   - Has a short `id` (kebab-case)
   - Has a concrete `description` (what code will land in this chunk)
   - Has a `gate_ids` list — the subset of criteria gates that must pass for this chunk to count as done. Early chunks typically need only lint / import-clean. Later chunks add pytest and cli gates.
   - Optional `depends_on` — IDs of chunks that must finish first.
   - Optional `language` override (for polyglot projects).
   - Optional `paths: [<project-relative-paths-or-globs>, ...]`. Declares which project paths this chunk owns. `git_iter_commit.py` uses this to stage only the chunk's own files per iteration — critical for parallel waves where sibling chunks would otherwise cross-contaminate each other's commits via `git add -A`. If two chunks in the same wave would touch overlapping paths, that's a sign they should be sequenced (add `depends_on:`) rather than parallelized.
5. **Enforce sequencing:** gate_ids must be real IDs from `criteria.yaml`. If a chunk references a nonexistent gate, fix it.
6. **Validate** `chunks.yaml` against `schemas/chunks.schema.json` (same pattern as `clarify` step 7).
7. **Show both files to the user** and ask for sign-off before returning. Adjust ordering, split/merge chunks if requested.

## Principles

- **Small chunks.** A chunk should be 30–90 minutes of work for a focused engineer. If a chunk needs 3+ modules changed, split it.
- **Gate early, gate often.** Don't reserve all gates for the last chunk. The whole point of the loop is to fail fast.
- **Dependency-order the list.** `chunks[0]` has no dependencies; each later chunk can reference earlier ones in `depends_on`.
- **Heading discipline.** Blueprint module headings (`##`) should map 1:1 to chunks in `chunks.yaml`. This keeps each chunk's subagent focused on the right section of the blueprint.
- **Declare `paths:` for every chunk.** It costs one line per chunk in `chunks.yaml` and prevents the parallel-wave commit-scope failure mode. A chunk that genuinely touches the whole repo (rare — usually only a `scaffold` chunk) can omit `paths:` and accept `git add -A` fallback; for anything smaller, declare the paths.

## Output

```
plan complete:
- blueprint.md (N modules)
- chunks.yaml (M chunks, first: <chunk_id>)
```
