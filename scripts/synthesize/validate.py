#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 3: oracle validation.

For each draft gate, runs the measure_python adapter against:
  - should-pass: the analogue's cache-dir (resolved from draft's first ref)
  - should-fail: a type-driven tmpdir scaffold (scripts/synthesize/_scaffold)
and classifies the pair into {oracle, smoke-only, none} with optional warn.

Output: .skillgoid/synthesis/validated.json

CLI:
    python scripts/synthesize/validate.py --skillgoid-dir .skillgoid
    python scripts/synthesize/validate.py --skillgoid-dir .skillgoid --skip-validation
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.synthesize._common import load_json, save_json, synthesis_path  # noqa: E402


def _skip_payload(drafts: list[dict]) -> dict:
    """Produce a validated.json-shaped payload where every gate is skipped."""
    return {
        "schema_version": 1,
        "gates": [
            {
                "id": d["id"],
                "validated": "none",
                "warn": "validation skipped by --skip-validation",
                "oracle_run": None,
            }
            for d in drafts
        ],
    }


def run_validate(sg: Path, skip: bool = False, stage_timeout_sec: int = 600) -> Path:
    """Run Stage 3 oracle validation. Returns the path to validated.json."""
    drafts_payload = load_json(synthesis_path(sg, "drafts.json"))
    drafts = drafts_payload.get("drafts", [])

    if skip:
        payload = _skip_payload(drafts)
    else:
        raise NotImplementedError("oracle execution lands in Task 4")

    out = synthesis_path(sg, "validated.json")
    save_json(out, payload)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 3: oracle validation")
    parser.add_argument("--skillgoid-dir", type=Path, default=Path(".skillgoid"))
    parser.add_argument("--skip-validation", action="store_true",
                        help="Emit validated: none for every gate without running oracle")
    parser.add_argument("--stage-timeout-sec", type=int, default=600,
                        help="Total wall-clock cap for Stage 3 (default 600)")
    args = parser.parse_args(argv)

    try:
        out_path = run_validate(args.skillgoid_dir, skip=args.skip_validation,
                                stage_timeout_sec=args.stage_timeout_sec)
    except FileNotFoundError as exc:
        sys.stderr.write(f"validate: {exc}\n")
        return 1

    sys.stdout.write(f"wrote: {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
