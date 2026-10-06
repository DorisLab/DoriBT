# 0.2 发布准备

维护者检查表，检查日期：2026-10-06。本文不属于用户手册，也不表示已经发布。

## 当前状态

- GitHub 最新公开版本为 `v0.1.0`；本地为 `0.2.0.dev0`，位于 `codex/minute-execution`。
- 开发版已包含分钟行情、部分成交、滑点、预计算分段执行、运行配置、参数声明、自定义输出及日频报告。
- 图表默认改为策略红、基准灰、回撤绿；分钟横轴保留完整时点和市场时区。验证记录见 [release-progress.md](release-progress.md)。
- 现有 CI 覆盖 Windows／Linux × Python／Numba，以及依赖和凭据检查。远程最新成功运行对应 `v0.1.0`，不能用于证明当前开发版通过。
- 仓库中尚无文档站配置或 Pages 工作流。清除旧终端继承的 token 后确认 GitHub API 身份为 DorisLab，具备仓库管理权限；仓库元数据 `has_pages=false`，尚未启用 Pages。

## 发布前必须完成

| 工作 | 当前缺口 | 完成标准 |
| --- | --- | --- |
| 用户文档 | README 混合已发布包与开发版能力；API／结果文档逐次追加，缺少顺序教程 | 阅读者无需开发讨论背景即可从安装走到导出；每页注明适用版本，示例对应同一版本 |
| 安装后的首次运行 | README 的最小代码导入仓库内 `examples`，wheel 用户不能直接复制运行 | 提供仅依赖公开 `doribt` API 的完整合成数据示例，在仓库外安装候选 wheel 后执行 |
| API 与示例收口 | 旧直接参数和新 `RunConfig` 并存；分钟示例依赖内部 `MinuteClock` | 新教程统一使用 `RunConfig`；旧入口保留兼容说明；用户示例仅使用公开入口，或明确补齐所需公共工具 |
| 统计与执行说明 | 日线旧文案与分钟／日频报告说明混排 | 分清每 bar 的 `stats()` 与日末采样 `report()`、年化基数、首日收益、基准和交易盈亏定义；核对 `RunConfig` 与旧入口的成交默认值 |
| 范围与升级 | 规则预设截止 2025，Python 仅 3.13；源码模块重组及原型移除 | 明确 Windows／Linux、1／5 分钟、规则区间及未覆盖状态；列出从 0.1 升级的导入和行为差异，不能默认宣称支持 2026 规则 |
| 候选验收 | 新能力已有 Windows 本地证据，尚无当前候选的 Linux／远程 CI 证据 | 最终候选的两后端本地门禁、四组合 CI、锁定依赖审计、完整历史凭据扫描通过；补查文档链接、代码示例及构建 |
| 发行产物 | 版本仍为开发版 | 同步版本和 CHANGELOG；从最终标签构建 wheel／sdist，检查包内容、隔离安装与源码包重建，生成 SHA256SUMS，核对实际上传下载的文件 |
| 发布身份 | 本地提交作者／提交者为 DorisLab，SSH 使用 github-dorislab；清除旧终端继承的 token 后，gh API 身份已验证为 DorisLab | 使用已清理环境的进程；PR／Release／Pages 等写操作前复核 API 身份，每次推送核对 Git 署名与 SSH 目的地 |

本轮没有推送、创建标签、发布包或改变仓库设置。发布渠道先沿用 GitHub Releases；PyPI 是独立的后续发行渠道，不是文档站的前提。

## 文档整理方案

README 只保留定位、支持范围、安装与最小示例、手册／示例链接、许可和参与入口。路线图只列当前版本摘要及少量未来方向，已完成的逐项验收转至发行记录。

