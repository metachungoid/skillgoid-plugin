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
   - Invoke `skillgoid:feasibility`. Parse the returned JSON report. If `all_ok == false`, surface the markdown summary to the user. Ask: "Proceed anyway / fix criteria / abort?" — pause until user chooses. Only proceed to `plan` on "proceed" or "fix criteria" (after user edits). If feasibility errors or the skill is missing, proceed to plan with a warning.
   - Invoke `skillgoid:plan`. Reads/writes `.skillgoid/blueprint.md` + `.skillgoid/chunks.yaml`.

3. **Per-chunk dispatch loop.** For each chunk in `chunks.yaml` in order:

   3a. Check dependencies (`chunk.depends_on`). If any listed chunk has not yet exited with `success`, skip this chunk for now (dependency ordering is already enforced by `plan`, so this is a safety check).

   3b. Build the subagent prompt with a curated context slice:
      - The chunk entry as YAML (id, description, gate_ids, language, depends_on)
      - `retrieve_summary` verbatim
      - `blueprint.md` in full (v0.2 punts on blueprint slicing — passes whole file)
      - Any existing `.skillgoid/iterations/*.json` records for this chunk (if resuming; up to last 2)

   3c. Before dispatching, read `models.chunk_subagent` from `criteria.yaml` (default `"sonnet"`) and use it as the `model=` arg. Valid values: `"haiku"`, `"sonnet"`, `"opus"`. If the field is absent or any other value, fall back to `"sonnet"` and log a stderr warning.

      Dispatch via the `Agent` tool:
      ```
      Agent(
        subagent_type="general-purpose",
        model=<criteria.models.chunk_subagent or "sonnet">,
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

      ## Integration failure context (populated on integration auto-repair, empty otherwise)
      <empty on first dispatch; populated by the orchestrator when re-dispatching
      this chunk to fix an integration-gate failure — contains which integration
      gate failed, its hint, and the first 200 chars of stderr>

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
      - If `exit_reason` is `"budget_exhausted"` or `"stalled"`: STOP. Do NOT dispatch subsequent chunks. Surface the failure and a three-option recovery menu to the user:

        ```
        Chunk <chunk_id> exited with <exit_reason> after <N> iterations.
        Latest failure signature: <sig> — <one-line summary>
        Options:
          • /skillgoid:build resume                 retry with same budget (useful only if env changed)
          • /skillgoid:unstick <chunk_id> "<hint>"  re-dispatch with a human one-sentence hint
          • /skillgoid:build retrospect-only        finalize this project as-is
        ```

4. **When all chunks have succeeded**, run the integration phase:

   4a. Read `.skillgoid/criteria.yaml`. If `integration_gates` is absent or empty, skip to step 9 (retrospect).

   4b. Create `.skillgoid/integration/` if absent.

   4c. Determine `integration_retries` (default 2). Track `attempt = 1`.

   4d. Before dispatching, read `models.integration_subagent` from `criteria.yaml` (default `"haiku"`). Integration is pure measurement — haiku is the cost-efficient default but users may override via the `models` block.

      **Dispatch integration subagent** via the Agent tool:
      ```
      Agent(
        subagent_type="general-purpose",
        model=<criteria.models.integration_subagent or "haiku">,
        description="Run Skillgoid integration gates (attempt <attempt>)",
        prompt=<integration prompt — see template below>,
      )
      ```

      **Integration subagent prompt template:**
      ```
      You are running Skillgoid's integration gates — the end-to-end checks
      that verify the project works as a whole after all chunks have passed
      their individual gates.

      ## Your task
      1. Read `.skillgoid/criteria.yaml` and extract `integration_gates`.
      2. Write a temporary criteria subset to a temp file or stdin, with the
         integration_gates list AS its `gates:` key:
              gates:
                - <each integration_gates entry>
      3. Invoke `skillgoid:python-gates` (or the appropriate language-gates
         skill) against that temp criteria. python-gates always reads `gates[]`
         — it does not distinguish integration vs. per-chunk; the semantic
         difference lives in the orchestrator.
      4. Return the structured JSON report verbatim.

      ## Return format
      Return a JSON object on your final message:
      {
        "passed": bool,
        "results": [ ... same shape as any gate_report.results ... ]
      }
      ```

   4e. Write `.skillgoid/integration/<attempt>.json` with the returned report:
      ```json
      {
        "iteration": <attempt>,
        "chunk_id": "__integration__",
        "gate_report": { ... returned verbatim ... },
        "started_at": "ISO-8601",
        "ended_at": "ISO-8601"
      }
      ```

   4f. **If `gate_report.passed == true`**: integration succeeded. Proceed to step 9 (retrospect).

   4g. **If `gate_report.passed == false` and `attempt < integration_retries + 1`**: auto-repair path.

      - **Identify suspect chunk(s).** For each failing gate, grep its `stderr` and `stdout` for filenames that appear in the chunks' blueprint/impl paths. Pick the chunk whose file is most recently mentioned. If no filename match, ask the user which chunk to retry.
      - **Re-dispatch the suspect chunk's loop subagent** (exactly as in step 3c) with extra injected context: a new field `integration_failure_context` in the chunk prompt describing the integration-gate failure (which gate failed, hint, stderr prefix). The loop subagent should interpret this as "your chunk's per-chunk gates pass, but the full system fails at X — fix your chunk to address X."
      - After the chunk subagent returns (with a fresh `success` / `stalled` / `budget_exhausted`), increment `attempt` and return to step 4d to re-run the integration subagent.

   4h. **If `gate_report.passed == false` and attempts exhausted**: Surface to the user. Do NOT auto-invoke retrospect. Print:
      ```
      Integration failed after <N> attempts. See .skillgoid/integration/*.json
      for reports. Run /skillgoid:build retrospect-only to finalize this
      project as-is, or debug manually and re-run.
      ```
      Stop.

### Dispatch — Resume (`subcommand == "resume"` or default when `.skillgoid/` exists)

5. Report current state: "On chunk X of N. Chunk X last exited: <success | stalled | budget_exhausted | in-progress>."

6. Continue the per-chunk dispatch loop (step 3) starting with the first chunk that has NOT yet exited `success`.

### Dispatch — Status only

7. Print chunk summary: which chunks have passed, which are pending, which is current. Include recent iteration `exit_reason` per chunk. Do not modify any files, do not dispatch any subagents.

### Dispatch — Retrospect-only

8. Invoke `skillgoid:retrospect` directly. Used when the user abandons or finalizes early.

### Retrospect phase

9. Invoke `skillgoid:retrospect` once integration (if any) passes or is skipped.

## Output

Stream progress updates after each sub-skill invocation. End with a final summary of what was built and where artifacts live.
