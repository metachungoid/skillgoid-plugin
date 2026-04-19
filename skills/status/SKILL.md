---
name: status
description: Use when the user wants to see the current project's in-flight state — which chunks have passed, which are stuck, which are pending, and whether the last integration attempt failed. Invokable as `/skillgoid:status`. Read-only; never modifies `.skillgoid/`.
---

# status

## What this skill does

Reads `.skillgoid/chunks.yaml`, `.skillgoid/iterations/*.json`, and `.skillgoid/integration/*.json` in the current working directory and produces a markdown snapshot of the project's current state.

## When to use

- The user asks "what's Skillgoid doing right now?" / "which chunk is stuck?" / "did integration pass?".
- Mid-run, when a wave has been working silently for a while and the user wants an overview without reading `iterations/*.json` by hand.
- Before invoking `/skillgoid:unstick` or `/skillgoid:explain <chunk_id>`, to identify the chunk of interest.

**NOT** for:
- Cross-project metrics (use `/skillgoid:stats` instead).
- Modifying state (this skill is strictly read-only).
- Chunk-level post-mortem (use `/skillgoid:explain <chunk_id>` for an iteration timeline).

## Inputs

- None required. Runs against `./.skillgoid/` in the current working directory.
- Optional `skillgoid_dir` path override — defaults to `./.skillgoid`.

## Procedure

1. Invoke:
   ```bash
   python <plugin-root>/scripts/status_reader.py [--skillgoid-dir .skillgoid]
   ```
2. The script emits a markdown report on stdout. Pass it through to the user unchanged. Do not re-interpret or re-synthesize; the script's output is the authoritative view.

## Output format

```markdown
# Skillgoid status — <cwd basename>

**Phase:** N wave(s) planned

## Chunks
| chunk_id | wave | state | iter | latest gate state | files touched |
| scaffold | 1 | success | 1 | ruff pass, pytest pass | src/app.py |
| parser | 2 | stalled | 3 | pytest_unit FAIL | src/parser.py |
...

## Latest integration attempt
- Attempt 1 (2026-04-18T10:01:00Z) — FAILED
  - Gate `integration_check` stderr: `src/parser.py:42: AssertionError...`
```

## What this skill does NOT do

- Write to or modify `.skillgoid/`.
- Dispatch any loop / integration / retrospect subagents.
- Render HTML or fetch remote data.
- Summarize across projects — that is `/skillgoid:stats`.
