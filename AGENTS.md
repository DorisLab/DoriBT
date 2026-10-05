# DoriBT development

Read README.md, docs/roadmap.md, docs/api-design.md and docs/quality.md before changes.
Keep implementation status distinct from release targets. The first release requires
the complete baseline engine in the roadmap, not only the experimental simulator.

- Implement one coherent objective at a time; review public API usage with a runnable example.
- Python files in src, tests, examples and scripts must be at most 400 physical lines.
- Every function must satisfy Ruff C901 complexity <= 10. Split by responsibility;
  do not hide branches in clever expressions or add blanket exclusions.
- Before committing, run the local quality entry for affected backends. Run targeted
  checks during iteration and the full local gate on the final change.
- Commit completed main objectives with a concise Chinese Conventional Commit.
- Only milestone or release tags trigger CI; ordinary pushes and PR updates do not.
- Use codex/ branches and PRs. Preserve dedicated repository author identity DorisLab;
  check author, committer and SSH destination before any push.
- Do not publish private consumer code, credentials or unlicensed datasets.
- Update docs/release-progress.md with evidence, unresolved requirements and the next objective.
