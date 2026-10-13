# 0.6.2 实现与验收

日期：2026-10-13。0.6.2 已完成正式发行，以下分别记录本地实现、性能证据、发行 CI、
公开安装和手册验收。机器可读结果见 [发行核验摘要](release-0.6.2-verification.json)。

## 需求响应

接受研究侧的合法非活动区间、完整账本、错误时点和公开路径审计要求。
日线 P0 与 1／5 分钟 P1 一并实现，支持 close／execution 与 rebalance 两种选择。
规则定量与申报资格分开，零目标仍保留意图及已有资源的生命周期；不补未来规则或价格，
不修改研究侧冻结标签、策略、容量映射和费用。设计与测试映射见
[编译设计](compiled-inactive-design.md)。

`run_info.execution_plan` 区分完整目标编译、兼容分段和逐 bar 回调，记录请求／实际后端、
JIT 状态及稳定原因码。原 `execution_path` 的执行族含义保持不变。公司行动、任意回调和
自定义目标继续兼容执行；没有部分区间编译，因此不虚构区间计数。本版未加入“要求完整编译”
选项，调用方可断言公开的实际计划；这项可选 P1 诊断并非本次运行的默认失败策略。

## 独立预期与冻结账本

- 六日 A／B 上市样例有独立手算，`examples/inactive_weights.py` 验证部分及全期规则覆盖。
- C01—C12 覆盖混合／单证券、停复牌、退市尾段、旧意图、共享现金、规则变化、零／恒定／频繁目标。
- E01—E05 保留缺规则优先于缺价、持仓估值失败、数据验证、溢出、错误顺序及 close 先全量定量再替换的原子性。
- 普通回调、新 Python 和新 Numba 比较完整数组及 Order／Fill／Intent／TaxLot 的全部字段；
  108 组另与 PyPI 0.6.1 生成的冻结账本逐值相同，不只比较期末净值。
- 1／5 分钟覆盖跨日上市与最后一根声明；20 个固定种子组合规则、状态、费用、滑点和量限。
  原有 PositionTargets 编译、公司行动和资金不变量继续运行。

真实冻结来源 Run `4901814d-d6ec-4afc-b5c4-0575e379270c`：generation 323，1633 日、219 证券、
357627 根 bar，其中适配器标签为 123568 根 unlisted、2001 根 suspended。没有把这些标签
升级成已经核验的真实上市日期。三组原参数全部保留，密集／稀疏目标、QMT golden、完整账本
和正式报告均通过。独立新 Run：

| 安装包 | 全量验证 Run |
| --- | --- |
| PyPI 0.6.1 | `66f85991-e671-473f-8471-e98cb8036720` |
| 非 editable 0.6.2 候选 wheel | `1d3da829-bda0-49c7-bb61-858b0b489e37` |

每次 Run 保存唯一请求／有效参数、输入与目标标识、源码及 dirty 快照、依赖、完整压缩账本、
公开计划和检查记录。三组新 Numba 均为 `compiled_targets`。私有消费者脚本和行情仅留本机，
公开仓库保留人工例子、标识和汇总证据。

## Python 与依赖实测

Windows 11 10.0.26300 和 WSL2 Ubuntu 24.04，x86_64、常规 GIL CPython；各版本独立环境。
新版依赖统一 NumPy 2.5.4、Numba 0.68.0、llvmlite 0.50.0、Matplotlib 3.11.2。

| Python | Windows 完整门禁 | WSL2 完整门禁 | WSL2 强制原生 |
| --- | --- | --- | --- |
| 3.13.16 | 1115 通过、42 跳过 | 1115 通过、42 跳过 | 1157 通过、零跳过 |
| 3.14.8 | 1115 通过、42 跳过 | 1115 通过、42 跳过 | 1157 通过、零跳过 |
| 3.15.0 | 1115 通过、42 跳过 | 1115 通过、42 跳过 | 1157 通过、零跳过 |

42 项仅为纯包不启用的原生协议检查，不能据此声称原生通过。三个 WSL2 原生环境另完成
sdist 重建、基础／原生 wheel 隔离安装和 required 失败路径。Windows 各环境实际执行基础
及 Numba／plot wheel；新能力不依赖可编辑安装。原生仍仅为 Linux x86_64 可选源码构建，
正式发行继续提供纯 Python wheel。

