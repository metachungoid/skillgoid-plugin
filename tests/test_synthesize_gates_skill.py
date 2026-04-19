"""Sanity assertions over skills/synthesize-gates/SKILL.md content."""
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "synthesize-gates" / "SKILL.md"


def test_skill_references_stage_3_validate_script():
    text = SKILL.read_text()
    assert "scripts/synthesize/validate.py" in text


def test_skill_documents_skip_validation_flag():
    text = SKILL.read_text()
    assert "--skip-validation" in text


def test_skill_documents_validate_only_flag():
    text = SKILL.read_text()
    assert "--validate-only" in text


def test_skill_phase2_limitations_reflect_v011_oracle():
    text = SKILL.read_text()
    assert "v0.11" in text or "oracle validates" in text
