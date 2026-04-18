#!/usr/bin/env bash
# Stop hook: if active Skillgoid session has failing gates and loop budget remains, block the stop.
set -euo pipefail

cwd="${CLAUDE_PROJECT_DIR:-$PWD}"
sg="$cwd/.skillgoid"

if [ ! -d "$sg" ]; then
  exit 0
fi

iters_dir="$sg/iterations"
if [ ! -d "$iters_dir" ]; then
  exit 0
fi

latest=$(ls -1 "$iters_dir"/*.json 2>/dev/null | sort | tail -n1 || true)
if [ -z "$latest" ]; then
  exit 0
fi

python3 - <<PY "$sg" "$latest"
import json, sys, yaml
sg, latest = sys.argv[1], sys.argv[2]
rec = json.load(open(latest))
exit_reason = rec.get("exit_reason", "in_progress")
report = rec.get("gate_report", {})
passed = report.get("passed", True)

if passed or exit_reason in ("success",):
    sys.exit(0)

# Check budget
max_attempts = 5
try:
    crit = yaml.safe_load(open(f"{sg}/criteria.yaml"))
    max_attempts = (crit or {}).get("loop", {}).get("max_attempts", 5)
except Exception:
    pass
iteration = rec.get("iteration", 0)

if iteration >= max_attempts or exit_reason in ("budget_exhausted", "stalled"):
    # Budget already exhausted — allow stop.
    sys.exit(0)

failing_ids = [r.get("gate_id") for r in report.get("results", []) if not r.get("passed")]
reason = (
    f"Skillgoid: gates still failing ({', '.join(failing_ids) or 'unknown'}) and "
    f"loop budget remains ({iteration}/{max_attempts}). Continue iterating with /skillgoid:build resume, "
    f"or break explicitly with /skillgoid:build retrospect-only."
)
print(json.dumps({"decision": "block", "reason": reason}))
PY
