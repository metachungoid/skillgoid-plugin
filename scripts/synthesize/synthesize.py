#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 2: parse + validate subagent output.

The skill prose dispatches the synthesis subagent (with grounding.json +
goal.md as context) and pipes the subagent's stdout into this script.
This script parses the JSON, enforces the provenance contract (every
draft must cite a ref that exists in grounding.json), and writes
drafts.json.

NO LLM call is made here. The script is pure parsing + validation.

Contract:
    parse_subagent_output(raw: str, grounding: dict) -> list[dict]
        Returns validated draft dicts. Raises DraftValidationError on failure.

    run_synthesize(sg: Path, raw: str) -> Path
        Loads grounding.json, parses, writes drafts.json. Returns its path.

CLI:
    python scripts/synthesize/synthesize.py --skillgoid-dir .skillgoid
        (reads subagent output from stdin)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.synthesize._common import (  # noqa: E402
    ensure_synthesis_dir,
    load_json,
    save_json,
    synthesis_path,
)

# Mirror schemas/criteria.schema.json gate type enum exactly
SUPPORTED_GATE_TYPES = frozenset({
    "pytest", "ruff", "mypy", "import-clean",
    "cli-command-runs", "run-command", "coverage",
})


class DraftValidationError(ValueError):
    """Raised when subagent output violates the draft contract."""


def _collapse_duplicate_coverage(drafts: list[dict]) -> list[dict]:
    """Merge multiple type: coverage drafts into one (max min_percent wins).

    Provenance refs are unioned into a list. Rationale strings are concatenated
    with ' + '. Non-coverage drafts pass through unchanged.
    """
    coverage_drafts = [d for d in drafts if d.get("type") == "coverage"]
    if len(coverage_drafts) <= 1:
        return drafts

    refs: list[str] = []
    for d in coverage_drafts:
        prov_ref = d.get("provenance", {}).get("ref")
        if isinstance(prov_ref, list):
            refs.extend(prov_ref)
        elif isinstance(prov_ref, str):
            refs.append(prov_ref)
    # Dedupe while preserving first-occurrence order
    seen: set[str] = set()
    deduped_refs: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            deduped_refs.append(r)

    merged = {
        "id": coverage_drafts[0]["id"],
        "type": "coverage",
        "min_percent": max(d.get("min_percent", 0) for d in coverage_drafts),
        "provenance": {
            "source": coverage_drafts[0].get("provenance", {}).get("source", "analogue"),
            "ref": deduped_refs if len(deduped_refs) > 1 else deduped_refs[0],
        },
        "rationale": " + ".join(
            d.get("rationale", "") for d in coverage_drafts if d.get("rationale")
        ),
    }

    sys.stderr.write(
        f"collapsed {len(coverage_drafts)} coverage drafts into one "
        f"(min_percent={merged['min_percent']})\n"
    )

    out: list[dict] = []
    merged_emitted = False
    for d in drafts:
        if d.get("type") == "coverage":
            if not merged_emitted:
                out.append(merged)
                merged_emitted = True
            continue
        out.append(d)
    return out


def parse_subagent_output(raw: str, grounding: dict) -> list[dict]:
    """Parse subagent stdout JSON and validate each draft.

    Validation rules:
      1. Top-level must be a JSON object with key 'drafts' = list.
      2. Each draft must have id, type, provenance.{source, ref}.
      3. type must be in SUPPORTED_GATE_TYPES.
      4. provenance.ref must match an observation ref in grounding['observations'].
      5. ids must be unique across all drafts.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DraftValidationError(f"subagent output is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict) or "drafts" not in payload:
        raise DraftValidationError("subagent output must contain 'drafts' key")

    drafts = payload["drafts"]
    if not isinstance(drafts, list):
        raise DraftValidationError("'drafts' must be a list")

    valid_refs = {o.get("ref") for o in grounding.get("observations", [])}
    seen_ids: set[str] = set()

    for idx, draft in enumerate(drafts):
        if not isinstance(draft, dict):
            raise DraftValidationError(f"draft[{idx}] is not an object")

        gate_id = draft.get("id")
        if not gate_id:
            raise DraftValidationError(f"draft[{idx}] missing 'id'")
        if gate_id in seen_ids:
            raise DraftValidationError(f"duplicate gate id: {gate_id}")
        seen_ids.add(gate_id)

        gate_type = draft.get("type")
        if gate_type not in SUPPORTED_GATE_TYPES:
            raise DraftValidationError(
                f"draft '{gate_id}': unsupported gate type '{gate_type}' "
                f"(allowed: {sorted(SUPPORTED_GATE_TYPES)})"
            )

        provenance = draft.get("provenance")
        if not isinstance(provenance, dict):
            raise DraftValidationError(f"draft '{gate_id}' missing 'provenance' object")
        ref = provenance.get("ref")
        if not ref:
            raise DraftValidationError(f"draft '{gate_id}' provenance missing 'ref'")
        refs_to_check = ref if isinstance(ref, list) else [ref]
        for r in refs_to_check:
            if not isinstance(r, str):
                raise DraftValidationError(
                    f"draft '{gate_id}' provenance.ref entries must be strings (got {r!r})"
                )
            if r not in valid_refs:
                raise DraftValidationError(
                    f"draft '{gate_id}' provenance ref not found in grounding: {r}"
                )

        if gate_type == "coverage":
            args = draft.get("args")
            if args is not None and len(args) > 0:  # empty list is treated as absent
                raise DraftValidationError(
                    f"draft '{gate_id}' (coverage): must not have args; "
                    f"use type: run-command for literal CLI usage"
                )
            min_percent = draft.get("min_percent")
            if min_percent is None:
                raise DraftValidationError(
                    f"draft '{gate_id}' (coverage): must have min_percent (int, 0-100)"
                )
            if (
                isinstance(min_percent, bool)
                or not isinstance(min_percent, int)
                or min_percent < 0
                or min_percent > 100
            ):
                raise DraftValidationError(
                    f"draft '{gate_id}' (coverage): min_percent must be 0-100 "
                    f"(got {min_percent!r})"
                )

    drafts = _collapse_duplicate_coverage(drafts)
    return drafts


def run_synthesize(sg: Path, raw: str) -> Path:
    """Load grounding.json, parse raw subagent output, write drafts.json."""
    ensure_synthesis_dir(sg)
    grounding_path = synthesis_path(sg, "grounding.json")
    grounding = load_json(grounding_path)

    drafts = parse_subagent_output(raw, grounding)

    out_path = synthesis_path(sg, "drafts.json")
    save_json(out_path, {"drafts": drafts})
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 2: synthesis output parser")
    parser.add_argument(
        "--skillgoid-dir",
        type=Path,
        default=Path(".skillgoid"),
        help="Path to .skillgoid directory (default ./.skillgoid)",
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read()
    try:
        out_path = run_synthesize(args.skillgoid_dir, raw)
    except (DraftValidationError, FileNotFoundError) as exc:
        sys.stderr.write(f"synthesize: {type(exc).__name__}: {exc}\n")
        return 1

    sys.stdout.write(f"drafts written: {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
