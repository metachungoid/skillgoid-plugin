"""Tests for scripts/synthesize/_scaffold.py — per-gate-type should-fail scaffolds."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.synthesize._scaffold import build_scaffold


def _read_pyproject(path: Path) -> str:
    return (path / "pyproject.toml").read_text() if (path / "pyproject.toml").exists() else ""


def test_scaffold_pytest_creates_empty_tests_dir(tmp_path):
    gate = {"id": "pytest_main", "type": "pytest", "args": ["tests"]}
    with build_scaffold("pytest", gate, analogue_cache_dir=None) as scaffold:
        assert (scaffold / "tests").is_dir()
        assert list((scaffold / "tests").iterdir()) == []


def test_scaffold_ruff_creates_empty_src_and_copies_ruff_config(tmp_path):
    analogue = tmp_path / "analogue"
    analogue.mkdir()
    (analogue / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[tool.ruff]\nline-length = 120\n'
    )
    gate = {"id": "lint", "type": "ruff", "args": ["check", "."]}
    with build_scaffold("ruff", gate, analogue_cache_dir=analogue) as scaffold:
        assert (scaffold / "src" / "__init__.py").exists()
        assert (scaffold / "src" / "__init__.py").read_text() == ""
        pyproject = _read_pyproject(scaffold)
        assert "[tool.ruff]" in pyproject
        assert "line-length = 120" in pyproject


def test_scaffold_mypy_creates_empty_src_and_copies_mypy_config(tmp_path):
    analogue = tmp_path / "analogue"
    analogue.mkdir()
    (analogue / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[tool.mypy]\nstrict = true\n'
    )
    gate = {"id": "typecheck", "type": "mypy", "args": ["src"]}
    with build_scaffold("mypy", gate, analogue_cache_dir=analogue) as scaffold:
        assert (scaffold / "src" / "__init__.py").exists()
        pyproject = _read_pyproject(scaffold)
        assert "[tool.mypy]" in pyproject
        assert "strict = true" in pyproject


def test_scaffold_coverage_creates_tests_and_src(tmp_path):
    gate = {"id": "cov", "type": "coverage", "min_percent": 80}
    with build_scaffold("coverage", gate, analogue_cache_dir=None) as scaffold:
        assert (scaffold / "tests").is_dir()
        assert (scaffold / "src").is_dir()
        pyproject = _read_pyproject(scaffold)
        assert "testpaths" in pyproject
        assert '["tests"]' in pyproject


def test_scaffold_cli_command_runs_emits_failing_entry_point(tmp_path):
    gate = {"id": "cli", "type": "cli-command-runs", "args": ["mycli", "--help"]}
    with build_scaffold("cli-command-runs", gate, analogue_cache_dir=None) as scaffold:
        app = scaffold / "src" / "app.py"
        assert app.exists()
        assert "raise SystemExit(1)" in app.read_text()
        pyproject = _read_pyproject(scaffold)
        assert "[project.scripts]" in pyproject


def test_scaffold_run_command_is_empty_tmpdir(tmp_path):
    gate = {"id": "run", "type": "run-command", "command": ["echo", "hi"]}
    with build_scaffold("run-command", gate, analogue_cache_dir=None) as scaffold:
        assert list(scaffold.iterdir()) == []


def test_scaffold_import_clean_emits_failing_package(tmp_path):
    gate = {"id": "imp", "type": "import-clean", "args": ["mypackage"]}
    with build_scaffold("import-clean", gate, analogue_cache_dir=None) as scaffold:
        init = scaffold / "src" / "mypackage" / "__init__.py"
        assert init.exists()
        assert "raise ImportError" in init.read_text()


def test_scaffold_import_clean_prefers_module_key(tmp_path):
    """Adapter reads `module:`, scaffold should too."""
    gate = {"id": "imp", "type": "import-clean", "module": "myapp"}
    with build_scaffold("import-clean", gate, analogue_cache_dir=None) as scaffold:
        assert (scaffold / "src" / "myapp" / "__init__.py").exists()


def test_scaffold_import_clean_rejects_path_traversal(tmp_path):
    """A malicious pkg name (e.g. '../escape') must not create dirs outside scaffold."""
    gate = {"id": "imp", "type": "import-clean", "module": "../../escape"}
    with build_scaffold("import-clean", gate, analogue_cache_dir=None) as scaffold:
        # Falls back to safe default 'mypackage'
        assert (scaffold / "src" / "mypackage" / "__init__.py").exists()
        # Nothing escaped the scaffold root
        assert not (scaffold.parent / "escape").exists()


def test_scaffold_unknown_gate_type_errors(tmp_path):
    gate = {"id": "x", "type": "future-type"}
    with pytest.raises(ValueError, match="unsupported gate type"):
        with build_scaffold("future-type", gate, analogue_cache_dir=None):
            pass


def test_scaffold_cleans_up_on_exit(tmp_path):
    gate = {"id": "pytest_main", "type": "pytest"}
    with build_scaffold("pytest", gate, analogue_cache_dir=None) as scaffold:
        assert scaffold.exists()
        captured = scaffold
    assert not captured.exists()
