"""End-to-end integration retry fixture test.

Validates the orchestrator-layer scripts through a realistic failure →
identify suspect → simulate fix → re-run → pass cycle. No real subagent
is invoked: we simulate the loop subagent's retry fix with a Python string
replacement on lib_b.sh.

This is the test for v0.11's H8 coverage: the integration retry path that
was never exercised in the v0.9 chrondel stress run.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "integration-retry"
SUSPECT_CLI = [sys.executable, str(ROOT / "scripts" / "integration_suspect.py")]
VERIFY_CLI = [sys.executable, str(ROOT / "scripts" / "verify_iteration_written.py")]


def test_suspect_identifies_lib_b_from_preseeded_failure(tmp_path):
    """integration_suspect.py names lib_b from the pre-seeded failed integration attempt."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    proc = subprocess.run(
        SUSPECT_CLI + [
            "--gate-report", str(project / ".skillgoid" / "integration" / "1.json"),
            "--chunks",      str(project / ".skillgoid" / "chunks.yaml"),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout.strip())
    assert data["suspect_chunk_id"] == "lib_b", (
        f"expected lib_b, got {data['suspect_chunk_id']!r}. evidence: {data.get('evidence')}"
    )
    assert data["confidence"] == "filename-match"


def test_integration_gate_fails_before_fix(tmp_path):
    """integration/check.sh fails when lib_b.sh still contains fn_a_typo."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    proc = subprocess.run(
        ["bash", "integration/check.sh"],
        capture_output=True, text=True, cwd=project,
    )
    assert proc.returncode != 0, "integration/check.sh should fail before the fix"
    assert "fn_a_typo" in proc.stderr or "lib_b.sh" in proc.stderr, (
        f"expected fn_a_typo or lib_b.sh in stderr, got: {proc.stderr!r}"
    )


def test_integration_gate_passes_after_fix(tmp_path):
    """After fixing the typo (simulating loop subagent retry), check.sh passes."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    lib_b = project / "src" / "lib_b.sh"
    lib_b.write_text(lib_b.read_text().replace("fn_a_typo", "fn_a"))

    proc = subprocess.run(
        ["bash", "integration/check.sh"],
        capture_output=True, text=True, cwd=project,
    )
    assert proc.returncode == 0, (
        f"integration/check.sh should pass after fix. stderr: {proc.stderr!r}"
    )


def test_verify_confirms_preseeded_iteration_records(tmp_path):
    """verify_iteration_written.py confirms the pre-seeded lib_a and lib_b records are valid."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    for chunk_id in ("lib_a", "lib_b"):
        proc = subprocess.run(
            VERIFY_CLI + ["--chunk-id", chunk_id,
                          "--skillgoid-dir", str(project / ".skillgoid")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, (
            f"verify failed for {chunk_id}: {proc.stdout.strip()}"
        )
        data = json.loads(proc.stdout.strip())
        assert data["ok"] is True
        assert data["exit_reason"] == "success"


def test_full_retry_cycle(tmp_path):
    """Full orchestrator contract: identify suspect → fix → integration passes."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    # Step 1: Integration failed — run suspect identification on pre-seeded report
    proc = subprocess.run(
        SUSPECT_CLI + [
            "--gate-report", str(project / ".skillgoid" / "integration" / "1.json"),
            "--chunks",      str(project / ".skillgoid" / "chunks.yaml"),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    suspect = json.loads(proc.stdout.strip())
    assert suspect["suspect_chunk_id"] == "lib_b"

    # Step 2: "Loop subagent" fixes the suspect chunk (Python string replace = the fix)
    lib_b = project / "src" / "lib_b.sh"
    lib_b.write_text(lib_b.read_text().replace("fn_a_typo", "fn_a"))

    # Step 3: Re-run integration gate — must pass now
    check = subprocess.run(
        ["bash", "integration/check.sh"],
        capture_output=True, text=True, cwd=project,
    )
    assert check.returncode == 0, (
        f"integration/check.sh must pass after lib_b fix. stderr: {check.stderr!r}"
    )
