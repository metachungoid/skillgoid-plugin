#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 1: grounding orchestrator.

Phase 1: only invokes ground_analogue. Phase 2 will add ground_context7
and ground_template; keep the contract here so the skill prose does not
change between phases.

Contract:
    run_ground(sg: Path, analogues: list[Path]) -> Path
        Writes <sg>/synthesis/grounding.json and returns its path.

CLI:
    python scripts/synthesize/ground.py [--skillgoid-dir .skillgoid] <repo> [<repo> ...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow cross-script import
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.synthesize._common import (  # noqa: E402
    ensure_synthesis_dir,
    save_json,
    synthesis_path,
)
from scripts.synthesize.ground_analogue import (  # noqa: E402
    detect_language,
    extract_observations,
)


def run_ground(sg: Path, analogues: list[Path]) -> Path:
    """Run all available grounding sources, write grounding.json, return path."""
    ensure_synthesis_dir(sg)

    observations: list[dict] = []
    language = "unknown"

    for repo in analogues:
        repo_lang = detect_language(repo)
        if language == "unknown" and repo_lang != "unknown":
            language = repo_lang
        for obs in extract_observations(repo):
            observations.append(obs.to_dict())

    payload = {
        "language_detected": language,
        "framework_detected": None,  # Phase 2: populated by ground_context7
        "observations": observations,
    }

    out_path = synthesis_path(sg, "grounding.json")
    save_json(out_path, payload)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 1: grounding orchestrator")
    parser.add_argument(
        "--skillgoid-dir",
        type=Path,
        default=Path(".skillgoid"),
        help="Path to .skillgoid directory (default ./.skillgoid)",
    )
    parser.add_argument(
        "analogues",
        nargs="*",
        type=Path,
        help="Zero or more analogue repo paths",
    )
    args = parser.parse_args(argv)

    if not args.skillgoid_dir.exists() or not args.skillgoid_dir.is_dir():
        sys.stderr.write(f"ground: not a Skillgoid project: {args.skillgoid_dir}\n")
        return 1

    out_path = run_ground(args.skillgoid_dir, args.analogues)
    sys.stdout.write(f"grounding written: {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
