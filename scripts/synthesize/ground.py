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
import os
import re
import shutil
import sys
import tempfile
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


def _cache_dir() -> Path:
    """Return the user-global cache dir for analogue clones.

    Prefers $XDG_CACHE_HOME/skillgoid/analogues, falls back to
    ~/.cache/skillgoid/analogues. If the primary is unwritable, falls back
    to a tempdir-based location ($TMPDIR on POSIX, or Python's
    tempfile.gettempdir() otherwise) and emits a stderr warning.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    target = base / "skillgoid" / "analogues"
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError:
        tmpdir = os.environ.get("TMPDIR") or tempfile.gettempdir()
        fallback = Path(tmpdir) / "skillgoid-analogues"
        fallback.mkdir(parents=True, exist_ok=True)
        sys.stderr.write(
            f"warning: cache dir {target} unwritable, using {fallback}\n"
        )
        return fallback


def _migrate_legacy_analogues(sg: Path) -> None:
    """Move any project-local analogue clones into the user-global cache dir.

    Scans <sg>/synthesis/analogues/<slug>/ and for each child directory:
      - If the cache dir has no entry with that name, rename the project-local
        copy into the cache dir.
      - If both exist, leave both alone and emit an "orphaned" warning.

    Idempotent: safe to call on every ground.py run.
    """
    cache_root = _cache_dir()
    legacy_root = sg / "synthesis" / "analogues"
    if not legacy_root.is_dir():
        return
    for child in sorted(legacy_root.iterdir()):
        if not child.is_dir():
            continue
        target = cache_root / child.name
        if target.exists():
            sys.stderr.write(
                f"warning: analogue cache already exists at {target}; "
                f"project-local copy at {child} is now orphaned, "
                f"please remove manually\n"
            )
            continue
        shutil.move(str(child), str(target))
        sys.stderr.write(f"migrated {child.name} analogue to {target}\n")


_URL_PREFIX_RE = re.compile(r"^(https?://|git@|ssh://|git://|file://)")
_SLUG_TAIL_RE = re.compile(r"([^/:]+)[/:]([^/:]+?)(?:\.git)?/?$")


def _is_url(arg: str) -> bool:
    """Return True if arg looks like a git URL, False if it's a local path."""
    return bool(_URL_PREFIX_RE.match(arg))


def _slug_for_url(url: str) -> str:
    """Derive a stable <owner>-<repo> slug from a git URL.

    For file:// URLs (no owner), returns the last path segment only.
    """
    if url.startswith("file://"):
        path = url[len("file://"):]
        name = Path(path).name
        return name.removesuffix(".git")
    match = _SLUG_TAIL_RE.search(url.rstrip("/"))
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return url.rsplit("/", 1)[-1].removesuffix(".git")


def run_ground(sg: Path, analogues: list) -> Path:
    """Run all available grounding sources, write grounding.json, return path.

    Each element of `analogues` may be a str (URL or path) or a Path. Git
    URLs are shallow-cloned into _cache_dir()/<slug>/; local paths are used
    in-place.
    """
    ensure_synthesis_dir(sg)
    _migrate_legacy_analogues(sg)

    observations: list[dict] = []
    language = "unknown"

    for arg in analogues:
        arg_str = str(arg)
        if _is_url(arg_str):
            slug = _slug_for_url(arg_str)
            target = _cache_dir() / slug
            if not target.exists():
                import subprocess
                sys.stderr.write(f"cloning {arg_str} -> {target}\n")
                result = subprocess.run(
                    ["git", "clone", "--depth=1", arg_str, str(target)],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    sys.stderr.write(f"clone failed for {arg_str}: {result.stderr}\n")
                    continue
            repo = target
        else:
            repo = Path(arg_str)

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
        help="Zero or more analogue repo URLs or local paths",
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
