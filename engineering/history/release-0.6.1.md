# 0.6.1 发布验收

2026-10-13 完成。发行提交 `99d95f9f415d90554654d98b9ed325527d569a0f` 已快进 main，
标签 v0.6.1 指向同一提交，未创建 PR。GitHub、PyPI 和 Pages 均实际发布成功，
公开发行文件和全新安装已核验。本记录在正式发布后创建，不使用标签创建前的草稿代表发布结果。

## 改动与发行整理

- 安装包排除 `engineering/`，保留 sdist 重建和可选原生扩展所需源码；工程记录仍保存在 Git。
  Pages 仅发布 docs 的构建结果，没有工程目录。三个新增回归验证真实构建的排除、必要文件与失败输出。
- 构建验证以 UTF-8 解码子进程 stdout／stderr，并保留非零退出码，避免中文错误被解码失败掩盖。
- CHANGELOG 和 GitHub Release 当前仅有 0.5.0、0.6.0 和新增 0.6.1。
  删除 0.1.0–0.4.0 Release 前，已下载元数据及全部资产并核验尺寸、可用摘要；
  备份清单位于 `.quality/release-061/retired/backup-manifest.json`。Git 标签、历史提交和 PyPI 文件保留。
- [0.6.0 完整发布验收](https://github.com/DorisLab/DoriBT/releases/download/v0.6.0/release-0.6.0-acceptance.md)
  已补充到原 Release，并公开下载逐字节核验。冻结 v0.6.0 标签和旧 sdist 保留发行前快照，未替换。
- 相对 0.6.0，生产源码仅 `__version__` 改为 0.6.1，交易、规则覆盖、账本和策略执行行为不变。
  本次没有重新测量性能，不宣称新的性能提升。

## 正式标签门禁

[发行工作流 38345521644](https://github.com/DorisLab/DoriBT/actions/runs/38345521644)
最终为 success；七项质量任务、build 和 publish 全部 success。数字来自该运行的实际日志：

| 任务 | 通过 | 跳过 | 明确排除 |
| --- | ---: | ---: | ---: |
| Windows／Python | 621 | 42 | 300 |
| Linux／Python | 621 | 42 | 300 |
| Windows／Numba | 921 | 42 | 0 |
| Linux／Numba | 921 | 42 | 0 |
| Linux 原生记录／Numba | 963 | 0 | 0 |

42 项是纯包环境不运行的原生检查，300 项是基础后端不运行的 Numba 用例；原生任务没有跳过。
Ruff、101 文件 strict mypy、400 行／复杂度门禁、示例、仓库外基础和 Numba／plot wheel 安装均通过。
全部 extras 的锁定依赖在线审计未发现已知漏洞；完整 Git 历史与当前变更的凭据扫描通过。
正式原生任务实际执行 sdist 重建、纯包及原生包隔离安装、RECORD、四类非空 C 调用和 required 失败路径。
正式构建的 wheel 和 sdist 已另行检查，均不含工程文件，sdist 保留原生构建所需 C 源码。

本地阶段及 CI 的范围分别记录：最终 Windows Numba 921 通过；基础阶段 620 通过后，
新 UTF-8 失败测试及其余打包用例定向复验通过；正式标签的两平台基础任务则各为 621 通过。
Linux 本地还完成定向原生打包，不把复用的 0.6.0 数值门禁称为新的 0.6.1 全量运行。
最终 CI 汇总 `.quality/release-061/ci-verification.json` SHA-256 为
`698260a82a7986e35500a746e1e20a2ccb6a0cd35f6dfa038e5a39b130d89cbc`。

## GitHub、PyPI 和线上手册

- [PyPI 0.6.1](https://pypi.org/project/doribt/0.6.1/) 已公开。GitHub `pypi` deployment
  `7029960656` 对应 v0.6.1／发行提交，最终状态为 success，时间为 2026-10-13 04:20:27 UTC。
  [上传任务](https://github.com/DorisLab/DoriBT/actions/runs/38345521644/job/115127214832) 同为 success。
  0.6.0 的 canceled 历史保留，本次没有以文件存在替代完整上传流程成功。
- [GitHub Release v0.6.1](https://github.com/DorisLab/DoriBT/releases/tag/v0.6.1) 由 DorisLab 正式发布，
  非 draft／prerelease，当前为 Latest。wheel、sdist、SHA256SUMS 已通过无需登录的公开下载，
  与 CI 原件逐字节相等；两个 PyPI 文件也与 CI 原件、公开摘要和 SHA256SUMS 相符。
- [手册工作流 38346044330](https://github.com/DorisLab/DoriBT/actions/runs/38346044330) 的 build／deploy
  均 success，严格构建、站内链接、API、中文索引与仓库外教程通过。
  [线上分钟教程](https://dorislab.github.io/DoriBT/guide/minutes.html) 实际显示 DoriBT 0.6.1，
  浏览器可见日期化覆盖与四种做 T 对照；中文“规则覆盖”搜索返回三页。
  教程下载的 intraday_t.py 与正式 sdist 内示例逐字节相同，SHA-256 为
  `0ccf4e6ac2bcbecec153698db1fdd4a6ceac08f90c50f3700f5dc6d35b6907fc`。
  本次没有将实际剪贴板内容核验标为通过。

| 资产 | SHA-256 |
| --- | --- |
| doribt-0.6.1-py3-none-any.whl | 04f1e62c643c9b1b31a8ba125eb76a4110838820bb2f4c9f00b393f02dffd092 |
| doribt-0.6.1.tar.gz | 3c51b48af613500d56bacadb18817f30f88dbfa240d543e1df6513ecbd4f304b |
| SHA256SUMS | 5a2b037b887644cdce63ce1b3286bfb0aad7228b64802f7c43e6936111f816f5 |

## 公开安装与策略验收

Windows 使用 CPython 3.13.12，从官方 PyPI 无缓存建立两个全新环境。基础安装不含 Numba／Matplotlib；
基础和 Numba／plot 环境各验证八个 1／5 分钟做 T 情况，版本、真实安装路径与正式 wheel 包文件相符。
Numba 环境执行线上下载示例，期末权益整数为 1003838800，导出日频报告和 PNG（60342 字节），
16 个 manifest 条目的 SHA-256／尺寸全部读回相符，PNG 签名通过。
证据位于 `.quality/release-061/public-*-acceptance.log` 及 `windows-public-report/`。

Linux 使用 CPython 3.13.14，从官方 PyPI 无缓存建立全新 Numba／plot 环境；75 个包文件逐字节匹配正式 wheel。
七个冻结示例与发行提交 Git blob 字节相同。历史费率断点、证券／日期覆盖、16 个 1／5 分钟做 T、
六个日线预计算场景、两后端分钟预计算、公司行动和 quickstart 均通过；两后端结果除 backend／run_info
外的全部公开字段相等。五份报告共 81 个文件，76 个 manifest 条目的摘要／尺寸通过；
两幅 PNG 的签名、46830／147392 字节尺寸通过。报告从 Linux 原生 `/tmp` 文件系统导出，
复制回工作区后逐字节核验，证据位于 `.quality/public-061-linux/`。
其 `acceptance.json` SHA-256 为 `8462e017889dcee94568407b99093fefa17c227856ce7e7a10036efb0f4b8ec9`。

两平台公开安装均解析到 NumPy 2.5.4、Numba 0.68.0、llvmlite 0.50.0、Matplotlib 3.11.2；
与门禁锁定的 NumPy 2.5.3 分别记录。WSL DrvFS 的原子发布限制沿用 0.6.0 手册说明，
本次没有用可覆盖操作替代原子不覆盖契约，也没有重测该已确认的失败分支。
