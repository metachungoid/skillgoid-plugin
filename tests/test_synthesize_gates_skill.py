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


def test_skill_documents_stage2_retry_prompt():
    text = SKILL.read_text()
    assert "Your previous output failed Stage 2 validation" in text, (
        "SKILL.md step 6 must instruct the retry to surface the Stage 2 stderr "
        "to the subagent. See v0.11.1 spec."
    )


def test_skill_documents_retry_stop_condition():
    text = SKILL.read_text()
    assert "failed Stage 2 validation twice" in text, (
        "SKILL.md step 6 must document the STOP condition after two failed attempts."
    )


def test_skill_removes_stale_phase1_no_retry_text():
    text = SKILL.read_text()
    assert "Phase 2 will add a single auto-retry" not in text, (
        "Stale pre-v0.11.1 note must be removed when retry ships."
    )
