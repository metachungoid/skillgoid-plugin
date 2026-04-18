#!/usr/bin/env bash
# SessionStart hook: if CWD contains .skillgoid/, emit a one-paragraph resume summary.
set -euo pipefail

cwd="${CLAUDE_PROJECT_DIR:-$PWD}"
sg="$cwd/.skillgoid"

if [ ! -d "$sg" ]; then
  # Not a Skillgoid project — emit nothing.
  exit 0
fi

chunks_file="$sg/chunks.yaml"
iters_dir="$sg/iterations"

summary="Resuming Skillgoid project at $cwd."
if [ -f "$chunks_file" ]; then
  chunk_count=$(grep -c "^  - id:" "$chunks_file" || echo 0)
  summary="$summary chunks.yaml defines $chunk_count chunk(s)."
fi

if [ -d "$iters_dir" ]; then
  latest=$(ls -1 "$iters_dir"/*.json 2>/dev/null | sort | tail -n1 || true)
  if [ -n "$latest" ]; then
    chunk_id=$(python3 -c "import json; print(json.load(open('$latest')).get('chunk_id', '?'))")
    exit_reason=$(python3 -c "import json; print(json.load(open('$latest')).get('exit_reason', 'in_progress'))")
    gates_passed=$(python3 -c "import json; r=json.load(open('$latest')).get('gate_report',{}); print(r.get('passed','?'))")
    summary="$summary Latest iteration: chunk=$chunk_id, exit=$exit_reason, gates_passed=$gates_passed."
  fi
fi

# Emit context-injection JSON per Claude Code hook protocol.
python3 - <<PY
import json
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": """$summary Use \`/skillgoid:build resume\` to continue, or \`/skillgoid:build status\` to inspect."""
    }
}))
PY
