# 2026-10-13：A 股轻量回测定位复核

本轮根据维护者要求检索 GitHub 同类项目，并查看官方 README、使用文档、依赖声明和相关源码。以下是定位判断的依据；公开推广页面继续围绕 DoriBT 自身能力展开。

## 判断

**“A 股与 ETF 的轻量高性能回测框架”成立，值得作为项目的主要定位。** 三个支点是交易规则开箱即用、快速重复回放、轻量接入现有 Python 脚本；完整交易账本把研究速度与结果解释连接起来。

有明确的直接竞争者：RQAlpha 已提供中国股票持仓与费用模型，SimTradeLab 已提供轻量本地 A 股回测，AKQuant 已提供 Rust 内核及 T+1／费用配置。由此，宣传应突出 DoriBT 的组合体验和实测效率。单独的“支持 A 股”“使用高性能内核”不足以形成鲜明定位。

DoriBT 的具体识别点：

- 基础安装只依赖 NumPy；普通函数策略与预计算目标共同使用公开接口。
- `china_rules` 按证券分类和历史日期生成规则，股票与不同 ETF 分类分别处理；`RuleOverride` 表达指定证券、指定时期的研究情景。
- 日线与 1／5 分钟都保留账户、目标、订单、成交、权益和税务记录；CSV／JSON 可以直接进入现有研究流程。
- 已有可复现的完整 API 性能对照，能够把“快”落实为具体数字。

目标用户是已有行情、使用 Python、希望在个人电脑或研究脚本中快速完成 A 股择时、ETF 轮动和分钟策略研究的人。

## 检索结果与一手来源

| 项目 | 已确认的公开定位或实现 | 对 DoriBT 定位的意义 |
| --- | --- | --- |
| [vectorbt](https://github.com/polakowo/vectorbt) | [README](https://github.com/polakowo/vectorbt/blob/master/README.md)以矩阵化、多配置研究、Numba／Rust 加速为核心 | 是研究效率的明确参照；速度宣传使用已有同场景实测 |
| [Backtesting.py](https://github.com/kernc/backtesting.py) | [README](https://github.com/kernc/backtesting.py/blob/master/README.md)提供 pip 安装、Strategy 类和通用行情回测入口 | 简单接入已有强竞争；需要用 A 股／ETF 规则和完整组合执行形成识别点 |
| [RQAlpha](https://github.com/ricequant/rqalpha) | [股票持仓源码](https://github.com/ricequant/rqalpha/blob/master/rqalpha/mod/rqalpha_mod_sys_accounts/position_model.py)包含 T+N 可平仓数量、分红与拆分；[费用源码](https://github.com/ricequant/rqalpha/blob/master/rqalpha/mod/rqalpha_mod_sys_transaction_cost/deciders.py)包含累计最低佣金和日期化印花税 | 中国市场及历史费用已经有成熟实现；DoriBT 强调自身轻量接入与实测回放效率 |
| [AKQuant](https://github.com/akfamily/akquant) | [README](https://github.com/akfamily/akquant/blob/main/README.md)提供 Rust＋Python 与 pip 安装；[策略文档](https://github.com/akfamily/akquant/blob/main/docs/zh/guide/strategy.md)提供 T+1、可用持仓、手数、佣金和税费配置 | 是高性能、多资产研究的直接竞争者；DoriBT 的依赖、函数接口与历史分类规则应明确呈现 |
| [Hikyuu](https://github.com/fasiondog/hikyuu) | [README](https://github.com/fasiondog/hikyuu/blob/master/readme.md)提供 C++／Python 研究、策略部件、A 股数据导入与多种存储后端 | 高性能 A 股研究已有选择；DoriBT 专注可嵌入脚本的独立回测包 |
| [WonderTrader](https://github.com/wondertrader/wondertrader) | [README](https://github.com/wondertrader/wondertrader/blob/master/README.md)定位覆盖数据、研发、交易和运营，采用 C++ 内核及 wtpy 接口 | 代表完整交易平台方向；DoriBT 围绕本地研究和回测形成集中体验 |
| [SimTradeLab](https://github.com/kay-ou/SimTradeLab) | [中文 README](https://github.com/kay-ou/SimTradeLab/blob/main/README.zh-CN.md)定位轻量 PTrade 本地 API，提供 A 股规则和交易／税务报告 | “轻量＋A 股规则”已有直接竞争，DoriBT 需要同时讲清独立函数接口与可复现速度 |
| [New Tea Quant](https://github.com/garnet1985/new-tea-quant) | [README](https://github.com/garnet1985/new-tea-quant/blob/master/README.md)面向个人 PC 的 A 股研究，提供四层回测、市场扫描和应用入口 | 同样争取个人研究者；DoriBT 的单包、单脚本研究流程应成为直观入口 |

依赖层面，DoriBT 基础包只有 NumPy；AKQuant 的当前 [pyproject](https://github.com/akfamily/akquant/blob/main/pyproject.toml)还列出 pandas、pyarrow、Plotly、Polars、Pydantic 等，SimTradeLab 的 [pyproject](https://github.com/kay-ou/SimTradeLab/blob/main/pyproject.toml)列出数据、缓存、图表及模型库。这支持明确宣传 DoriBT 的轻量依赖，而不是把“轻量”留作抽象形容词。

## 性能主张的依据

使用已有[公开性能归档](../benchmarks/documentation-20261013/README.md)，原始结果不改动：

- 2520 日 × 100 标的日线组合：DoriBT Numba 0.1470 秒，vectorbt Numba 0.09553 秒，vectorbt Rust 0.07533 秒。前两者耗时比为 1.539，支持该场景“接近向量化速度”的主张。
- `matrix-summary.json` 中共 18 个语义场景，17 个具有主对照耗时。按原始数值计数，DoriBT Numba 在其中 10 个更快；各场景采用归档中对应的 Numba／Rust／自定义回调适配器。
- 100 个独立组合的扫描：DoriBT Numba 19.131 秒，vectorbt Numba 7.677 秒；该工作流的数据也继续保留在性能页。
- 0.6.2 三组真实面板各重复 10 次，累计回放由 63.82 秒降到 40.57 秒，完整账户及交易账本一致。

因此，公开文案使用“预计算回测接近向量化速度”，并在性能正文给出具体场景和数字。现有证据支持清晰的产品定位；“唯一”“所有策略都达到同一速度”等表达超出这些具体事实。

## 展示信息与图标

README、手册首页、“为什么选择 DoriBT”、性能解读、文本导航和开发方向统一这一定位。既有短导航保持；介绍页先展示规则、速度和轻量接入，再解释完整结果。

GitHub 当前 About 为“面向 A 股与 ETF 研究的 Python 回测引擎：历史规则、共享资金、分钟做 T 与可对账报告”，Topics 为 `a-share`、`backtesting`、`etf`、`numba`、`python`、`quantitative-finance`。
候选 About、主页及 10 个 Topics 已保存到 [repository-profile.json](../../.github/repository-profile.json)，包含量化研究、中国股票市场、组合回测和轻量工具等检索入口。本轮沿用维护者的本地确认要求，未写入远程设置。

favicon 采用独立蓝白 BT 字标：并排字母、较粗笔画、切角底形，面向小尺寸辨识重新绘制。
本轮检查结果和提交状态见[推进记录](../release-progress.md)。
