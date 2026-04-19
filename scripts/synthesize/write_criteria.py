#!/usr/bin/env python3
"""Skillgoid synthesize-gates Stage 4: render criteria.yaml.proposed.

Reads drafts.json and (optionally) grounding.json; produces criteria.yaml
.proposed with provenance comment headers per gate. Output conforms to
schemas/criteria.schema.json.

Labels per gate are read from `.skillgoid/synthesis/validated.json` when
present (written by Stage 3). When absent, every gate defaults to
`validated: none, warn: validation artifact missing`.

NEVER overwrites an existing criteria.yaml. Always writes to
.skillgoid/criteria.yaml.proposed.

Contract:
    render_criteria_yaml(
        drafts: dict, language: str, validated_payload: dict | None = None,
    ) -> str
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

# Internal-only fields stripped before YAML emission (not in criteria schema)
INTERNAL_FIELDS = frozenset({"provenance", "rationale"})


def _gate_to_schema_dict(draft: dict) -> dict:
    """Strip internal fields from a draft to produce a schema-conformant gate."""
    return {k: v for k, v in draft.items() if k not in INTERNAL_FIELDS}


def _gate_comment_block(draft: dict, validated_entry: dict | None) -> str:
    """Build the comment lines that precede a gate in the rendered YAML."""
    prov = draft.get("provenance") or {}
    source = prov.get("source", "unknown")
    ref = prov.get("ref", "unknown")
    lines: list[str] = []
    if isinstance(ref, list):
        lines.append(f"  # source: {source}, refs:")
        for r in ref:
            lines.append(f"  #   - {r}")
    else:
        lines.append(f"  # source: {source}, ref: {ref}")

    if validated_entry is None:
        label = "none"
        warn = "validation artifact missing"
    else:
        label = validated_entry.get("validated", "none")
        warn = validated_entry.get("warn")
    lines.append(f"  # validated: {label}")
    if warn:
        lines.append(f"  # warn: {warn}")

    rationale = draft.get("rationale")
    if rationale:
        lines.append(f"  # rationale: {rationale}")
    return "\n".join(lines)


def render_criteria_yaml(
    drafts_payload: dict,
    language: str,
    validated_payload: dict | None = None,
) -> str:
    """Render drafts to a criteria.yaml string with provenance comments.

    The output is valid YAML and conforms to schemas/criteria.schema.json.
    """
    drafts = drafts_payload.get("drafts", [])
    today = dt.date.today().isoformat()

    validated_by_id: dict[str, dict] = {}
    if validated_payload:
        for entry in validated_payload.get("gates", []):
            validated_by_id[entry["id"]] = entry

    header_lines = [
        f"# Skillgoid criteria — synthesized {today} from:",
    ]
    sources_seen = sorted({(d.get("provenance") or {}).get("source", "unknown") for d in drafts})
    for src in sources_seen:
        # List one ref per source for the header (first encountered)
        for d in drafts:
            if (d.get("provenance") or {}).get("source") == src:
                ref = (d.get("provenance") or {}).get("ref", "unknown")
                if isinstance(ref, list):
                    ref = ref[0]
                header_lines.append(f"#   {src}: {ref}")
                break
    header_lines.append("# Review each gate below. Delete or edit as needed before running build.")
    header_lines.append(
        "# A `validated: oracle` label means the gate discriminated the analogue "
        "from an empty scaffold; it is not proof of correctness."
    )
    header_lines.append("")

    # Splice per-gate comments above each gate entry. We re-render gates one
    # at a time so each gets its provenance comment block. For the empty
    # case we simply emit `gates: []` with no per-gate loop iterations.
    out_lines: list[str] = list(header_lines)
    out_lines.append(f"language: {language}")
    if drafts:
        out_lines.append("gates:")
        for draft in drafts:
            entry = validated_by_id.get(draft["id"])
            out_lines.append(_gate_comment_block(draft, entry))
            gate_dict = _gate_to_schema_dict(draft)
            gate_yaml = yaml.safe_dump(
                [gate_dict], sort_keys=False, default_flow_style=False, indent=2,
            )
            # safe_dump with a list emits "- key: val" lines; indent each by 2 spaces
            for line in gate_yaml.splitlines():
                out_lines.append(f"  {line}")
    else:
        out_lines.append("gates: []")
    return "\n".join(out_lines) + "\n"


def run_write_criteria(sg: Path) -> Path:
    """Load drafts.json + grounding.json + (optional) validated.json, write criteria.yaml.proposed."""
    drafts_payload = load_json(synthesis_path(sg, "drafts.json"))
    try:
        grounding = load_json(synthesis_path(sg, "grounding.json"))
        language = grounding.get("language_detected", "unknown")
    except FileNotFoundError:
        sys.stderr.write("write_criteria: grounding.json missing, defaulting language=unknown\n")
        language = "unknown"

    try:
        validated_payload = load_json(synthesis_path(sg, "validated.json"))
    except FileNotFoundError:
        validated_payload = None

    rendered = render_criteria_yaml(
        drafts_payload, language=language, validated_payload=validated_payload,
    )
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
