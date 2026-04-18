#!/usr/bin/env bash
# Stop hook: if active Skillgoid session has failing gates and loop budget remains, block the stop.
# Robust: no string interpolation into Python, graceful PyYAML fallback.
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

python3 - "$sg" "$iters_dir" <<'PY'
import json
import sys
from pathlib import Path

sg = Path(sys.argv[1])
iters_dir = Path(sys.argv[2])

try:
    iter_files = list(iters_dir.glob("*.json"))
    if not iter_files:
        sys.exit(0)

    # Sort by mtime descending — most recently written iteration is the active one.
    latest = max(iter_files, key=lambda p: p.stat().st_mtime)
    try:
        rec = json.loads(latest.read_text())
    except Exception:
        sys.exit(0)  # malformed iteration — don't block

    exit_reason = rec.get("exit_reason", "in_progress")
    report = rec.get("gate_report", {})

    # gate_report may be a flat list (natural subagent output) or a dict {passed, results}.
    if isinstance(report, list):
        results_list = report
        passed = all(r.get("passed", True) for r in results_list)
    else:
        results_list = report.get("results", [])
        passed = report.get("passed", True)

    if passed or exit_reason == "success":
        sys.exit(0)

    # Determine loop budget — try yaml, fall back to default 5
    max_attempts = 5
    criteria_file = sg / "criteria.yaml"
    if criteria_file.exists():
        try:
            import yaml
            crit = yaml.safe_load(criteria_file.read_text()) or {}
            max_attempts = int((crit.get("loop") or {}).get("max_attempts", 5))
        except ImportError:
            # Fallback: regex for `max_attempts: N`
            import re
            text = criteria_file.read_text()
            m = re.search(r"^\s*max_attempts\s*:\s*(\d+)", text, re.MULTILINE)
            if m:
                max_attempts = int(m.group(1))
        except Exception:
            pass

    iteration = rec.get("iteration", 0)

    if iteration >= max_attempts or exit_reason in ("budget_exhausted", "stalled"):
        sys.exit(0)

    failing_results = [r for r in results_list if not r.get("passed")]
    failing_ids = [r.get("gate_id", "?") for r in failing_results]

    # Pick top 2 hints by length (most informative)
    def _truncate(s: str, n: int = 120) -> str:
        return s if len(s) <= n else s[: n - 1] + "…"

    hints_by_length = sorted(
        [(r.get("gate_id", "?"), (r.get("hint") or "")) for r in failing_results],
        key=lambda pair: len(pair[1]),
        reverse=True,
    )
    top_hints = [(gid, h) for gid, h in hints_by_length[:2] if h]

    reason_parts = [
        f"Skillgoid: gates still failing ({', '.join(filter(None, failing_ids)) or 'unknown'}) and "
        f"loop budget remains ({iteration}/{max_attempts})."
    ]
    for gid, hint in top_hints:
        reason_parts.append(f"→ {gid} hint: \"{_truncate(hint)}\"")
    reason_parts.append(
        "Continue iterating with `/skillgoid:build resume`, "
        "or break explicitly with `/skillgoid:build retrospect-only`."
    )
    reason = "\n".join(reason_parts)
    print(json.dumps({"decision": "block", "reason": reason}))
except Exception:
    # Any unexpected error: don't block
    sys.exit(0)
PY
