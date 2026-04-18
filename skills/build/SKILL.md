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

### Detection

1. **Detect state** by inspecting the current working directory:
   - `.skillgoid/` exists? Parse `chunks.yaml` and `iterations/` to determine which chunks have exited successfully (look for the most recent iteration per chunk and its `exit_reason`).
   - No `.skillgoid/`? Fresh start.

### Dispatch — Fresh start (rough_goal required)

2. **Main-session prep (in-process, this skill invokes them directly):**
   - Invoke `skillgoid:retrieve` with `rough_goal`. Capture the returned summary — call it `retrieve_summary`.
   - Invoke `skillgoid:clarify`. Reads/writes `.skillgoid/goal.md` + `.skillgoid/criteria.yaml`.
   - Invoke `skillgoid:plan`. Reads/writes `.skillgoid/blueprint.md` + `.skillgoid/chunks.yaml`.

3. **Per-chunk dispatch loop.** For each chunk in `chunks.yaml` in order:

   3a. Check dependencies (`chunk.depends_on`). If any listed chunk has not yet exited with `success`, skip this chunk for now (dependency ordering is already enforced by `plan`, so this is a safety check).

   3b. Build the subagent prompt with a curated context slice:
      - The chunk entry as YAML (id, description, gate_ids, language, depends_on)
      - `retrieve_summary` verbatim
      - `blueprint.md` in full (v0.2 punts on blueprint slicing — passes whole file)
      - Any existing `.skillgoid/iterations/*.json` records for this chunk (if resuming; up to last 2)

   3c. Dispatch via the `Agent` tool:
      ```
      Agent(
        subagent_type="general-purpose",
        model="sonnet",
        description="Execute Skillgoid chunk <chunk_id>",
        prompt=<curated prompt — see template below>,
      )
      ```

      **Subagent prompt template:**
      ```
      You are executing one chunk of a Skillgoid build loop.

      ## Your task
      Invoke `skillgoid:loop` for chunk_id="<chunk_id>". When it returns,
      report the structured summary back to me. Do NOT invoke retrospect —
      the orchestrator handles that.

      ## Chunk spec (from .skillgoid/chunks.yaml)
      ```yaml
      <chunk entry as YAML>
      ```

      ## Retrieved past lessons
      <retrieve_summary>

      ## Blueprint
      <contents of .skillgoid/blueprint.md>

      ## Prior iterations for this chunk (if any)
      <contents of up to 2 most recent iterations/*.json filtered to chunk_id==this chunk>

      ## Return format
      Return a JSON object on your final message (just JSON, no prose):
      {
        "exit_reason": "success" | "budget_exhausted" | "stalled",
        "iterations_used": <int>,
        "final_gate_report": { ... verbatim gate_report ... },
        "notes": "<1–3 sentences, any notable observations for retrospect>"
      }
      ```

   3d. Parse the subagent's JSON response. Accumulate summary in an in-memory orchestration state dict (you don't need to persist it — `.skillgoid/iterations/` already has the ground truth).

   3e. Gate check:
      - If `exit_reason == "success"`: continue to next chunk.
      - If `exit_reason` is `"budget_exhausted"` or `"stalled"`: STOP. Do NOT dispatch subsequent chunks. Surface the failure and the summary to the user. The user decides whether to retry (run `/skillgoid:build resume`) or break out (`/skillgoid:build retrospect-only`).

4. **When all chunks have succeeded**, proceed to the integration gate phase (added separately in v0.2 Task 8 — for now, if `integration_gates` is empty or not implemented, proceed directly to step 6 retrospect).

### Dispatch — Resume (`subcommand == "resume"` or default when `.skillgoid/` exists)

5. Report current state: "On chunk X of N. Chunk X last exited: <success | stalled | budget_exhausted | in-progress>."

6. Continue the per-chunk dispatch loop (step 3) starting with the first chunk that has NOT yet exited `success`.

### Dispatch — Status only

7. Print chunk summary: which chunks have passed, which are pending, which is current. Include recent iteration `exit_reason` per chunk. Do not modify any files, do not dispatch any subagents.

### Dispatch — Retrospect-only

8. Invoke `skillgoid:retrospect` directly. Used when the user abandons or finalizes early.

### Retrospect phase

9. (Integration phase runs here in v0.2 — added in a later commit.)

10. Invoke `skillgoid:retrospect` once integration (if any) passes or is skipped.

## Output

Stream progress updates after each sub-skill invocation. End with a final summary of what was built and where artifacts live.
