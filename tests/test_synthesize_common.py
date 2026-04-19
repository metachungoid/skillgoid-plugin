"""Tests for scripts/synthesize/_common.py — JSON IO helpers."""
import pytest

from scripts.synthesize._common import (
    SYNTHESIS_SUBDIR,
    ensure_synthesis_dir,
    load_json,
    save_json,
    synthesis_path,
)


def test_synthesis_subdir_constant():
    assert SYNTHESIS_SUBDIR == "synthesis"


def test_synthesis_path_joins_under_skillgoid(tmp_path):
    sg = tmp_path / ".skillgoid"
    out = synthesis_path(sg, "grounding.json")
    assert out == sg / "synthesis" / "grounding.json"


def test_ensure_synthesis_dir_creates_when_missing(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    out = ensure_synthesis_dir(sg)
    assert out.exists() and out.is_dir()
    assert out == sg / "synthesis"


def test_ensure_synthesis_dir_idempotent(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    ensure_synthesis_dir(sg)
    # Second call must not raise
    ensure_synthesis_dir(sg)


def test_save_json_then_load_json_round_trip(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    ensure_synthesis_dir(sg)
    target = synthesis_path(sg, "drafts.json")
    payload = {"drafts": [{"id": "x", "type": "pytest"}]}
    save_json(target, payload)
    assert load_json(target) == payload


def test_load_json_missing_file_raises_filenotfound(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    target = synthesis_path(sg, "missing.json")
    with pytest.raises(FileNotFoundError):
        load_json(target)


def test_save_json_pretty_prints_with_trailing_newline(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    ensure_synthesis_dir(sg)
    target = synthesis_path(sg, "x.json")
    save_json(target, {"a": 1})
    text = target.read_text()
    # Pretty-printed (indent=2) and ends with newline
    assert text == '{\n  "a": 1\n}\n'
