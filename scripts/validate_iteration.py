#!/usr/bin/env python3
"""Iteration JSON schema validator.

Validates a `.skillgoid/iterations/<chunk_id>-NNN.json` record against
`schemas/iterations.schema.json`. Used as a preflight check and called
internally by `git_iter_commit.py` before staging a commit.

Contract:
    validate_iteration(record: dict, schema_path: Path | None = None) -> list[str]
        Returns list of error messages (empty list = valid).

CLI:
    python scripts/validate_iteration.py <iteration-json-path> [--schema <path>]
    Exit 0 if valid; exit 2 if invalid (errors to stderr).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema


def _default_schema_path() -> Path:
    return Path(__file__).resolve().parent.parent / "schemas" / "iterations.schema.json"


def validate_iteration(record: dict, schema_path: Path | None = None) -> list[str]:
    """Validate an iteration record. Returns sorted list of error messages."""
    if schema_path is None:
        schema_path = _default_schema_path()
    try:
        schema = json.loads(schema_path.read_text())
    except Exception as exc:
        return [f"cannot load schema at {schema_path}: {exc}"]
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(record), key=lambda e: list(e.path))
    return [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in errors
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid iteration JSON validator")
    ap.add_argument("path", type=Path, help="Path to iteration JSON file")
    ap.add_argument("--schema", type=Path, default=None,
                    help="Override schema path (default: schemas/iterations.schema.json)")
    args = ap.parse_args(argv)

    try:
        record = json.loads(args.path.read_text())
    except Exception as exc:
        sys.stderr.write(f"validate_iteration: cannot read {args.path}: {exc}\n")
        return 2

    errors = validate_iteration(record, args.schema)
    if errors:
        sys.stderr.write(f"validate_iteration: {args.path} failed validation:\n")
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
