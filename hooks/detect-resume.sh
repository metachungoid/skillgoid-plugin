#!/usr/bin/env bash
# SessionStart hook: if CWD contains .skillgoid/, emit a one-paragraph resume summary.
# Robust: no string interpolation into Python, graceful PyYAML fallback.
set -euo pipefail

cwd="${CLAUDE_PROJECT_DIR:-$PWD}"
sg="$cwd/.skillgoid"

if [ ! -d "$sg" ]; then
  exit 0
fi

python3 - "$sg" "$cwd" <<'PY'
import json
import os
import sys
from pathlib import Path

sg = Path(sys.argv[1])
cwd = sys.argv[2]

try:
    summary_parts = [f"Resuming Skillgoid project at {cwd}."]

    chunks_file = sg / "chunks.yaml"
    if chunks_file.exists():
        chunk_count = None
        try:
            import yaml  # optional
            data = yaml.safe_load(chunks_file.read_text()) or {}
            chunks = data.get("chunks", [])
            chunk_count = len(chunks) if isinstance(chunks, list) else None
        except ImportError:
            # Fallback: count lines matching "- id:" at any indent
            import re
            text = chunks_file.read_text()
            chunk_count = len(re.findall(r"^\s*-\s+id\s*:", text, re.MULTILINE))
        except Exception:
            chunk_count = None
        if chunk_count is not None:
            summary_parts.append(f"chunks.yaml defines {chunk_count} chunk(s).")

    iters_dir = sg / "iterations"
    if iters_dir.is_dir():
        iter_files = sorted(iters_dir.glob("*.json"))
        if iter_files:
            latest = iter_files[-1]
            try:
                rec = json.loads(latest.read_text())
                chunk_id = rec.get("chunk_id", "?")
                exit_reason = rec.get("exit_reason", "in_progress")
                report = rec.get("gate_report", {})
                gates_passed = report.get("passed", "?")
                summary_parts.append(
                    f"Latest iteration: chunk={chunk_id}, exit={exit_reason}, gates_passed={gates_passed}."
                )
            except Exception:
                pass  # skip latest-iteration summary on any parse error

    summary = " ".join(summary_parts)
    summary += " Use `/skillgoid:build resume` to continue, or `/skillgoid:build status` to inspect."

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": summary,
        }
    }))
except Exception:
    # Any unexpected error: no-op (don't crash the session)
    pass
PY
