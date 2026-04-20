"""Prose-contract tests for skills/build/SKILL.md (v0.12: context7 grounding attachment)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).parent.parent / "skills" / "build" / "SKILL.md"


def test_build_skill_attaches_context7_grounding():
    text = SKILL.read_text()
    assert ".skillgoid/context7/framework-grounding.md" in text, (
        "SKILL.md step 3b/3c must reference the grounding file as a per-chunk "
        "subagent attachment. See v0.12 spec."
    )


def test_build_skill_marks_grounding_advisory():
    text = SKILL.read_text()
    assert "advisory" in text.lower(), (
        "SKILL.md must label the context7 grounding attachment as advisory so the "
        "chunk subagent doesn't treat it as a requirements document. See v0.12 spec."
    )
