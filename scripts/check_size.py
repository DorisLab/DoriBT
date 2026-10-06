"""Limit physical Python file size, including blank lines and comments."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def oversized_files(root: Path, maximum: int) -> list[tuple[Path, int]]:
    paths = (
        path
        for folder in ("src", "tests", "examples", "scripts", "benchmarks")
        for path in (root / folder).rglob("*.py")
    )
    measured = ((path, len(path.read_text(encoding="utf-8").splitlines())) for path in paths)
    return [(path, lines) for path, lines in measured if lines > maximum]


def main() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    maximum = config["tool"]["doribt"]["quality"]["max-file-lines"]
    violations = oversized_files(ROOT, maximum)
    for path, lines in violations:
        print(f"{path.relative_to(ROOT)}: {lines} lines exceeds {maximum}")
    if violations:
        raise SystemExit(1)
    print(f"Python file sizes passed (maximum {maximum} physical lines)")


if __name__ == "__main__":
    main()
