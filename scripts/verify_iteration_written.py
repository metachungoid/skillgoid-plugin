#!/usr/bin/env python3
"""Post-dispatch iteration-file verification.

Called by the build orchestrator (build/SKILL.md) after each loop subagent
returns. Confirms that .skillgoid/iterations/<chunk-id>-*.json exists, parses
as valid JSON, and satisfies the iteration schema.

CLI:
    python scripts/verify_iteration_written.py --chunk-id <id> --skillgoid-dir <path>
    Exit 0: ok (JSON result on stdout)
    Exit 1: file missing
    Exit 2: file present but invalid JSON or schema failure

Library:
    from scripts.verify_iteration_written import verify
    code, result = verify("parser", Path(".skillgoid"))
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow cross-script import when invoked directly as python scripts/verify_iteration_written.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validate_iteration import validate_iteration  # noqa: E402


def verify(chunk_id: str, skillgoid_dir: str | Path) -> tuple[int, dict]:
    """Return (exit_code, result_dict).

    0 = ok, 1 = file missing, 2 = invalid JSON or schema failure.
    """
    iters_dir = Path(skillgoid_dir) / "iterations"
    glob_pattern = f"{chunk_id}-*.json"

    try:
        files = list(iters_dir.glob(glob_pattern))
    except OSError:
        # Handles permission errors or other OS-level glob failures.
        # A non-existent directory returns [] naturally on Python 3.12+.
        files = []

    if not files:
        return 1, {
            "ok": False,
            "reason": f"no iteration files found for chunk {chunk_id!r}",
            "searched_glob": str(iters_dir / glob_pattern),
        }

    latest = max(files, key=lambda p: p.stat().st_mtime)

    try:
        record = json.loads(latest.read_text())
    except Exception as exc:
        return 2, {
            "ok": False,
            "reason": "file is not valid JSON",
            "file": str(latest),
            "errors": [str(exc)],
        }

    errors = validate_iteration(record)
    if errors:
        return 2, {
            "ok": False,
            "reason": "iteration file failed schema validation",
            "file": str(latest),
            "errors": errors,
        }

    name = latest.stem  # e.g. "parser-002"
    try:
        iteration_number = int(name.rsplit("-", 1)[-1])
    except (ValueError, IndexError):
        iteration_number = None

    result: dict = {
        "ok": True,
        "latest_iteration": str(latest),
        "exit_reason": record.get("exit_reason") or record.get("status"),
    }
    if iteration_number is not None:
        result["iteration_number"] = iteration_number
    return 0, result


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(
        description="Verify loop subagent wrote its iteration file"
    )
    ap.add_argument("--chunk-id", required=True, help="Chunk ID to check")
    ap.add_argument("--skillgoid-dir", required=True, help="Path to .skillgoid dir")
    args = ap.parse_args(argv)

    code, result = verify(args.chunk_id, args.skillgoid_dir)
    sys.stdout.write(json.dumps(result) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
