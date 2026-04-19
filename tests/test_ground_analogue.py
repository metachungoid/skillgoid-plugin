"""Tests for scripts/synthesize/ground_analogue.py.

Reads vendored mini-flask-demo fixture and asserts observation extraction.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.synthesize.ground_analogue import (
    Observation,
    _classify_command,
    detect_language,
    extract_observations,
    follow_wrapper_script,
    parse_pyproject_test_command,
    parse_pyproject_tool_sections,
    parse_workflow_steps,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthesize" / "mini-flask-demo"
CLI = [sys.executable, str(ROOT / "scripts" / "synthesize" / "ground_analogue.py")]


def test_detect_language_python_from_pyproject():
    assert detect_language(FIXTURE) == "python"


def test_detect_language_unknown_when_no_manifest(tmp_path):
    assert detect_language(tmp_path) == "unknown"


def test_parse_pyproject_test_command_returns_pytest_for_miniflask():
    cmd = parse_pyproject_test_command(FIXTURE / "pyproject.toml")
    # pyproject declares testpaths = ["tests"], pytest is the implied runner
    assert cmd == ["pytest", "tests"]


def test_parse_workflow_steps_extracts_run_lines():
    steps = parse_workflow_steps(FIXTURE / ".github" / "workflows" / "test.yml")
    # Workflow has: pip install, ruff check ., pytest -v
    assert "ruff check ." in steps
    assert "pytest -v" in steps


def test_extract_observations_returns_typed_observations():
    obs = extract_observations(FIXTURE)
    # Must include at least: pytest from pyproject, ruff from workflow,
    # pytest variant from workflow
    types_seen = {o.observed_type for o in obs}
    assert "pytest" in types_seen
    assert "ruff" in types_seen


def test_extract_observations_each_carries_source_ref():
    obs = extract_observations(FIXTURE)
    for o in obs:
        assert o.source == "analogue"
        assert o.ref.startswith(str(FIXTURE.name))  # ref is relative-ish to the repo
        assert o.command  # never empty


def test_observation_to_dict_round_trip():
    o = Observation(
        source="analogue",
        ref="mini-flask-demo/pyproject.toml",
        command="pytest tests",
        context="declared test command",
        observed_type="pytest",
    )
    d = o.to_dict()
    assert d == {
        "source": "analogue",
        "ref": "mini-flask-demo/pyproject.toml",
        "command": "pytest tests",
        "context": "declared test command",
        "observed_type": "pytest",
    }


def test_cli_emits_json_list_to_stdout():
    result = subprocess.run(
        CLI + [str(FIXTURE)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) >= 2
    for entry in payload:
        assert entry["source"] == "analogue"


def test_cli_exits_one_on_missing_repo(tmp_path):
    result = subprocess.run(
        CLI + [str(tmp_path / "nope")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "does not exist" in result.stderr


def test_classify_command_pytest():
    assert _classify_command("pytest tests") == "pytest"
    assert _classify_command("pytest -v --cov") == "pytest"


def test_classify_command_ruff():
    assert _classify_command("ruff check .") == "ruff"


def test_classify_command_mypy():
    assert _classify_command("mypy src") == "mypy"


def test_classify_command_coverage():
    assert _classify_command("coverage run -m pytest") == "coverage"


def test_classify_command_unrecognized_defaults_to_run_command():
    # Policy: unrecognized commands default to "run-command", NEVER to
    # "cli-command-runs". cli-command-runs is reserved for explicit
    # single-binary smoke tests.
    assert _classify_command("pip install -e .") == "run-command"
    assert _classify_command("make build") == "run-command"
    assert _classify_command("npm test") == "run-command"


def test_classify_command_empty_string_returns_run_command():
    # Empty input falls through the same path as any unrecognized head,
    # so per the policy it also lands on "run-command" (never None,
    # never "cli-command-runs"). Lock in the current behavior.
    assert _classify_command("") == "run-command"
    assert _classify_command("   ") == "run-command"


def test_parse_pyproject_tool_sections_pytest_only(tmp_path):
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.pytest.ini_options]\n"
        'addopts = "-rxXs"\n'
    )
    out = parse_pyproject_tool_sections(pp)
    assert out == [("pytest", "pytest", "tool.pytest.ini_options")]


def test_parse_pyproject_tool_sections_all_four(tmp_path):
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.pytest.ini_options]\n"
        'addopts = "-rxXs"\n'
        "[tool.ruff.lint]\n"
        'select = ["E", "F"]\n'
        "[tool.mypy]\n"
        "strict = true\n"
        "[tool.coverage.run]\n"
        'omit = ["venv/*"]\n'
    )
    out = parse_pyproject_tool_sections(pp)
    # Order is stable: pytest, ruff, mypy, coverage
    assert out == [
        ("pytest", "pytest", "tool.pytest.ini_options"),
        ("ruff", "ruff check .", "tool.ruff.lint"),
        ("mypy", "mypy .", "tool.mypy"),
        ("coverage", "coverage run -m pytest", "tool.coverage.run"),
    ]


def test_parse_pyproject_tool_sections_ruff_top_level(tmp_path):
    # [tool.ruff] with no sub-section still counts as ruff configured.
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.ruff]\n"
        "line-length = 100\n"
    )
    out = parse_pyproject_tool_sections(pp)
    assert out == [("ruff", "ruff check .", "tool.ruff")]


def test_parse_pyproject_tool_sections_ruff_lint_wins_over_bare_ruff(tmp_path):
    # When both [tool.ruff] and [tool.ruff.lint] coexist, only tool.ruff.lint
    # should be emitted (more specific sub-section wins via seen_tools dedup).
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.ruff]\n"
        "line-length = 100\n"
        "[tool.ruff.lint]\n"
        "select = ['E']\n"
    )
    out = parse_pyproject_tool_sections(pp)
    assert len(out) == 1
    assert out[0] == ("ruff", "ruff check .", "tool.ruff.lint")


def test_parse_pyproject_tool_sections_missing_returns_empty(tmp_path):
    pp = tmp_path / "pyproject.toml"
    assert parse_pyproject_tool_sections(pp) == []


def test_parse_pyproject_tool_sections_malformed_returns_empty(tmp_path):
    pp = tmp_path / "pyproject.toml"
    pp.write_text("not valid toml =[[[\n")
    assert parse_pyproject_tool_sections(pp) == []


def test_parse_pyproject_tool_sections_no_recognized_tools(tmp_path):
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.poetry]\n"
        'name = "demo"\n'
        "[tool.black]\n"
        'line-length = 88\n'
    )
    # Neither poetry nor black is in our recognized set.
    assert parse_pyproject_tool_sections(pp) == []


def test_extract_observations_emits_from_pyproject_tool_sections(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'addopts = "-rxXs"\n'
        "[tool.ruff.lint]\n"
        'select = ["E"]\n'
        "[tool.mypy]\n"
        "strict = true\n"
    )
    obs = extract_observations(repo)
    # Should include one observation per tool section, in order.
    types_seen = [o.observed_type for o in obs]
    assert "pytest" in types_seen
    assert "ruff" in types_seen
    assert "mypy" in types_seen
    # Each pyproject observation refs the section path
    pyproject_obs = [o for o in obs if "pyproject.toml" in o.ref]
    refs = {o.ref for o in pyproject_obs}
    assert "demo/pyproject.toml#tool.pytest.ini_options" in refs
    assert "demo/pyproject.toml#tool.ruff.lint" in refs
    assert "demo/pyproject.toml#tool.mypy" in refs
    # Context names the section
    for o in pyproject_obs:
        assert "pyproject.toml" in o.context


def test_extract_observations_pyproject_wins_over_workflow_on_dedup(tmp_path):
    # A workflow step that emits the same (command, type) pair as the
    # pyproject observation — the pyproject observation must win.
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[tool.ruff.lint]\nselect = ['E']\n")
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "name: ci\non: [push]\njobs:\n"
        "  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: ruff check .\n"
    )
    obs = extract_observations(repo)
    ruff_obs = [o for o in obs if o.observed_type == "ruff"]
    assert len(ruff_obs) == 1
    assert "pyproject.toml#tool.ruff.lint" in ruff_obs[0].ref
    assert "workflows" not in ruff_obs[0].ref


def test_follow_wrapper_script_extracts_commands(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    script = repo / "scripts" / "test"
    script.write_text(
        "#!/bin/sh\n"
        "set -e\n"
        "\n"
        "# Run the suite\n"
        "pytest tests/\n"
        "ruff check .\n"
    )
    out = follow_wrapper_script(script, repo)
    assert out == ["pytest tests/", "ruff check ."]


def test_follow_wrapper_script_strips_prefix_substitutions(tmp_path):
    # Real-world httpx pattern: ${PREFIX}pytest "$@"
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    script = repo / "scripts" / "test"
    script.write_text(
        "#!/bin/sh\n"
        'export PREFIX=""\n'
        '${PREFIX}coverage run -m pytest "$@"\n'
        '${PREFIX}ruff check .\n'
    )
    out = follow_wrapper_script(script, repo)
    # Prefix substitution is stripped so the classifier can see the real head
    assert out == ['coverage run -m pytest "$@"', "ruff check ."]


def test_follow_wrapper_script_skips_shell_builtins(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    script = repo / "scripts" / "test"
    script.write_text(
        "#!/bin/sh\n"
        "export FOO=bar\n"
        "set -ex\n"
        "if [ -z $X ]; then\n"
        "  pytest\n"
        "fi\n"
        "cd ..\n"
    )
    out = follow_wrapper_script(script, repo)
    # Only `pytest` survives — export/set/if/fi/cd are filtered
    assert out == ["pytest"]


def test_follow_wrapper_script_missing_returns_empty(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    assert follow_wrapper_script(repo / "nope", repo) == []


def test_follow_wrapper_script_rejects_path_outside_repo(tmp_path):
    # Security: script must be inside repo_root
    repo = tmp_path / "demo"
    repo.mkdir()
    outside = tmp_path / "outside.sh"
    outside.write_text("#!/bin/sh\npytest\n")
    assert follow_wrapper_script(outside, repo) == []


def test_follow_wrapper_script_inline_env_prefix(tmp_path):
    # PYTHONPATH=src pytest and CI=1 ruff should emit the command, not be dropped.
    # Compound case (FOO=a BAZ=b mypy) should peel both assignments.
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    script = repo / "scripts" / "test"
    script.write_text(
        "#!/bin/sh\n"
        "PYTHONPATH=src pytest tests/\n"
        "CI=1 ruff check .\n"
        "FOO=a BAZ=b mypy .\n"
    )
    out = follow_wrapper_script(script, repo)
    assert out == ["pytest tests/", "ruff check .", "mypy ."]


def test_follow_wrapper_script_caps_at_100_lines(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    script = repo / "scripts" / "test"
    body = "#!/bin/sh\n" + "\n".join(f"cmd_{i}" for i in range(200)) + "\n"
    script.write_text(body)
    out = follow_wrapper_script(script, repo)
    # 100-line cap includes the shebang line
    assert len(out) <= 100


def test_extract_observations_follows_wrapper_scripts(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()

    (repo / "scripts").mkdir()
    (repo / "scripts" / "test").write_text(
        "#!/bin/sh\n"
        "pytest tests/\n"
        "ruff check .\n"
    )

    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "name: ci\n"
        "on: [push]\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: scripts/test\n"
    )

    obs = extract_observations(repo)
    types_seen = [o.observed_type for o in obs]

    assert "pytest" in types_seen
    assert "ruff" in types_seen

    pytest_obs = [o for o in obs if o.observed_type == "pytest"]
    assert any(o.ref.endswith("scripts/test") for o in pytest_obs)

    wrapper_obs = [o for o in obs if "wrapper" in o.context.lower()]
    assert wrapper_obs, "expected at least one wrapper-derived observation"


def test_extract_observations_wrapper_follow_is_one_level_deep(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    (repo / "scripts" / "test").write_text(
        "#!/bin/sh\n"
        "scripts/inner\n"
    )
    (repo / "scripts" / "inner").write_text(
        "#!/bin/sh\n"
        "pytest\n"
    )
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "name: ci\n"
        "on: [push]\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: scripts/test\n"
    )

    obs = extract_observations(repo)
    types_seen = [o.observed_type for o in obs]
    # No pytest — scripts/inner is not followed (depth-1 only)
    assert "pytest" not in types_seen
    # scripts/inner is observed as a command head from depth-1 follow
    commands = [o.command for o in obs]
    assert any("scripts/inner" in c for c in commands)


def test_coverage_threshold_from_pyproject_fail_under(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage.report]\n"
        "fail_under = 95\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert len(thresholds) == 1
    t = thresholds[0]
    assert t.source == "analogue"
    assert t.ref.endswith("/pyproject.toml#tool.coverage.report")
    assert t.command == "coverage_threshold=95"
    assert t.context == "pyproject.toml [tool.coverage.report] declares fail_under"


def test_coverage_threshold_absent_when_fail_under_missing(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage.report]\n"
        "show_missing = true\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert thresholds == []


def test_coverage_threshold_non_int_is_skipped(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.coverage.report]\n'
        'fail_under = "ninety"\n'
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert thresholds == []


def test_coverage_threshold_bool_is_skipped(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage.report]\nfail_under = true\n"
    )
    obs = extract_observations(tmp_path)
    assert [o for o in obs if o.observed_type == "coverage_threshold"] == []


def test_coverage_threshold_from_workflow_fail_under(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "jobs:\n"
        "  t:\n"
        "    steps:\n"
        "      - run: coverage report --fail-under=85\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert len(thresholds) == 1
    t = thresholds[0]
    assert t.command == "coverage_threshold=85"
    assert t.ref.endswith("/.github/workflows/ci.yml")


def test_coverage_threshold_two_sources_emits_two_observations(tmp_path):
    # pyproject says 100, workflow says 95 — both recorded, subagent picks
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage.report]\n"
        "fail_under = 100\n"
    )
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "jobs:\n"
        "  t:\n"
        "    steps:\n"
        "      - run: coverage report --fail-under=95\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = sorted(
        (o for o in obs if o.observed_type == "coverage_threshold"),
        key=lambda o: o.command,
    )
    assert len(thresholds) == 2
    assert thresholds[0].command == "coverage_threshold=100"
    assert thresholds[1].command == "coverage_threshold=95"


def test_coverage_threshold_from_wrapper_script(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    wrapper = scripts_dir / "test"
    wrapper.write_text(
        "#!/bin/sh\n"
        "set -e\n"
        "pytest\n"
        "coverage report --fail-under=90\n"
    )
    wrapper.chmod(0o755)
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "jobs:\n"
        "  t:\n"
        "    steps:\n"
        "      - run: ./scripts/test\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert len(thresholds) == 1
    assert thresholds[0].command == "coverage_threshold=90"


def test_coverage_threshold_from_pytest_cov_flag(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "jobs:\n"
        "  t:\n"
        "    steps:\n"
        "      - run: pytest --cov=src --cov-fail-under=80\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert len(thresholds) == 1
    assert thresholds[0].command == "coverage_threshold=80"


def test_coverage_threshold_space_separated(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "jobs:\n"
        "  t:\n"
        "    steps:\n"
        "      - run: coverage report --fail-under 75\n"
    )
    obs = extract_observations(tmp_path)
    thresholds = [o for o in obs if o.observed_type == "coverage_threshold"]
    assert len(thresholds) == 1
    assert thresholds[0].command == "coverage_threshold=75"
