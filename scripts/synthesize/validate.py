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
from time import monotonic

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.synthesize._common import load_json, save_json, synthesis_path  # noqa: E402
from scripts.measure_python import run_gates  # noqa: E402
from scripts.synthesize._scaffold import build_scaffold  # noqa: E402


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


def _resolve_analogue_path(draft: dict, analogues_map: dict[str, str]) -> Path | None:
    """Derive the analogue cache-dir for a draft from its first ref.

    Returns None if the draft has no usable ref, the slug is missing from
    the analogues map, or the mapped path doesn't exist on disk.
    """
    prov = draft.get("provenance") or {}
    ref = prov.get("ref")
    if ref is None:
        return None
    first = ref[0] if isinstance(ref, list) else ref
    if not isinstance(first, str) or "/" not in first:
        return None
    slug = first.split("/", 1)[0]
    path_str = analogues_map.get(slug)
    if path_str is None:
        return None
    p = Path(path_str)
    return p if p.exists() else None


def _truncate(text: str, limit: int = 200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _coverage_produced_number(adapter_result: dict) -> bool:
    """True iff the adapter's stdout includes a coverage percentage.

    measure_python._gate_coverage writes `coverage: <pct>%` to stdout on
    any successful run (even one that failed the min_percent threshold).
    The stdout stays empty when pytest-cov isn't installed / errors early.
    """
    stdout = adapter_result["results"][0].get("stdout") or ""
    return "coverage:" in stdout and "%" in stdout


def _classify_coverage(gate_id: str, should_pass: dict, should_fail: dict) -> dict:
    sp_produced = _coverage_produced_number(should_pass)
    sf_produced = _coverage_produced_number(should_fail)

    if sp_produced and not sf_produced:
        return {"id": gate_id, "validated": "oracle", "warn": None,
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": False}}}
    if sp_produced and sf_produced:
        return {"id": gate_id, "validated": "smoke-only",
                "warn": "scaffold also produced coverage; scaffold may be leaking code",
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": True}}}
    return {"id": gate_id, "validated": "none",
            "warn": "coverage tooling not exerciseable on analogue",
            "oracle_run": {"should_pass": {"passed": False}, "should_fail": None}}


def _classify(
    gate_id: str,
    gate_type: str,
    should_pass: dict,
    should_fail: dict,
) -> dict:
    """Map (should_pass, should_fail) adapter results to a validated.json entry."""
    if gate_type == "coverage":
        return _classify_coverage(gate_id, should_pass, should_fail)

    sp_passed = should_pass["results"][0]["passed"]
    sf_passed = should_fail["results"][0]["passed"]

    if sp_passed and not sf_passed:
        return {"id": gate_id, "validated": "oracle", "warn": None,
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": False}}}
    if sp_passed and sf_passed:
        return {"id": gate_id, "validated": "smoke-only",
                "warn": "scaffold also passes; consider tightening",
                "oracle_run": {"should_pass": {"passed": True},
                               "should_fail": {"passed": True}}}
    sp_stderr = should_pass["results"][0].get("stderr", "")
    sp_hint = should_pass["results"][0].get("hint", "")
    excerpt = _truncate(sp_stderr or sp_hint, 200)
    return {"id": gate_id, "validated": "none",
            "warn": f"should-pass failed: {excerpt}" if excerpt else "should-pass failed",
            "oracle_run": {"should_pass": {"passed": False}, "should_fail": None}}


def _oracle_one_gate(draft: dict, analogues_map: dict[str, str]) -> dict:
    """Run oracle for a single draft; return the validated.json entry."""
    gate_id = draft["id"]
    gate_type = draft.get("type")

    analogue_path = _resolve_analogue_path(draft, analogues_map)
    if analogue_path is None:
        return {"id": gate_id, "validated": "none",
                "warn": "no analogue on disk for this gate's ref",
                "oracle_run": None}

    one_gate_criteria = {"gates": [{k: v for k, v in draft.items()
                                    if k not in ("provenance", "rationale")}]}

    try:
        should_pass = run_gates(one_gate_criteria, analogue_path)
    except Exception as exc:  # noqa: BLE001
        return {"id": gate_id, "validated": "none",
                "warn": f"adapter internal error: {_truncate(str(exc))}",
                "oracle_run": None}

    try:
        with build_scaffold(gate_type, draft, analogue_path) as scaffold:
            should_fail = run_gates(one_gate_criteria, scaffold)
    except ValueError as exc:
        return {"id": gate_id, "validated": "none",
                "warn": f"scaffold unavailable: {exc}",
                "oracle_run": None}
    except Exception as exc:  # noqa: BLE001
        return {"id": gate_id, "validated": "none",
                "warn": f"should-fail internal error: {_truncate(str(exc))}",
                "oracle_run": None}

    return _classify(gate_id, gate_type, should_pass, should_fail)


def run_validate(sg: Path, skip: bool = False, stage_timeout_sec: int = 600) -> Path:
    """Run Stage 3 oracle validation. Returns the path to validated.json."""
    drafts_payload = load_json(synthesis_path(sg, "drafts.json"))
    drafts = drafts_payload.get("drafts", [])

    if skip:
        payload = _skip_payload(drafts)
    else:
        grounding = load_json(synthesis_path(sg, "grounding.json"))
        analogues_map = grounding.get("analogues", {})

        entries: list[dict] = []
        start = monotonic()
        for draft in drafts:
            if monotonic() - start >= stage_timeout_sec:
                entries.append({
                    "id": draft["id"], "validated": "none",
                    "warn": "Stage 3 stage-timeout exceeded",
                    "oracle_run": None,
                })
                continue
            entries.append(_oracle_one_gate(draft, analogues_map))

        payload = {"schema_version": 1, "gates": entries}

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
