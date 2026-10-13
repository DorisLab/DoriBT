# 2026-10-13 文档逐份审阅

基于 `27641a8f33c7e7208a368fe17c432563f48f2132`，逐份审阅原有 **57 份**受 Git 跟踪的 Markdown／文本文件。公开页面围绕读者任务与 DoriBT 的研究价值改写；工程文档按其维护、复现和历史记录用途核对。

本轮同时将手册栏标题恢复为 `DoriBT 0.6.2 文档`，采用短导航，并将 favicon 绘制为与 Dorislab DL 同结构、同色的 BT。页面 URL 保持现有入口。

## 逐份结果

| 文件 | 处理 | 审阅结论 |
| --- | --- | --- |
| [AGENTS.md](../../AGENTS.md) | 保留 | 开发约定与门禁适用范围清晰，保留维护用途。 |
| [CHANGELOG.md](../../CHANGELOG.md) | 修订 | 将 0.6.2 的“框架选型”改为“项目介绍”，发行与能力事实保持原样。 |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | 修订 | 删去响应承诺的防御性尾句，保留贡献流程与实际检查要求。 |
| [README.md](../../README.md) | 修订 | 按研究价值、可运行入门、实战和性能组织；明确选择 DoriBT 的理由。 |
| [benchmarks/minute/README.md](../../benchmarks/minute/README.md) | 保留 | 复现命令、输出与采样说明服务于运行基准，保留技术信息。 |
| [docs/api-design.md](../../docs/api-design.md) | 修订 | 保留接口职责和契约，精简内部状态对象的实现说明。 |
| [docs/api.md](../../docs/api.md) | 修订 | 开头改为公开 API 的使用入口，保留签名、参数与成交语义。 |
| [docs/china-market.md](../../docs/china-market.md) | 修订 | 短标题；删去重复提醒，保留日期、分类、来源和覆盖规则。 |
| [docs/comparison.md](../../docs/comparison.md) | 修订 | 重写为“为什么选择 DoriBT”，用自身能力与研究任务说明价值。 |
| [docs/corporate-actions.md](../../docs/corporate-actions.md) | 修订 | 按输入、账户处理、结果和依据排列；删去面向开发者的验收提醒。 |
| [docs/data-contract.md](../../docs/data-contract.md) | 修订 | 短标题与直接表述；保留行情字段、时点、公司行动和指纹契约。 |
| [docs/examples.md](../../docs/examples.md) | 修订 | 短标题；直达命令和用途，保留全部现有示例入口。 |
| [docs/execution-model.md](../../docs/execution-model.md) | 修订 | 短标题；精简重复尾句，保留下单、定量、共享资金和成本规则。 |
| [docs/faq.md](../../docs/faq.md) | 修订 | 短标题；以故障原因与解决步骤回答，迁移问题改为通用操作。 |
| [docs/guide/data.md](../../docs/guide/data.md) | 修订 | 短标题；精简格式提醒，保留可运行 CSV 接入与单位说明。 |
| [docs/guide/extensions.md](../../docs/guide/extensions.md) | 修订 | 短标题；直接介绍自定义指标、曲线和表格。 |
| [docs/guide/install.md](../../docs/guide/install.md) | 修订 | 突出安装、Python 推荐版本和新旧依赖组合，删除环境升级自我提醒。 |
| [docs/guide/minutes.md](../../docs/guide/minutes.md) | 修订 | 短标题；用时点与成交操作解释分钟回测。 |
| [docs/guide/parameters.md](../../docs/guide/parameters.md) | 修订 | 短标题；保留配置、参数声明与实际传入的用法。 |
| [docs/guide/quickstart.md](../../docs/guide/quickstart.md) | 修订 | 短标题；保留三日算例和对 10895 元的逐项解释。 |
| [docs/guide/reports.md](../../docs/guide/reports.md) | 修订 | 短标题；删去免责式段落，突出分析与导出操作。 |
| [docs/guide/strategies.md](../../docs/guide/strategies.md) | 修订 | 短标题；精简重复提醒，保留窗口、目标、资金与取整算例。 |
| [docs/index.md](../../docs/index.md) | 修订 | 重写首页价值与任务入口；导航使用单行短名称。 |
| [docs/llms.txt](../../docs/llms.txt) | 修订 | 与短导航同步，直接介绍用途和页面，删去无价值的尾句。 |
| [docs/minute-execution.md](../../docs/minute-execution.md) | 修订 | 短标题；保留部分成交、有效期、滑点与冻结规则。 |
| [docs/native-records.md](../../docs/native-records.md) | 修订 | 短标题；先讲使用价值，再给构建步骤，压缩底层物化和验收细节。 |
| [docs/performance.md](../../docs/performance.md) | 修订 | 先给数据与选择理由；保留 17 场景和核心数值，完整结果仍在归档。 |
| [docs/quality.md](../../docs/quality.md) | 保留 | 开发者门禁文档的受众明确，命令、失败语义和检查范围保持原样。 |
| [docs/research-contract.md](../../docs/research-contract.md) | 修订 | 短标题；删去内部模块与验收小节，保留参数、指标与输出契约。 |
| [docs/results.md](../../docs/results.md) | 修订 | 短标题；简化图表与导出说明，保留统计定义、单位、文件和实际错误处理。 |
| [docs/roadmap.md](../../docs/roadmap.md) | 修订 | 现有能力与后续方向分开，精简排期提醒。 |
| [docs/scheduled-execution.md](../../docs/scheduled-execution.md) | 修订 | 改为预计算目标的用法、适用路径、执行计划与缓存，删去内核实现细节。 |
| [docs/search-terms.txt](../../docs/search-terms.txt) | 保留 | 中文/API 分词词典覆盖现有研究任务与编译术语，保留词条。 |
| [docs/tutorials/data-to-report.md](../../docs/tutorials/data-to-report.md) | 修订 | 短标题；围绕数据、研究和报告组织说明，删去指纹免责及重复提醒。 |
| [docs/tutorials/etf-rotation.md](../../docs/tutorials/etf-rotation.md) | 修订 | 短标题；突出动量、共享账户和解释换仓，删去策略收益的免责段落。 |
| [docs/tutorials/intraday-t.md](../../docs/tutorials/intraday-t.md) | 修订 | 短标题；突出 T+0/T+1 与底仓差异，删去推广无关的提醒。 |
| [engineering/README.md](../README.md) | 保留 | 清楚说明使用文档与工程证据的入口，保持维护导航。 |
| [engineering/benchmarks/documentation-20261013/README.md](../benchmarks/documentation-20261013/README.md) | 保留 | 核对归档身份、复现命令和计时范围；原测量与归档说明保留。 |
| [engineering/benchmarks/release-0.6.2/README.md](../benchmarks/release-0.6.2/README.md) | 保留 | 核对三组回放和 Python 版本数据来源，保留冻结输入与复现步骤。 |
| [engineering/history/compiled-inactive-design.md](compiled-inactive-design.md) | 保留 | 0.6.2 非活动区间设计与验收证据，保留历史事实。 |
| [engineering/history/historical-rules-0.5.0.md](historical-rules-0.5.0.md) | 保留 | 历史规则范围、来源与发布验收记录，保留当时结论。 |
| [engineering/history/market-validation.md](market-validation.md) | 修订 | 保留市场核验事实，修正分派案例所指依据小节的站内锚点。 |
| [engineering/history/minute-performance-optimized.md](minute-performance-optimized.md) | 保留 | 分钟优化的原始结果与比较方法，保留数据和实验说明。 |
| [engineering/history/minute-performance.md](minute-performance.md) | 保留 | 分钟性能原始基线，保留耗时、内存和输出范围。 |
| [engineering/history/minute-validation.md](minute-validation.md) | 保留 | 分钟账本与失败路径验收记录，保留独立预期与实测结果。 |
| [engineering/history/model.md](model.md) | 保留 | 早期模型与实现阶段的记录，保留历史语境。 |
| [engineering/history/performance.md](performance.md) | 保留 | 早期日线性能基线，保留计时边界与原结果。 |
| [engineering/history/release-0.1.0.md](release-0.1.0.md) | 保留 | 早期发行验收，保留对应版本的范围和检查结果。 |
| [engineering/history/release-0.6.0.md](release-0.6.0.md) | 保留 | 0.6.0 发行证据，保留提交、测试和资产事实。 |
| [engineering/history/release-0.6.1.md](release-0.6.1.md) | 保留 | 0.6.1 发行证据，保留发布与外部安装结果。 |
| [engineering/history/release-0.6.2.md](release-0.6.2.md) | 保留 | 0.6.2 已发布的验收记录，保留失败历史、修复与公开安装结果。 |
| [engineering/history/release-preparation.md](release-preparation.md) | 保留 | 早期发布准备记录，保留当时状态与后续步骤。 |
| [engineering/native-records-integration.md](../native-records-integration.md) | 保留 | 原生集成的构建、调用和回归方案，保留维护用途。 |
| [engineering/publishing.md](../publishing.md) | 保留 | 当前发布操作契约，保留 CI、权限与发行步骤。 |
| [engineering/release-progress.md](../release-progress.md) | 修订 | 逐项审阅已有阶段记录；追加本轮文案修订与本地确认状态。 |
| [engineering/runtime-array-rebuild.md](../runtime-array-rebuild.md) | 保留 | 数组运行时重建的工程设计，保留状态与数据契约。 |
| [engineering/runtime-optimization.md](../runtime-optimization.md) | 保留 | 运行时优化方案和验收口径，保留阶段事实。 |

## 验证与确认

- 原始性能 JSON／CSV／ZIP 未修改；性能页全部 17 个场景的数值与原文逐项核对。
- README 与教程的 Python 示例保留；严格文档门禁验证构建、内部链接、中文/API 搜索、示例及教程片段。
- 浏览器查看桌面和窄窗口导航、项目介绍与性能首屏、完整场景展开，以及 BT 图标的 16—160 px 尺寸。
- 完整验收结果在本轮本地提交前记录于[推进记录](../release-progress.md)。本轮仅本地提交，交由维护者逐项确认后决定后续仓库操作。
