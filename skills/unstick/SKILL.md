---
name: unstick
description: Use when a chunk has stalled or exhausted its budget and the user has a one-sentence hint that would unblock the agent. Invoked as `/skillgoid:unstick <chunk_id> "<hint>"`. Re-dispatches the chunk's subagent with the hint injected into the chunk prompt's integration-failure-context slot, resetting the attempt counter.
---

# unstick

## What this skill does

Given a stuck chunk and a one-sentence human hint, re-dispatches the chunk's subagent with the hint as extra context. Lets a user rescue a stalled loop with minimal intervention — one sentence, not a full manual takeover.

## When to use

- A chunk has exited with `stalled` or `budget_exhausted`.
- The user has a specific correction that would likely unblock the loop (e.g., "the API key env var is `MYAPP_KEY`, not `API_KEY`"; "use `pytest-asyncio` for the async tests"; "the sqlite database path should be relative to cwd, not absolute").

**NOT** for:
- Complex multi-step corrections (use manual intervention + `build resume`).
- Chunks that haven't stalled (use `build resume` instead).

## Inputs

- `chunk_id` — must match an entry in `.skillgoid/chunks.yaml`.
- `hint` — a single sentence. Shorter is better.
- `--dry-run` (optional flag) — preview the constructed subagent prompt without dispatching. Attempt counter is not reset, no iteration record is written, and unstick budget is not consumed. Useful for validating the hint before spending it.

**Invocation forms:**
- Normal: `/skillgoid:unstick <chunk_id> "<hint>"`
- Dry-run: `/skillgoid:unstick <chunk_id> --dry-run "<hint>"`

## Procedure

1. **Validate chunk_id** — must exist in `.skillgoid/chunks.yaml`. If not, error out.
2. **Read recent state** — the latest iteration for this chunk in `.skillgoid/iterations/`. Since v0.7, iteration files are named `<chunk_id>-NNN.json`, so finding a chunk's latest iteration is `sorted(iters_dir.glob(f"{chunk_id}-*.json"))[-1]`. Pre-v0.7 projects may have unprefixed `NNN.json` files; if you don't find a `<chunk_id>-*.json` match, fall back to scanning all `*.json` files and filter by the `chunk_id` field in the record body.
   - If `exit_reason` ∈ {`success`} — warn: "this chunk already succeeded. Unstick is for stalled chunks." Ask user to confirm before proceeding.
   - If `exit_reason` ∈ {`stalled`, `budget_exhausted`} — proceed.
   - If `exit_reason == "in_progress"` — the loop is still running or was interrupted. Unstick in this case means "restart with hint" — ask user to confirm.
3. **Check unstick budget** — count prior unstick invocations for this chunk by inspecting `iterations/*.json` records where `unstick_hint` field is present. Cap total unsticks per chunk at 3 (prevents runaway).
4. **Construct the chunk subagent prompt** — same dispatch-prep pattern as `build` step 3c, with TWO differences:
   - Inject the `<hint>` into the chunk prompt's `## Integration failure context (populated on integration auto-repair, empty otherwise)` slot (repurpose the v0.2 slot — it was designed for exactly this kind of mid-flight hint injection).
   - Prefix the hint with: `"UNSTICK HINT (from human operator): "` so the subagent knows the source.

   **If `--dry-run` was passed:** do NOT dispatch the subagent. Instead, print the full constructed prompt to stdout wrapped in a banner:

   ```
   --- begin dispatched prompt ---
   <full prompt including UNSTICK HINT (from human operator): <hint>>
   --- end dispatched prompt ---
   ```

   Return immediately after printing. Do NOT reset the attempt counter (step 5 is skipped), do NOT write an iteration record (step 6 is skipped), do NOT count against the unstick budget from step 3 — a dry-run is a read-only preview.

   **Otherwise (no `--dry-run`):** dispatch the subagent with the constructed prompt and proceed to step 5.
5. **Reset the attempt counter.** The subagent starts from iteration N+1 but with `attempt=1` for its internal `max_attempts` tracking. (This is semantic — just don't pass a starting `attempt` arg to `loop`.)
6. **Mark the new iteration record** with `unstick_hint: "<hint>"` so future unstick budget counts can find it.
7. **Continue the build loop** from that point — the subagent returns with a fresh `exit_reason`, and `build` resumes the normal per-chunk loop.

## Output

On success (normal dispatch):
```
unstick: chunk <chunk_id> re-dispatched with hint.
Subagent returned: <exit_reason>, iterations_used: N, gates: <summary>
```

On `--dry-run`:
```
--- begin dispatched prompt ---
<full constructed chunk subagent prompt, including the UNSTICK HINT prefix>
--- end dispatched prompt ---
unstick: dry-run complete. No dispatch, no iteration record, no budget consumed.
```

On over-budget:
```
unstick: chunk <chunk_id> has already been unstuck 3 times. Break out
with /skillgoid:build retrospect-only or continue manually.
```

## Risks

- If the hint is wrong, the chunk spends a fresh budget getting it wrong in a new way. That's the cost.
- If the hint contradicts criteria.yaml, the subagent will likely revert to criteria-driven behavior on subsequent iterations. Consider editing criteria directly instead for structural disagreements.