旧依赖保留：两系统均验证 Python 3.13.16＋NumPy 2.1.3／Numba 0.61.2，及
Python 3.14.8＋NumPy 2.3.5／Numba 0.63.1；每组完整引擎 1115 通过、42 原生跳过。
Windows 旧 3.13 首轮测试环境少装 Ruff，导致质量工具反例用例失败；补装后最终 wheel 的完整测试通过，
未修改或删除断言。新旧依赖分别进入发行 CI，防止只测最新版。

包按解释器声明 NumPy／Numba 下限，llvmlite 由 Numba 配对选择。基础包仍只依赖 NumPy，
不要求旧环境升级所有依赖。支持范围不包括 free-threaded、PyPy 和 Python 3.16。
版本依据：[Python 3.15.0](https://www.python.org/downloads/release/python-3150/)、
[Numba 0.68](https://numba.readthedocs.io/en/latest/release/0.68.0-notes.html)、
[NumPy 2.5.2](https://numpy.org/devdocs/release/2.5.2-notes.html)。

## 性能与版本建议

本机性能测试 wheel 的实际源码摘要为 `aecdfb8f6f350eadcc78788db2d83d43d3c0a3cb7aef56933fe49eabe4023471`。
真实冻结面板的三组完整 Numba 适配器回放暖态中位数从 2.561／1.872／1.846 秒降到
1.270／1.451／1.304 秒；三组各 10 次合计从 63.82 秒降到 40.57 秒。新版 Backtest.run
本身为 0.393／0.464／0.447 秒，包含约 12—16 毫秒内核和完整记录物化。
市场准备仍约 8—9 秒，不能把回放加速倍数推广到一次完整研究流程。空缓存首次 Numba 回放
旧 12.72、新 18.24 秒；有磁盘缓存的新进程旧 9.67、新 3.80 秒。峰值进程树 RSS
旧约 941 MiB、新约 963 MiB，覆盖完整验证进程。

Python 3.13.16／3.14.8／3.15.0 在同一人工面板的 Numba 中位数为 0.568／0.507／0.460 秒，
完整账本哈希均为 `8d0c82e71815291832d2cbd987b570d9ce0e9ce4ca7a301296b6d4f652bd442d`。
建议新的 DoriBT 环境使用 3.15.0、NumPy 2.5.4、Numba 0.68.0、llvmlite 0.50.0；
现有研究主环境保留冻结解释器也受支持，不把 DoriBT 验证扩大为全部消费者依赖兼容。

原始轮次、p10／p90、30 次总耗时、线程、环境、峰值 RSS、六组规模／上市分布测量及本地测试
日志摘要见[本次证据](../benchmarks/release-0.6.2/README.md)。第一轮候选揭示了准备成本，
随后增加批量规则准备；初轮 Run 和人工测量保留在本机，不冒充最终源码成绩。

## 文案与 NEXT_STEPS

先接收推广包的文档、教程与既有性能材料，提交 `2c652cb`；随后在 0.6.2 中统一安装要求、
实际执行计划和当前能力。原始性能数字、输入、计时边界及复现资产原样保留，没有改版本标签
冒充重测。本次新测量独立归档。三个教程、README 代码、内部链接和 API 均由文档门禁执行／检查。

手册首页按研究任务组织，安装页提供依赖与解释器建议，FAQ 解释 Numba 未加速的排查入口。
新增自绘 DL 风格 SVG favicon，并实际查看本地首页及图标。PyPI 定位与关键词随发行更新；
GitHub About、手册地址和六个 Topics 已更新并读回核验；线上页面在正式部署后核验。

NEXT_STEPS 中的 sitemap、robots 和搜索站长提交属可选建议，本次不新增：现有静态页面和
明确导航已可访问，额外站长提交需要具体站点账户与目标。`llms.txt` 是文本索引，不承诺排名
或 AI 收录。工程记录不进入 wheel／sdist 或 Pages。

性能 wheel 与首次发行提交的 75 个 Python／C 文件核对一致，差异仅为 4 个 Python 文件的 CRLF／LF，
这些文件另经 AST 等价核对。随后 CI 修复只调整 `execution_audit.py` 的可选依赖类型声明：
以 Protocol／cast 描述 Numba 动态配置属性，计算、数据准备和记录代码未变。原性能记录保留
测量时的源码摘要，不能当作最终发行包的字节摘要。文件差异见 source-equivalence.json；
正式包另核对发行提交及公开资产摘要。

本地最终质量入口：Python 636 通过、42 原生跳过、479 Numba 用例明确排除；
Numba 1115 通过、42 原生跳过。Ruff、104 文件 strict mypy、400 行／复杂度、示例、
两种隔离 wheel、两后端文档教程与锁定依赖联网审计均通过。Actionlint、Git 历史及待提交
内容 Gitleaks 扫描通过，未发现泄漏。

## 首次发行 CI 的失败与修复

首次标签对应提交 `29eb2aadfb842f133c591c561adfa60428b365bd`，
[工作流 38359791922](https://github.com/DorisLab/DoriBT/actions/runs/38359791922)
的 6 个基础后端任务因 mypy `unused-ignore` 失败；其余 15 个质量任务通过，构建与发布跳过。
原因是没有安装 Numba 时，其配置模块的类型退化为 Any，原来的属性忽略声明变成多余。
此前隔离基础 wheel 验证覆盖了运行时，但本地基础开发门禁仍使用装有 Numba 的环境，
没有覆盖这一静态检查差异。此次增加真正不安装 Numba 的独立开发环境，修复类型边界，
不放宽检查、不跳过失败用例。Windows 11 和 WSL2 Ubuntu 的 CPython 3.15.0 独立无 Numba
环境均通过完整基础门禁（636 通过、42 原生跳过、479 Numba 用例明确排除）；Windows
Numba 环境再次通过完整门禁（1115 通过、42 原生跳过）。日志摘要另存 ci-fix-local-checks.json。

修复通过 [PR #27](https://github.com/DorisLab/DoriBT/pull/27) 合入，最终发行提交为
`5f0de8701610eb581cc269729f547514b39487c7`。维护者在本次会话明确批准修复尚未完成发行的
`v0.6.2` 标签；核实 PyPI 0.6.2 和 GitHub Release 均不存在后，以旧标签对象
`d2d12b76b82aa3f34357414318944f45aa9afd53` 为精确 force-with-lease 条件更新。
旧提交及失败工作流继续保留。此例外不授权覆盖已发布包，也不改变后续版本的不可覆盖规则。
新标签对象为 `270360bc238b746b45007bfafac2e165defa8875`。

## 正式发行与资产

[发行工作流 38366193173](https://github.com/DorisLab/DoriBT/actions/runs/38366193173)
的 21 项质量任务、build 和 publish 共 23 项全部 success。逐任务日志中的测试结果如下：

| CI 范围 | 任务数 | 每任务通过／跳过／明确排除 |
| --- | ---: | --- |
| Windows／Linux × Python 3.13／3.14／3.15，基础后端 | 6 | 636／42／479 |
| 同一平台及解释器矩阵，Numba 后端 | 6 | 1115／42／0 |
| Linux 原生记录 × 三代解释器 | 3 | 1157／0／0 |
| Windows／Linux × 两组旧依赖 | 4 | 1115／42／0 |

另外两项为联网依赖审计和 Git 历史凭据扫描，均通过。跳过和排除范围与本地门禁相同，
不能将基础环境的排除项说成已运行。正式构建另验证基础及 Numba／plot wheel 隔离安装。

PyPI `pypi` deployment `7033289287` 对应发行提交和 v0.6.2，最终为 success，
时间为 2026-10-13 08:05:02 UTC（北京时间 16:05:02）；上传 job 同样 success。
[PyPI 0.6.2](https://pypi.org/project/doribt/0.6.2/) 与
[GitHub Release](https://github.com/DorisLab/DoriBT/releases/tag/v0.6.2) 均已公开，Release 为正式 Latest。
CI 原件、公开 PyPI 文件、免登录 GitHub 下载的字节完全一致：

| 资产 | SHA-256 |
| --- | --- |
| doribt-0.6.2-py3-none-any.whl | c1d6e8a304c6451a714eb451ee42978ba5f871f193fc0bb93eeadaf22b69075c |
| doribt-0.6.2.tar.gz | fd3a22dc4177ecadaf387685b50bf417da3a9498e72426aaa4ab4a3cc54cad25 |
| SHA256SUMS | 3335cd05ebebce6866cce05e27d59e81875eeeef505b36f97fb25cb2676ca93d |

wheel 与 sdist 中的 75 个 Python／C 源码文件均与发行提交的 Git blob 逐字节一致；工程记录
不进入这两种发行包。正式包实际引擎摘要为
`b68a52bf01f8ff097e9244b0ec38d2b3a8735d7f55e6737c907ef9583ed8aa9f`，与上文性能候选摘要分别保留。

## 公开安装验收

直接从官方 PyPI 索引、禁用下载缓存建立三个全新环境：Windows 11／Python 3.13.16 基础包，
Windows 11／Python 3.15.0 Numba＋plot，WSL2 Ubuntu 24.04／Python 3.15.0 Numba＋plot。
基础安装只有 NumPy 2.5.4；两套完整安装均为 NumPy 2.5.4、Numba 0.68.0、llvmlite 0.50.0、
Matplotlib 3.11.2。76 个安装包文件（含类型标记）均与正式 wheel 一致，无 editable 或本地 wheel 替代。

基础环境完成 8 组非活动权重及 8 组分钟做 T；两套完整环境各完成两后端共 16 组非活动权重、
16 组分钟做 T，比较完整公开结果字段，并验证 Numba 实际计划为完整目标编译。
非活动面板覆盖两种规则覆盖、close／execution、rebalance 两种设置，成交和权益另与手算预期核对。
三个环境另运行 quickstart 和分钟预计算示例；公开 Windows Numba 安装执行全部手册教程及正文片段。

三个环境共导出 6 份报告，91 个 manifest 条目的字节数与 SHA-256 读回一致，4 幅 PNG 的签名通过。
WSL 报告在 Linux 原生文件系统导出。原日志和完整报告保留于本机 `.quality/release-062/`，
WSL 的 `.quality/public-062-full-2/`；机器可读摘要保存每套验收文件的哈希。

PyPI 上传刚完成时，版本 JSON 和文件已经公开，但 simple 索引尚未列出 0.6.2，三个首次安装
均明确失败。保留这些环境及日志；确认公开索引已出现版本后重新创建环境，才得到以上成功结论。
未使用文件直链代替公开索引安装。

## 线上手册与最终文档维护

GitHub Release 触发的 [手册工作流 38367080848](https://github.com/DorisLab/DoriBT/actions/runs/38367080848)
构建和部署均成功。随后线上实操发现搜索“非活动”没有结果，中文分词字典未保留这一完整词。
通过 [PR #28](https://github.com/DorisLab/DoriBT/pull/28) 补充“非活动”“完整编译”“执行计划”，
并扩展索引门禁；严格构建、公开 Numba 安装运行全部教程及完整基础质量入口通过。

新文档标签 `milestone/docs/0.6.2-1` 指向已合入的
`5f01d72e08840e65908da2b567304f84d78aea9c`。
[文档工作流 38367673739](https://github.com/DorisLab/DoriBT/actions/runs/38367673739)
build／deploy 均 success，`github-pages` deployment `7033441725` 成功。
该更新只修正文档搜索，不覆盖已发布的 v0.6.2 或安装包。

线上首页、安装、框架比较、性能、三篇实战教程、预计算说明均显示 0.6.2；
`llms.txt` 和 favicon 与发行源码逐字节一致。浏览器实际查看首页和 DL 图标，确认首页的任务入口
与手册版本可见。favicon 摘要为 `40b5901726a569266913878f71135db64afcf8edb6196f4c1832ad2582167753`。
新索引上线后，浏览器仍暂存旧资源；确认服务器的 `max-age=600` 缓存策略并等待更新后，
线上“非活动”搜索实际返回性能页、示例页、预计算执行页，共 3 页。未把索引构建成功替代浏览器验收。

本记录作为 main 上的完成记录，并以 `release-0.6.2-acceptance.md` 附于 GitHub Release；
机器可读摘要以同名版本的 verification.json 附件提供。发行标签中的发布前记录保持原样。
