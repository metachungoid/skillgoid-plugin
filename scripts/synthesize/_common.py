"""Shared helpers for synthesize-gates stage scripts.

All stages read/write under `<.skillgoid>/synthesis/`. Centralize the path
conventions and JSON IO here so each stage script stays focused on its
own logic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SYNTHESIS_SUBDIR = "synthesis"


def synthesis_path(sg: Path, filename: str) -> Path:
    """Return the canonical path for a synthesis artifact under sg/synthesis/."""
    return sg / SYNTHESIS_SUBDIR / filename


def ensure_synthesis_dir(sg: Path) -> Path:
    """Create sg/synthesis/ if missing. Returns the directory path."""
    target = sg / SYNTHESIS_SUBDIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def load_json(path: Path) -> Any:
    """Load JSON from path. Raises FileNotFoundError if missing."""
    return json.loads(path.read_text())


def save_json(path: Path, payload: Any) -> None:
    """Pretty-print payload to path (indent=2, trailing newline).

    Creates parent directories if missing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
