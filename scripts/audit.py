"""Audit the lockfile's distributable dependencies, including all extras."""

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="doribt-audit-") as temporary:
        requirements = Path(temporary) / "requirements.txt"
        subprocess.run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--all-extras",
                "--no-emit-project",
                "--output-file",
                str(requirements),
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "pip-audit",
                "--strict",
                "--disable-pip",
                "--require-hashes",
                "-r",
                str(requirements),
            ],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    main()
