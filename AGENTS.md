# DoriBT development

Read README.md, docs/roadmap.md, docs/api-design.md and docs/quality.md before changes.
Keep current capabilities, future plans and historical evidence distinct.
User documentation lives in docs; development records live in engineering.

- Implement one coherent objective at a time; review public API usage with a runnable example.
- 图表文案、项目自有日志及新增或修改的代码注释优先使用中文；保留 API 名称、
  标识符和常用指标缩写。不翻译第三方工具输出或改写用户自定义标签。
- Python files in src, tests, examples and scripts must be at most 400 physical lines.
- Every function must satisfy Ruff C901 complexity <= 10. Split by responsibility;
  do not hide branches in clever expressions or add blanket exclusions.
- Before committing, run the local quality entry for affected backends. Run targeted
  checks during iteration and the full local gate on the final change.
- Commit completed main objectives with a concise Chinese Conventional Commit.
- Only milestone or release tags trigger CI; ordinary pushes and PR updates do not.
- 文档变更运行 scripts/check_docs.py，检查严格构建、站内链接及可执行教程。
- Use codex/ branches and PRs. Preserve dedicated repository author identity DorisLab;
  check author, committer and SSH destination before any push.
- Do not publish private consumer code, credentials or unlicensed datasets.
- Update engineering/release-progress.md with evidence, unresolved requirements and the next objective.
