# 分钟执行性能协议

这是开发验证工具，不是 DoriBT 运行依赖。vectorbt 适配器只调用 vectorbt 的订单、共享状态和估值 API；不调用 DoriBT 的 broker、金额计算或撮合内核。

准备 Python 3.13 的单独环境，安装当前 DoriBT 源码与 vectorbt==0.28.5、NumPy==2.5.3、Numba==0.68.0。环境指向当前源码便于核对内容，不能指向较旧发布 wheel。驱动器使用本仓库 dev 环境的 psutil：

```sh
uv run --no-sync python -m benchmarks.minute.run PRIVATE_SNAPSHOT \
  --python COMPARISON_ENV_PYTHON --output NEW_RESULT_DIRECTORY --batch 10 --repeats 3
```

PRIVATE_SNAPSHOT 含标准 market.csv 和 calendar.csv，字段见 scripts/minute_case.py。必须先通过该脚本与独立 Decimal 对账。工具不读取或下载供应商数据；不可把未授权原始行情提交进仓库。

每个参数账户独立：人民币十万元、单只深市境内股票 ETF、T+1、佣金万三且每个 DAY 订单最低五元、零印花税／过户费、固定一个 tick 不利滑点、成交量参与率 0.1%。只模拟连续竞价，收盘竞价行保留估值。每天 09:45 以截至该时点的分钟均线决定持有 10,000 份或空仓；快线 30、40、…，慢线 240，未满窗口不交易。目标变更撤旧子单，未满足目标跨日生成合法数量的新子单。

统一核对逐 bar 现金、持仓、权益，以及逐笔时间、数量、价格和佣金。DoriBT 整数账本须与 Decimal 精确相等；vectorbt 的浮点现金／权益允许 0.0001 记账单位（即 1e-8 元）计算误差，成交金额／佣金规范化后逐项一致。不是只比较最终收益。

时间区分数据准备、第一次执行（含新缓存 JIT）、预热后重复运行、参数批量。DoriBT 复用同一 Backtest 的已编译行情并串行调用；vectorbt 一次传入 N 列独立资金账户。都包含生成完整现金／持仓／权益曲线与成交表；不包含文件导出、信号计算、Decimal 对账。DoriBT 同时构建订单／意图／来源等更丰富结果，vectorbt 仅保留适配器运行状态和成交表，此额外工作未剥离。

每种引擎新起进程并使用独立空 Numba 缓存。RSS 每 5ms 采样进程树，范围包含共同数据载入、依赖导入、预热、保留的参数组输出和账本核对，不能称为撮合内核自身内存。worker_wall 包含全部验证及导入，不能当成单次冷启动；first_run 不含 import 和输入解析。原始 JSON 保存所有样本、输入／适配器哈希、版本及账本摘要。速度排名仅适用于这个有限协议，不代表 vectorbt 原生提供了完整 A 股生命周期。
