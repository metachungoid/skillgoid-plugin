---
name: explain
description: Use when the user wants a compact post-mortem of a chunk — iteration-by-iteration timeline, stall signature, and verbatim reflections. Invokable as `/skillgoid:explain <chunk_id>`. Read-only; never modifies `.skillgoid/`.
---

# explain

## What this skill does

Reads every `.skillgoid/iterations/<chunk_id>-*.json` record for the named chunk and produces a compact markdown timeline + stall signal + verbatim reflection section. Use it to understand *why* a chunk behaved the way it did without manually opening each iteration JSON.

## When to use

- A chunk has stalled or succeeded after multiple iterations, and the user wants to see what changed (or didn't) across attempts.
- Before invoking `/skillgoid:unstick <chunk_id> "<hint>"`, to pick an informed hint.
- After a run, as part of a manual post-mortem before the automatic retrospective is written.

**NOT** for:
- In-flight wave overview across all chunks (use `/skillgoid:status` instead).
- Cross-project metrics (use `/skillgoid:stats` instead).
- Writing reflections or modifying iteration records (read-only).

## Inputs

- `chunk_id` (required) — must match a chunk in `.skillgoid/chunks.yaml`. The script glob-matches `.skillgoid/iterations/<chunk_id>-*.json`.
- Optional `skillgoid_dir` path override — defaults to `./.skillgoid`.

## Procedure

1. Invoke:
   ```bash
   python <plugin-root>/scripts/explain_chunk.py --chunk-id <chunk_id> [--skillgoid-dir .skillgoid]
   ```
2. The script emits a markdown report on stdout. Pass it through to the user unchanged. Do not re-interpret or re-synthesize.
3. If the script exits 1 with `"no iteration files for chunk <id>"`, either the chunk id is misspelled or the chunk has not run yet — surface the error to the user with the list of chunk ids from `.skillgoid/chunks.yaml` so they can pick a valid one.

## Output format

```markdown
# Chunk `<id>` — N iterations

## Timeline
| iter | gate state | files touched | first stderr / hint | exit_reason | sig |
| 1 | pytest_unit FAIL | src/parser.py | AssertionError in test_parse_iso | in_progress | a1b2c3d4 |
| 2 | pytest_unit FAIL | src/parser.py | AssertionError in test_parse_iso (same) | in_progress | a1b2c3d4 |
| 3 | pytest_unit FAIL | src/parser.py | AssertionError in test_parse_iso (same) | stalled | a1b2c3d4 |

## Stall signal
Signature `a1b2c3d4` repeated 3 times — loop detected no-progress at iteration 3.

## Reflections
### Iteration 1
<reflection text>
### Iteration 2
<reflection text>
### Iteration 3
<reflection text>
```

## What this skill does NOT do

- Synthesize new narrative — every line in the output is extracted deterministically from iteration JSON.
- Write to `.skillgoid/` or invoke any subagent.
- Cross-reference against blueprint.md or goal.md.
- Render HTML or fetch remote data.
