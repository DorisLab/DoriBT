# 发布维护

发行包：[PyPI](https://pypi.org/project/doribt/)。使用手册：[GitHub Pages](https://dorislab.github.io/DoriBT/)。

## 触发规则

| 事件 | 工作流 | 工作内容 |
| --- | --- | --- |
| 普通分支 push、PR | 无 | 本地运行受影响的质量门禁 |
| `milestone/*` 标签，排除 `milestone/docs/*` | `ci.yml` | 跨平台质量检查 |
| `v*` 标签 | `publish.yml` | 复用质量矩阵，通过后构建并发布 PyPI |
| `milestone/docs/*` 标签 | `docs.yml` | 文档构建、教程执行和 Pages 部署 |
| GitHub Release 正式发布 | `docs.yml` | 发布该版本携带的文档工作流和手册 |

发行和文档标签必须指向已合入 main 的提交。已经发布的版本和标签不可覆盖；修正包内容需发布新版本。只有文档变化时，创建新的文档里程碑标签，例如 `milestone/docs/0.2.0-2`。

## 本地检查

```sh
uv sync --locked --group docs --extra numba
uv run --no-sync python scripts/check.py --backend python
uv run --no-sync python scripts/check.py --backend numba
uv run --no-sync python scripts/check_docs.py
```

发布前同步 `pyproject.toml`、包内版本和 `uv.lock`，检查发行说明、安装说明及公开 API 示例。普通文档修改只运行文档门禁；执行契约或示例变化同时验证受影响的后端。

## PyPI

Trusted Publisher 使用以下值，GitHub `pypi` 环境只允许 `v*` 标签：

| 字段 | 值 |
| --- | --- |
| Project name | `doribt` |
| Owner | `DorisLab` |
| Repository | `DoriBT` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

无需 PyPI Token 或密码。工作流在 Windows／Linux × Python／Numba、依赖审计、凭据扫描通过后构建、隔离安装并计算 SHA-256；独立上传 job 使用 OIDC 发布已验证的资产。

发布后从公开 PyPI 安装基础包和可选依赖，执行最小回测与教程，核对 wheel／sdist 的 SHA-256。GitHub Release 附上同一次构建的 wheel、sdist 和 SHA256SUMS，说明当前能力、安装要求和边界，不把内部迭代记录当成用户发行说明。

```sh
python -m pip install doribt
python -m pip install "doribt[numba,plot]"
```

依据：[Trusted Publisher 配置](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)、[通过 OIDC 发布](https://docs.pypi.org/trusted-publishers/using-a-publisher/)。

## GitHub Pages

仓库 Settings → Pages → Source 选择 **GitHub Actions**。站点使用项目路径 `/DoriBT/`，不需要自购域名或额外服务器。

`docs.yml` 构建 Sphinx／MyST／Furo 站点，严格检查链接、API 锚点、中文搜索词条，并在仓库外执行教程；通过后上传 Pages artifact，再由 `github-pages` 环境部署。部署 job 仅有 `pages: write` 和 `id-token: write`，环境允许 `v*` 与 `milestone/docs/*` 标签。

上线后检查首页、深层教程、API、代码复制、下载链接和中文搜索。工程证据在 `engineering/`，不进入站点导航或搜索。