| 用户手册栏目 | 内容及现有来源 |
| --- | --- |
| 安装与首次回测 | 版本／环境／extras；自包含示例，从人工行情到一次成交和报告 |
| 准备数据 | 日线／分钟输入、日历、证券与状态、规则、原始价与研究价；整合 data-contract、china-market |
| 编写策略 | 回调、可见历史、股数／目标权重、组合调仓和参数；整合 api-design、scheduled-execution 与示例 |
| 配置执行 | RunConfig、佣金／最低佣金、参与率、三类滑点、订单有效期与部分成交；整合 minute-execution |
| 阅读结果 | 标准字段、日频报告、基准、费用与交易分析、绘图和导出；整合 results、research-contract |
| 扩展研究 | ParameterSet、ctx.record、ResearchOutput、analyze／with_outputs；每类给出可运行例子 |
| API 与规则参考 | 公开对象签名、字段／单位／默认值、指标定义、交易规则和权益税务模型；从教程链接深入 |
| 升级与常见问题 | 0.1 到 0.2；未成交原因、时间对齐、复权、最低佣金、Numba 冷启动及支持边界 |

整理时保留每项契约的一处权威定义，教程引用它，不复制一套容易分叉的口径。API 自动提取签名，语义、单位、例子和适用条件仍需人工编写。

开发流水账 `release-progress.md`、阶段验收和原型 `model.md` 不进入文档站构建或搜索；仅从站点导航隐藏并不足够。公开性能页面保留测量环境、输入范围、方法、提交和复现入口，去掉过程对话。原文件移动时一起修复仓库链接和 AGENTS 的导航；历史验收不改写成新版本证据。

## GitHub Pages 方案

使用现有 DoriBT 仓库的项目站，预期地址为 **https://dorislab.github.io/DoriBT/**。不需要另建 `DorisLab.github.io` 仓库、购买域名或运行服务器。该地址是目标地址，尚未作为本轮上线结果验证。

建议采用 **Sphinx + MyST + Furo**：手册继续写 Markdown，用 Sphinx 的 Python API 文档能力提取公开签名，Furo 提供文档导航和搜索界面。文档工具放在独立依赖组，不进入引擎运行依赖。站点目录按教程和参考组织，明确排除维护记录；文档版本从候选包读取。

实施步骤：

1. 整理手册并添加构建配置。严格构建检查告警、内部链接及公开 API 引用，教程中的完整例子在隔离安装环境运行。
2. 本地预览生成的静态站点，检查中文搜索、代码复制、移动布局和 `/DoriBT/` 子路径链接；不能只检查构建命令退出码。
3. 仓库 **Settings → Pages → Build and deployment → Source → GitHub Actions**。
4. 添加独立 Pages 工作流：检出已核验版本 → 安装锁定文档依赖 → 构建 → 上传 Pages artifact → deploy-pages。默认只读权限，部署步骤按需授予 `pages: write`、`id-token: write`，使用 `github-pages` 环境并固定 Action 版本。
5. 初期发布一个与当前稳定 Release 对应的手册。采用明确选择版本的手动部署或正式 Release 发布事件，部署前校验来源标签和对应 CI；不能让任意分支的手动运行覆盖稳定文档。普通提交不触发完整 CI 的现行约定保持不变。
6. 部署后实际检查项目地址、深层页面、搜索及安装示例，再添加 README 和包元数据的 Documentation 链接。后续确有多个受支持版本时再加版本切换。

工作流入库、本地预览与远程启用／部署是不同完成状态。

依据：[GitHub Pages 项目站地址](https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages)、[自定义 Actions 部署](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)、[Sphinx Markdown 支持](https://www.sphinx-doc.org/en/master/usage/markdown.html)、[公开 API 文档提取](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html)、[Furo](https://pradyunsg.me/furo/)。

## 不作为本次发布前提

期货、平台代码适配、参数优化器、更多 Python 版本和新的性能优化均不应挤入本次收尾。性能宣传只使用现有报告已验证的场景，不把稀疏预计算路径的结果推广到逐 bar 回调、密集交易或任意组合。

执行顺序：先整理用户文档与完整教程，再搭建本地文档站，随后冻结候选、补齐发布验收，最后发行产物和部署对应版本手册。
