"""Tests for scripts/blueprint_slice.py — chunk-aware blueprint slicer."""
from pathlib import Path

import pytest

from scripts.blueprint_slice import slice_blueprint


BLUEPRINT_WITH_ALL_SECTIONS = """\
# Blueprint — test

## Architecture overview

Arch text here.

## Cross-chunk types

Nil — defined in values.py.

## scaffold

Scaffold section.

## parser

Parser section.

## evaluator-core

Evaluator section.
"""

BLUEPRINT_NO_CROSS_CHUNK_TYPES = """\
# Blueprint — test

## Architecture overview

Arch text.

## scaffold

Scaffold.

## parser

Parser.
"""

BLUEPRINT_NO_H2 = """\
# Blueprint — legacy

Just prose, no H2 headings.
"""


def test_slice_returns_chunk_section_plus_overview_plus_types():
    result = slice_blueprint(BLUEPRINT_WITH_ALL_SECTIONS, "parser")
    assert "## Architecture overview" in result
    assert "Arch text here." in result
    assert "## Cross-chunk types" in result
    assert "Nil — defined in values.py." in result
    assert "## parser" in result
    assert "Parser section." in result
    # Should NOT include other chunks' sections
    assert "## scaffold" not in result
    assert "Scaffold section." not in result
    assert "## evaluator-core" not in result
    assert "Evaluator section." not in result


def test_slice_works_for_first_chunk():
    result = slice_blueprint(BLUEPRINT_WITH_ALL_SECTIONS, "scaffold")
    assert "## scaffold" in result
    assert "Scaffold section." in result
    assert "## parser" not in result


def test_slice_without_cross_chunk_types_warns(capsys):
    result = slice_blueprint(BLUEPRINT_NO_CROSS_CHUNK_TYPES, "parser")
    captured = capsys.readouterr()
    assert "Cross-chunk types" in captured.err  # warning present
    # Still returns arch + chunk section
    assert "## Architecture overview" in result
    assert "## parser" in result
    assert "Parser." in result


def test_slice_unknown_chunk_id_raises():
    with pytest.raises(ValueError, match="does-not-exist"):
        slice_blueprint(BLUEPRINT_WITH_ALL_SECTIONS, "does-not-exist")


def test_slice_legacy_no_h2_returns_full_content(capsys):
    result = slice_blueprint(BLUEPRINT_NO_H2, "anything")
    captured = capsys.readouterr()
    assert "no H2 headings" in captured.err
    assert result == BLUEPRINT_NO_H2


def test_slice_chunk_id_with_hyphen():
    md = """\
# Blueprint

## Architecture overview
Arch.

## special-forms
Special forms section.

## tail-calls
Tail calls section.
"""
    result = slice_blueprint(md, "special-forms")
    assert "## special-forms" in result
    assert "Special forms section." in result
    assert "## tail-calls" not in result


def test_slice_cli_valid(tmp_path: Path):
    import subprocess
    import sys
    bp = tmp_path / "blueprint.md"
    bp.write_text(BLUEPRINT_WITH_ALL_SECTIONS)
    result = subprocess.run(
        [sys.executable, "scripts/blueprint_slice.py",
         "--blueprint", str(bp), "--chunk-id", "parser"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "## parser" in result.stdout
    assert "Parser section." in result.stdout


def test_slice_cli_unknown_chunk_returns_two(tmp_path: Path):
    import subprocess
    import sys
    bp = tmp_path / "blueprint.md"
    bp.write_text(BLUEPRINT_WITH_ALL_SECTIONS)
    result = subprocess.run(
        [sys.executable, "scripts/blueprint_slice.py",
         "--blueprint", str(bp), "--chunk-id", "nonexistent"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "nonexistent" in result.stderr
