"""Prose-contract tests for skills/clarify/SKILL.md."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).parent.parent / "skills" / "clarify" / "SKILL.md"


def test_clarify_asks_one_question_at_a_time():
    text = SKILL.read_text()
    assert "one question" in text.lower(), (
        "SKILL.md must contain an explicit 'one question' rule — Claude was "
        "observed dumping all questions at once without it."
    )


def test_clarify_does_not_cap_rounds():
    text = SKILL.read_text()
    assert "max 6" not in text, (
        "SKILL.md must not cap clarifying rounds at 6 — the conversation should "
        "stay open until the user explicitly signals readiness."
    )


def test_clarify_has_explicit_ready_signal():
    text = SKILL.read_text()
    assert "ready" in text.lower(), (
        "SKILL.md must tell the user how to signal they are done clarifying "
        "(e.g. 'say ready' or 'type ready to proceed')."
    )


def test_clarify_surfaces_unknown_unknowns():
    text = SKILL.read_text()
    assert "unknown" in text.lower() or "haven't considered" in text.lower() or "may not" in text.lower(), (
        "SKILL.md must instruct Claude to surface non-obvious decisions the user "
        "may not have considered, not just answer explicit questions."
    )
