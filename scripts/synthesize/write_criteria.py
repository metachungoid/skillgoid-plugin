#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 4: render criteria.yaml.proposed.

Reads drafts.json and (optionally) grounding.json; produces criteria.yaml
.proposed with provenance comment headers per gate. Output conforms to
schemas/criteria.schema.json.

Phase 1: every gate is labeled `validated: none (Phase 1: oracle
validation deferred)`. Phase 2 will replace this with real oracle labels.

NEVER overwrites an existing criteria.yaml. Always writes to
.skillgoid/criteria.yaml.proposed.

Contract:
    render_criteria_yaml(drafts: dict, language: str) -> str
    run_write_criteria(sg: Path) -> Path

CLI:
    python scripts/synthesize/write_criteria.py --skillgoid-dir .skillgoid
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.synthesize._common import load_json, synthesis_path  # noqa: E402

# Phase 1 validation label (Phase 2 will switch this per-gate)
PHASE1_VALIDATION_LABEL = "validated: none (Phase 1: oracle validation deferred)"

# Internal-only fields stripped before YAML emission (not in criteria schema)
INTERNAL_FIELDS = frozenset({"provenance", "rationale"})


def _gate_to_schema_dict(draft: dict) -> dict:
    """Strip internal fields from a draft to produce a schema-conformant gate."""
    return {k: v for k, v in draft.items() if k not in INTERNAL_FIELDS}


def _gate_comment_block(draft: dict) -> str:
    """Build the comment lines that precede a gate in the rendered YAML."""
    prov = draft.get("provenance") or {}
    source = prov.get("source", "unknown")
    ref = prov.get("ref", "unknown")
    lines = [
        f"  # source: {source}, ref: {ref}",
        f"  # {PHASE1_VALIDATION_LABEL}",
    ]
    rationale = draft.get("rationale")
    if rationale:
        lines.append(f"  # rationale: {rationale}")
    return "\n".join(lines)


def render_criteria_yaml(drafts_payload: dict, language: str) -> str:
    """Render drafts to a criteria.yaml string with provenance comments.

    The output is valid YAML and conforms to schemas/criteria.schema.json.
    """
    drafts = drafts_payload.get("drafts", [])
    today = dt.date.today().isoformat()

    header_lines = [
        f"# Skillgoid criteria — synthesized {today} from:",
    ]
    sources_seen = sorted({(d.get("provenance") or {}).get("source", "unknown") for d in drafts})
    for src in sources_seen:
        # List one ref per source for the header (first encountered)
        for d in drafts:
            if (d.get("provenance") or {}).get("source") == src:
                ref = (d.get("provenance") or {}).get("ref", "unknown")
                header_lines.append(f"#   {src}: {ref}")
                break
    header_lines.append("# Review each gate below. Delete or edit as needed before running build.")
    header_lines.append("")

    body_dict: dict = {"language": language, "gates": []}
    body_dict["gates"] = [_gate_to_schema_dict(d) for d in drafts]
    body_yaml = yaml.safe_dump(body_dict, sort_keys=False, default_flow_style=False)

    if not drafts:
        # Empty gates list — emit header + body without per-gate comments
        return "\n".join(header_lines) + body_yaml

    # Splice per-gate comments above each gate entry. We re-render gates one
    # at a time so each gets its provenance comment block.
    out_lines: list[str] = list(header_lines)
    out_lines.append(f"language: {language}")
    out_lines.append("gates:")
    for draft in drafts:
        out_lines.append(_gate_comment_block(draft))
        gate_dict = _gate_to_schema_dict(draft)
        gate_yaml = yaml.safe_dump(
            [gate_dict], sort_keys=False, default_flow_style=False,
        )
        # safe_dump with a list emits "- key: val" lines; indent each by 2 spaces
        for line in gate_yaml.splitlines():
            out_lines.append(f"  {line}")
    return "\n".join(out_lines) + "\n"


def run_write_criteria(sg: Path) -> Path:
    """Load drafts.json + grounding.json, write criteria.yaml.proposed."""
    drafts_payload = load_json(synthesis_path(sg, "drafts.json"))
    try:
        grounding = load_json(synthesis_path(sg, "grounding.json"))
        language = grounding.get("language_detected", "unknown")
    except FileNotFoundError:
        language = "unknown"

    rendered = render_criteria_yaml(drafts_payload, language=language)
    out_path = sg / "criteria.yaml.proposed"
    out_path.write_text(rendered)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 4: write criteria.yaml.proposed")
    parser.add_argument(
        "--skillgoid-dir",
        type=Path,
        default=Path(".skillgoid"),
        help="Path to .skillgoid directory (default ./.skillgoid)",
    )
    args = parser.parse_args(argv)

    try:
        out_path = run_write_criteria(args.skillgoid_dir)
    except FileNotFoundError as exc:
        sys.stderr.write(f"write_criteria: {exc}\n")
        return 1

    sys.stdout.write(f"wrote: {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
