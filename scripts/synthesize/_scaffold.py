"""Per-gate-type should-fail scaffold builder for oracle validation.

build_scaffold is a context manager that yields a tmpdir populated with the
minimum structure a gate type needs to execute without setup errors. The
goal is for the adapter to fail in the *content* layer (no tests found, no
real code imported) rather than the *structural* layer (missing pyproject,
missing src).

Per-type factory rules are encoded in _GATE_SCAFFOLDS. Adding a new gate
type = add one entry.
"""
from __future__ import annotations

import contextlib
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Callable, Iterator


def _copy_tool_section(analogue_cache_dir: Path | None, section: str, scaffold: Path) -> None:
    """If analogue pyproject.toml has [tool.<section>], copy that section.

    Writes to scaffold/pyproject.toml. No-op if analogue is None or has no
    pyproject or no matching section.
    """
    if analogue_cache_dir is None:
        return
    src = analogue_cache_dir / "pyproject.toml"
    if not src.exists():
        return
    try:
        data = tomllib.loads(src.read_text())
    except tomllib.TOMLDecodeError:
        return
    tool_data = data.get("tool", {}).get(section)
    if tool_data is None:
        return
    dst = scaffold / "pyproject.toml"
    lines = [f"[tool.{section}]"]
    for k, v in tool_data.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {str(v).lower()}")
        elif isinstance(v, int):
            lines.append(f"{k} = {v}")
        elif isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, list):
            items = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
            lines.append(f"{k} = [{items}]")
    dst.write_text("\n".join(lines) + "\n")


def _scaffold_pytest(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    (scaffold / "tests").mkdir()


def _scaffold_ruff(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    (scaffold / "src").mkdir()
    (scaffold / "src" / "__init__.py").write_text("")
    _copy_tool_section(analogue, "ruff", scaffold)


def _scaffold_mypy(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    (scaffold / "src").mkdir()
    (scaffold / "src" / "__init__.py").write_text("")
    _copy_tool_section(analogue, "mypy", scaffold)


def _scaffold_coverage(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    (scaffold / "tests").mkdir()
    (scaffold / "src").mkdir()
    (scaffold / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\n'
    )


def _scaffold_cli_command_runs(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    src_dir = scaffold / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("def main():\n    raise SystemExit(1)\n")
    (scaffold / "pyproject.toml").write_text(
        "[project]\n"
        'name = "scaffold"\n'
        'version = "0.0.0"\n'
        "[project.scripts]\n"
        'scaffold = "app:main"\n'
    )


def _scaffold_run_command(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    pass


def _scaffold_import_clean(scaffold: Path, gate: dict, analogue: Path | None) -> None:
    # Adapter reads `module:`; fall back to args[0] for tolerance, then default.
    candidate = gate.get("module")
    if not candidate:
        args = gate.get("args") or []
        candidate = args[0] if args else "mypackage"
    # Reject anything that isn't a bare Python identifier (path traversal guard).
    pkg_name = candidate if isinstance(candidate, str) and candidate.isidentifier() else "mypackage"
    pkg_dir = scaffold / "src" / pkg_name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text('raise ImportError("scaffold")\n')


_GATE_SCAFFOLDS: dict[str, Callable[[Path, dict, Path | None], None]] = {
    "pytest": _scaffold_pytest,
    "ruff": _scaffold_ruff,
    "mypy": _scaffold_mypy,
    "coverage": _scaffold_coverage,
    "cli-command-runs": _scaffold_cli_command_runs,
    "run-command": _scaffold_run_command,
    "import-clean": _scaffold_import_clean,
}


@contextlib.contextmanager
def build_scaffold(
    gate_type: str,
    gate: dict,
    analogue_cache_dir: Path | None,
) -> Iterator[Path]:
    """Yield a freshly-created tmpdir populated per gate_type's scaffold rules.

    On exit the tmpdir and all contents are removed. Raises ValueError if
    gate_type has no scaffold rule.
    """
    factory = _GATE_SCAFFOLDS.get(gate_type)
    if factory is None:
        raise ValueError(
            f"unsupported gate type for scaffold: {gate_type} — "
            f"add a row to _GATE_SCAFFOLDS"
        )
    tmp = Path(tempfile.mkdtemp(prefix="skillgoid-scaffold-"))
    try:
        factory(tmp, gate, analogue_cache_dir)
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
