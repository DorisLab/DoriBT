# 0.1.0 范围与验收索引

0.1.0 已于 2026-10-06 发布，可从本地数据完成策略编写、回测、解释成交、比较指标和导出复现记录。本文将[路线图](roadmap.md)要求对应到实现和可复核证据；最终标签 [CI 37390685059](https://github.com/DorisLab/DoriBT/actions/runs/37390685059) 六个任务全部成功，[GitHub Release](https://github.com/DorisLab/DoriBT/releases/tag/v0.1.0) 已公开。内部历史实施记录不覆盖后续提交的验证。

| 验收要求 | 公共入口与行为 | 证据 |
| --- | --- | --- |
| 数据、时间与来源 | `MarketData.from_records/from_csv`，完整独立日历、状态、原始 OHLC、逐期规则、行动及按时点研究价 | `test_market_data`、`test_rules_actions`、`test_price_adjustments`：缺日／重复／未知状态／无规则失败，改变未来价格或因子不改变过去视图 |
| 策略与参数 | `Backtest.run`＋`Context` 或 `WeightTargets`，买入持有、均线、轮动无需改内核 | `examples/strategies.py`、`examples/research.py`、`test_engine`、`test_provenance`：实参驱动成交、前缀稳定、回调与预计算一致 |
| 意图、执行与订单 | 收盘固定股数、次日开盘、替换／撤销／到期、停牌／限价方向／资金不足、费用滑点 | `test_execution_edges`、`test_order_quantities`、`test_engine_reference`：手算与独立 Decimal 核对，未知／溢出失败 |
| 账户与组合 | 多标的共享现金、先卖后买、确定顺序、批次解锁、重复参数账户隔离 | `test_engine_reference`、`test_repeated_runs`：逐日现金／持仓／权益精确核对，复跑不污染已有结果；即时成交模型没有跨日冻结订单 |
| 规则与权益 | `china_rules`、公司行动、股息税；数量／费率按有效日期变化 | `test_china_rules`、`test_published_action`、`test_corporate_reference` 等：规则断点、真实发行人分配事实＋人工行情、独立权益账本 |
| 分析与交付 | `stats/plot/export`、精确账本及来源清单、基础安装与可选 extras | `test_analysis`、`test_export`、`test_provenance`、仓库外 `check_wheel`：手算指标、从文件重建账户、失败／竞争不覆盖、实际 PNG／哈希核对 |
| 市场案例与性能 | 真实 ETF 独立参考、完整策略耗时和资源占用 | [市场验收](market-validation.md)、[性能基线](performance.md)，公开工具不携带行情；两后端结果一致不代替独立账本 |

## 使用范围

Python 3.13；Windows 与 Linux。引擎仅依赖 NumPy，Numba 和 Matplotlib 分别为可选执行与绘图依赖。锁文件用于可复现开发和验收，wheel 元数据声明兼容区间；并不代表区间内所有版本都已逐一验证。

普通股票／境内股票 ETF 的预设历史范围为 2020–2025，特殊市场状态和未覆盖证券不得直接套用普通分类。普通个人股息税有独立的身份、日期及分配条件。日线开盘模拟不还原盘口排队、流动性冲击或券商盘中扣款。逐项限制见[市场矩阵](china-market.md)、[权益模型](corporate-actions.md)和[执行模型](execution-model.md)。

基础策略、组合、权益和分析已打通；并行参数优化、更多周期／市场、第三方策略适配器仍是后续候选，不纳入本版完成范围。用户必须提供合法可用的数据和规则事实，回测结果不是投资建议或真实交易授权。

## 发布检查与产物

1. 最终候选运行本地 `scripts/check.py` 的基础及 Numba 入口，核对格式、类型、400 行／复杂度 10、行为测试、示例、构建及仓库外安装；联网运行全部 extras 的锁定依赖审计。
2. 核对版本元数据、作者／提交者、专用 SSH 和 GitHub API 身份；暂存凭据扫描通过后，以 `codex/` 分支和 PR 合入。
3. 在最终提交创建 `v0.1.0`，只由此发布里程碑运行 Windows／Linux × Python／Numba、依赖审计和完整历史凭据扫描。全部成功后才发布 Release，失败不得借用较早里程碑的绿灯。
4. 从标签对应的干净源码构建 wheel 和 sdist；检查包内文件属于公开仓库且无真实行情／私有消费者文件，两种仓库外 wheel 安装通过；确认 sdist 可重建同一引擎源码。
5. Release 交付 wheel、sdist、`SHA256SUMS`、变更与范围说明，GitHub 提供标签源码归档。下载已上传资产重新验哈希并检查实际安装，记录准确提交和 CI 链接。

这次不向 PyPI 上传，不提供质量或支持时限承诺。已完成的具体证据与公开范围保留，不能以免责声明代替失败检查。

## 最终发行记录

发布标签 `v0.1.0` 固定在提交 `1b719cbff938ef6d1ac50a56d5184ec97af698b3`，Release 作者为 DorisLab，发布时间为 2026-10-06 07:53:08（Asia/Shanghai）。PR #10 完成性能目标，PR #11 完成最终候选；普通 PR 没有触发 CI，发布标签触发上述最终跨平台运行。

本地最终门禁为完整 317 项、基础 254 项。最终六项 CI 覆盖 Windows／Linux 的两种后端、锁定运行依赖审计和完整历史凭据扫描；每种安装包均在仓库外执行。源码包的 100 个文件与公开仓库逐项核对，wheel 引擎源码一致；sdist 重建 wheel 字节完全相同。上传后下载资产验哈希，基础及 Numba＋plot 安装再次通过；发布后使用无登录的公开地址下载，三个文件均与验证产物逐字节一致。

| 资产 | 字节 | SHA-256 |
| --- | ---: | --- |
| `doribt-0.1.0-py3-none-any.whl` | 58208 | `16baa1325e8565c070403eea2aa95f645033426f9ffd6478e4633f9ceaf10c0b` |
| `doribt-0.1.0.tar.gz` | 165107 | `9d7aaedf81c677682eebc74f66823aa00d7278924592c2afd750541781f0eb55` |
| `SHA256SUMS` | 184 | `f2100d90b72f283413e6c5e7aefe27585a8ef8c2b3eec8e4931074638d58dee8` |

后续源码修改需新的检查与版本；本页的发行后记录不改变标签固定的源码和产物。
