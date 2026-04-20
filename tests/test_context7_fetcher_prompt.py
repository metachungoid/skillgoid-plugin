"""Prose-contract tests for skills/plan/prompts/context7-fetcher.md (v0.12)."""
from __future__ import annotations

from pathlib import Path

PROMPT = (
    Path(__file__).parent.parent
    / "skills"
    / "plan"
    / "prompts"
    / "context7-fetcher.md"
)


def test_fetcher_prompt_exists():
    assert PROMPT.exists(), (
        "skills/plan/prompts/context7-fetcher.md must exist (new file in v0.12)."
    )


def test_fetcher_prompt_reads_goal():
    text = PROMPT.read_text()
    assert "goal.md" in text, (
        "Fetcher prompt must instruct the subagent to read .skillgoid/goal.md."
    )


def test_fetcher_prompt_reads_manifest():
    text = PROMPT.read_text()
    assert "pyproject.toml" in text, (
        "Fetcher prompt must instruct the subagent to read at least one manifest "
        "file (pyproject.toml as the canonical example)."
    )


def test_fetcher_prompt_names_context7_mcp():
    text = PROMPT.read_text()
    assert "context7" in text, (
        "Fetcher prompt must reference the context7 MCP by name."
    )


def test_fetcher_prompt_documents_skipped_signal():
    text = PROMPT.read_text()
    assert "SKIPPED:" in text, (
        "Fetcher prompt must document the 'SKIPPED: <reason>' stdout signal for "
        "graceful failure."
    )


def test_fetcher_prompt_documents_output_schema():
    text = PROMPT.read_text()
    assert "Project structure" in text, (
        "Fetcher prompt must require a '## Project structure' output section."
    )
    assert "Testing patterns" in text, (
        "Fetcher prompt must require a '## Testing patterns' output section."
    )
    assert "Common pitfalls" in text, (
        "Fetcher prompt must require a '## Common pitfalls' output section."
    )
