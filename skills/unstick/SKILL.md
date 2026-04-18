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

## Procedure

1. **Validate chunk_id** — must exist in `.skillgoid/chunks.yaml`. If not, error out.
2. **Read recent state** — the latest iteration for this chunk in `.skillgoid/iterations/`.
   - If `exit_reason` ∈ {`success`} — warn: "this chunk already succeeded. Unstick is for stalled chunks." Ask user to confirm before proceeding.
   - If `exit_reason` ∈ {`stalled`, `budget_exhausted`} — proceed.
   - If `exit_reason == "in_progress"` — the loop is still running or was interrupted. Unstick in this case means "restart with hint" — ask user to confirm.
3. **Check unstick budget** — count prior unstick invocations for this chunk by inspecting `iterations/*.json` records where `unstick_hint` field is present. Cap total unsticks per chunk at 3 (prevents runaway).
4. **Dispatch a fresh chunk subagent** — same dispatch pattern as `build` step 3c, with TWO differences:
   - Inject the `<hint>` into the chunk prompt's `## Integration failure context (populated on integration auto-repair, empty otherwise)` slot (repurpose the v0.2 slot — it was designed for exactly this kind of mid-flight hint injection).
   - Prefix the hint with: `"UNSTICK HINT (from human operator): "` so the subagent knows the source.
5. **Reset the attempt counter.** The subagent starts from iteration N+1 but with `attempt=1` for its internal `max_attempts` tracking. (This is semantic — just don't pass a starting `attempt` arg to `loop`.)
6. **Mark the new iteration record** with `unstick_hint: "<hint>"` so future unstick budget counts can find it.
7. **Continue the build loop** from that point — the subagent returns with a fresh `exit_reason`, and `build` resumes the normal per-chunk loop.

## Output

On success:
```
unstick: chunk <chunk_id> re-dispatched with hint.
Subagent returned: <exit_reason>, iterations_used: N, gates: <summary>
```

On over-budget:
```
unstick: chunk <chunk_id> has already been unstuck 3 times. Break out
with /skillgoid:build retrospect-only or continue manually.
```

## Risks

- If the hint is wrong, the chunk spends a fresh budget getting it wrong in a new way. That's the cost.
- If the hint contradicts criteria.yaml, the subagent will likely revert to criteria-driven behavior on subsequent iterations. Consider editing criteria directly instead for structural disagreements.
