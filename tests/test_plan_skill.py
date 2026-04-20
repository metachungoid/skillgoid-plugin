"""Prose-contract tests for skills/plan/SKILL.md (v0.12: context7 grounding)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).parent.parent / "skills" / "plan" / "SKILL.md"


def test_plan_skill_references_context7():
    text = SKILL.read_text()
    assert "context7" in text, (
        "SKILL.md must reference context7 in the new step 2.5. See v0.12 spec."
    )


def test_plan_skill_references_grounding_file_path():
    text = SKILL.read_text()
    assert ".skillgoid/context7/framework-grounding.md" in text, (
        "SKILL.md must name the grounding file path explicitly. See v0.12 spec."
    )


def test_plan_skill_references_skipped_sentinel():
    text = SKILL.read_text()
    assert ".skillgoid/context7/SKIPPED" in text, (
        "SKILL.md must name the SKIPPED sentinel path explicitly. See v0.12 spec."
    )


def test_plan_skill_dispatches_context7_fetcher():
    text = SKILL.read_text()
    assert "context7-fetcher" in text, (
        "SKILL.md step 2.5 must reference the fetcher prompt path (context7-fetcher.md). "
        "See v0.12 spec."
    )


def test_plan_skill_documents_refresh_flag():
    text = SKILL.read_text()
    assert "--refresh-context7" in text, (
        "SKILL.md must document the --refresh-context7 flag. See v0.12 spec."
    )
