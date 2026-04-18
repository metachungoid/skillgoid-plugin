---
name: build
description: Top-level Skillgoid orchestrator. Use when the user says "skillgoid build <goal>", "start a new project with skillgoid", or invokes `/skillgoid:build`. Routes to the appropriate sub-skill based on project state — fresh start, mid-loop, or ready-to-retrospect.
---

# build

## What this skill does

Routes a user request through the Skillgoid pipeline:

1. **No `.skillgoid/` directory yet** → `retrieve` → `clarify` → `plan` → for each chunk: `loop` → `retrospect`.
2. **`.skillgoid/` exists, chunks remaining** → resume at the current chunk with `loop`.
3. **`.skillgoid/` exists, all chunks passed** → `retrospect`.

## Inputs

- `rough_goal` (optional, required only on fresh start).
- `subcommand` (optional): `status`, `resume`, `retrospect-only`.

## Procedure

1. **Detect state** by inspecting the current working directory:
   - `.skillgoid/` exists? Check `chunks.yaml` and `iterations/` to determine which chunks have exited successfully.
   - No `.skillgoid/`? Fresh start.
2. **Dispatch:**

   Fresh start (`rough_goal` required):
   - Invoke `skillgoid:retrieve` with `rough_goal`.
   - Invoke `skillgoid:clarify`.
   - Invoke `skillgoid:plan`.
   - For each chunk in `chunks.yaml` in order: invoke `skillgoid:loop` with `chunk_id`. If a chunk exits with `stalled` or `budget_exhausted`, surface to user and stop — do NOT continue to subsequent chunks.
   - When all chunks succeed, invoke `skillgoid:retrospect`.

   Mid-project resume (`subcommand == "resume"` or default when `.skillgoid/` exists):
   - Report current state: "On chunk X of N. Chunk X last exited: <success | stalled | budget_exhausted | in-progress>".
   - Continue loop on the next incomplete chunk.

   Status only (`subcommand == "status"`):
   - Print a summary of chunks (passed, pending, current) and recent iteration outcomes.
   - Do not modify any files.

   Retrospect-only (`subcommand == "retrospect-only"`):
   - Invoke `skillgoid:retrospect` even if not all chunks passed. Used for abandoned projects.

3. **Always** commit any files written in `.skillgoid/` to git if the project is a git repo.

## Output

Stream progress updates after each sub-skill invocation. End with a final summary of what was built and where artifacts live.
