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
   - Invoke `skillgoid:feasibility`. Parse the returned JSON report. If `all_ok == false`, surface the markdown summary to the user. Ask: "Proceed anyway / fix criteria / abort?" — pause until user chooses.
     - On **"proceed anyway"** → continue to `plan`.
     - On **"fix criteria"** → let the user edit `.skillgoid/criteria.yaml`, then **re-invoke `skillgoid:feasibility`**. Loop this branch until `all_ok == true` OR the user elects "proceed anyway" OR "abort".
     - On **"abort"** → stop; do not invoke `plan`.
     If feasibility errors or the skill is missing, proceed to plan with a warning.
   - Invoke `skillgoid:plan`. Reads/writes `.skillgoid/blueprint.md` + `.skillgoid/chunks.yaml`.

3. **Wave-based dispatch loop.** First, compute execution waves:

   ```bash
   python <plugin-root>/scripts/chunk_topo.py --chunks-file .skillgoid/chunks.yaml
   ```

   The output is a JSON object `{"waves": [["a"], ["b", "c"], ["d"]]}` where each wave is a set of chunks that can dispatch concurrently (all dependencies satisfied). For purely sequential projects, every wave has one chunk — identical to v0.4 behavior.

   For each wave in order:

   3a. For each chunk in the wave:
      - **Resume-skip:** if the chunk's latest iteration record in `.skillgoid/iterations/` already has `exit_reason: "success"`, skip it entirely — do not dispatch a new subagent. This preserves v0.4-style resume behavior when some wave siblings already succeeded in a prior run.
      - **Dependency check:** every listed `chunk.depends_on` must have exited successfully in a prior wave.
      - Dispatch (via concurrent `Agent()` calls) only the chunks in the wave that pass both checks.

   3b. Build the subagent prompt with the curated context slice:
      - The chunk entry as YAML (id, description, gate_ids, language, depends_on, paths, gate_overrides). The `paths:` field is consumed by `git_iter_commit.py` at commit time. `gate_overrides` (v0.8) is consumed by the subagent when building its criteria subset per `skills/loop/SKILL.md` step 3.1. Pass both through verbatim.
      - `retrieve_summary` verbatim
      - **Sliced blueprint for the chunk** (v0.8, replacing v0.2's punt on slicing). Invoke the slicer:
        ```
        python <plugin-root>/scripts/blueprint_slice.py \
          --blueprint .skillgoid/blueprint.md \
          --chunk-id <chunk_id>
        ```
        Use the output as the "Blueprint (relevant)" section of the subagent prompt. Subagents receive their chunk's section + `## Architecture overview` + `## Cross-chunk types` (when present) — NOT the full blueprint. Prevents the ahead-of-scope implementation pattern observed in the minischeme stress run (F7). If the slicer exits 2 (no `## <chunk_id>` section), surface the error and do NOT dispatch — this is a blueprint authoring error the plan step should have caught.
      - Any existing `.skillgoid/iterations/*.json` records for this chunk (if resuming; up to last 2)
      - Optional `integration_failure_context` slot for integration auto-repair or `/skillgoid:unstick` hints

      Use the subagent prompt template (same as v0.2/v0.3/v0.4 — see step 3c's Agent call for the full prompt body).

   3c. Dispatch each chunk's subagent concurrently:
      ```
      Agent(
        subagent_type="general-purpose",
        model=<criteria.models.chunk_subagent or "sonnet">,
        description="Execute Skillgoid chunk <chunk_id>",
        prompt=<curated prompt>,
      )
      ```
      When multiple chunks are in the same wave, these dispatches run in parallel. Claude Code's `Agent` tool supports concurrent subagent invocation — issue all the wave's `Agent()` tool calls in a single message so they execute in parallel.

   3d. **Wait for every subagent in the wave to return** before evaluating results. This guarantees within-wave isolation.

   3e. Parse each subagent's JSON response and accumulate into orchestration state.

   3e-verify. **Verify each dispatched chunk wrote its iteration file.** For every chunk dispatched in this wave (excluding resume-skipped chunks from step 3a), immediately invoke:

      ```bash
      python <plugin-root>/scripts/verify_iteration_written.py \
        --chunk-id <chunk_id> \
        --skillgoid-dir .skillgoid
      ```

      If any invocation exits non-zero, halt the wave **before** the gate check (3f). Surface to the user:
      - Each chunk that failed to produce a valid iteration file
      - The reason from the script's JSON output (`reason` field)
      - The corresponding subagent's final response text (for manual reconstruction)

      Do not proceed to step 3f, subsequent waves, or integration until the iteration file(s) are written or the user intervenes. This is a distinct failure surface from the stall/budget recovery menu in 3f — a missing iteration file means the subagent never declared an `exit_reason` at all.

   3f. **Wave gate check**, evaluated after ALL subagents in the wave report:
      - If every chunk in the wave exited `success`: proceed to the next wave.
      - If any chunk exited `budget_exhausted` or `stalled`: STOP. Do NOT dispatch subsequent waves. Surface ALL failures (possibly multiple siblings) to the user with the three-option recovery menu:

        ```
        Chunk(s) <chunk_ids> exited with <exit_reasons> after <N> iterations.
        Latest failure signatures: <sigs> — <one-line summaries>
        Options:
          • /skillgoid:build resume                 retry with same budget (useful only if env changed)
          • /skillgoid:unstick <chunk_id> "<hint>"  re-dispatch with a human one-sentence hint (capped at 3 invocations per chunk)
          • /skillgoid:build retrospect-only        finalize this project as-is
        ```

   After all waves complete successfully, proceed to step 4 (integration phase).

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

      - **Identify suspect chunk.** Invoke:

        ```bash
        python <plugin-root>/scripts/integration_suspect.py \
          --gate-report .skillgoid/integration/<attempt>.json \
          --chunks     .skillgoid/chunks.yaml
        ```

        Parse `suspect_chunk_id` from the stdout JSON. If non-null, proceed to re-dispatch that chunk's loop subagent with the `integration_failure_context` slot populated. If null (no deterministic path match), ask the user which chunk to retry — the script's `evidence` field explains what it searched.
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

### Retrospect phase (auto-invoked on every terminal state since v0.12)

9. **Auto-retrospect trigger.** After every terminal state reached inside the `build "<goal>"` or `build resume` invocation modes — that is, after step 3f stops the wave on a `stalled` / `budget_exhausted` failure, after step 4h exits with integration still failing, OR after step 4f succeeds with integration passing — invoke `skillgoid:retrospect` exactly once before surfacing the final summary to the user.

   **Skip conditions (do NOT auto-invoke retrospect):**
   - Invocation mode is `build retrospect-only` (step 8 already invokes retrospect — avoids double-call).
   - Invocation mode is `build status` (read-only subcommand, no loop ran, no terminal state).
   - `.skillgoid/iterations/` is absent or empty (clarify/plan/feasibility phase aborted before any loop dispatch — nothing to retrospect on).

   **Slug passed to `metrics_append.py`:** use `$(basename "$(pwd)")` (same convention as `/skillgoid:status`). This ensures a metrics line is written for every terminal run, not only the success path. `metrics.jsonl` is append-only — a subsequent `build resume` after an unstick will append a fresh line with the updated outcome; dedup-by-slug display is a v0.13+ concern.

   **Outcome classification is unchanged:** `retrospect` delegates to `scripts/metrics_append.py`, which already returns `success` / `partial` / `abandoned` based on the iteration set (locked in by `tests/test_v10_bundle.py::test_h9_retrospect_only_partial_outcome` and v0.12's `tests/test_auto_retrospect_trigger.py`).

10. Surface the final summary to the user (same content as before: what was built, where artifacts live, and for failure paths, the three-option recovery menu from step 3f or step 4h).

## Output

Stream progress updates after each sub-skill invocation. End with a final summary of what was built and where artifacts live.
