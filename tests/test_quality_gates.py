"""Verify that maintainability gates actually reject violating source files."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_file_limit_counts_comments_and_blank_lines_and_fails(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    gate = scripts / "check_size.py"
    gate.write_bytes((ROOT / "scripts/check_size.py").read_bytes())
    (tmp_path / "pyproject.toml").write_text(
        "[tool.doribt.quality]\nmax-file-lines = 400\n", encoding="utf-8"
    )
    source = scripts / "too_large.py"
    source.write_text("# comment\n\n" * 200, encoding="utf-8")
    assert subprocess.run([sys.executable, str(gate)], capture_output=True).returncode == 0
    with source.open("a", encoding="utf-8") as stream:
        stream.write("# one extra line\n")
    checked = subprocess.run([sys.executable, str(gate)], capture_output=True, text=True)
    assert checked.returncode == 1
    assert "401 lines exceeds 400" in checked.stdout


def test_complexity_limit_rejects_an_eleventh_decision(tmp_path):
    source = tmp_path / "complex.py"
    source.write_text(
        "def complicated(x):\n"
        + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(10)),
        encoding="utf-8",
    )
    checked = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            str(ROOT / "pyproject.toml"),
            "--select",
            "C901",
            "--output-format",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 1
    findings = json.loads(checked.stdout)
    assert findings[0]["code"] == "C901"
    assert "11 > 10" in findings[0]["message"]
