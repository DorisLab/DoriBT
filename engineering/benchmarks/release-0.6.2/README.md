# 0.6.2 性能证据

日期：2026-10-13。Windows 11、AMD Ryzen 7 9800X3D、8 个物理核心／16 个逻辑核心，常规 GIL CPython。
NUMBA_NUM_THREADS、OMP_NUM_THREADS、OPENBLAS_NUM_THREADS 均为 1。测量串行执行，
与功能门禁分开；数值结果及完整账本先核对，计时不作为财务正确性的通过阈值。

## 文件与计时边界

- `research-061-*.json` 与 `research-062-*.json`：同一研究侧冻结面板，分别从非 editable
  0.6.1／0.6.2 wheel 运行；Python 3.13.16、NumPy 2.4.4、Numba 0.68.0、llvmlite 0.50.0。
  记录完整账本摘要、实际计划、每轮耗时、分位数、环境和进程树峰值 RSS。
- `cold`：新进程及全新专用 Numba 缓存；`disk`：第二个进程复用前者的磁盘缓存；
  `warm`：同进程先运行一次，再记录 10 次，Python／Numba 顺序逐轮交替。
  首次回放包含各自的初始化，不能命名为纯 JIT 编译耗时。
- 三个研究场景为 30 万元／10%／5bp、3000 万元／5%／5bp、30 万元／10%／5.01bp。
  1633 日 × 219 证券，目标、规则、费用、标签和完整输出不变。`strategy_targets` 为策略目标
  构造；`market_prepare` 为 MarketData 准备；`seconds` 为完整适配器回放，包括目标转换、
  新建 Backtest 的 run、完整记录及消费者输出。`backtest_run_seconds` 是其内含分项。
- 新版完整编译额外分出 `kernel_seconds` 与 `records_and_result_seconds`，后者从内核返回
  计到完整结果构造完毕。它们已经包含在 Backtest.run，不能再次加到总时间上。旧版未使用
  该完整编译入口，相应字段为空，不能把空值当零成本。
- 10 次 × 3 参数的总耗时可由 warm 的各组 `seconds.total` 求和；市场准备、策略目标构造
  另外保留。摘要导出、读取冻结预期及完整账本一致性检查在计时外，每轮仍实际执行。

研究侧源码与行情未获公开再分发授权，因此只发布摘要、输入标识和 Run ID。本机 Run 的
请求、依赖、源码 dirty 快照、验证脚本、原始账本和清单继续保存。0.6.1 基准的首组波动较大，
保留全部原始轮次和 p10／p90，不删除慢轮。此前的 0.6.1 历史三次测量及推广包测量不被此表替代。

## 公开人工复现

`python-31316.json`、`python-3148.json`、`python-3150.json` 分别使用三代解释器，
均为 NumPy 2.5.4、Numba 0.68.0、llvmlite 0.50.0；相同输入与完整账本摘要须一致。
`scale-<证券数>-<比例>.json` 使用 Python 3.13.16，覆盖 10／50／219 证券、252 日及两种上市分布。

```sh
python benchmarks/inactive_panel.py --days 1633 --symbols 219 --inactive 0.7 --repeats 10 --output panel.json
python benchmarks/inactive_panel.py --days 252 --symbols 50 --inactive 0.9 --repeats 10 --output scale.json
```

先在独立环境安装待测 wheel、Numba 与开发用 psutil，并设置上述三个线程变量。
为首次测量指定尚未使用的 NUMBA_CACHE_DIR；输出文件也须不存在。脚本不覆盖现有结果。
`--inactive` 是最晚上市证券的上市前区间占比，各证券上市时点等距分布，**不是整个面板的
非活动行占比**；例如 0.7 大致对应全体 bar 的 35%。这些日期只是人工连续日期，并非交易所日历。

人工计时中的 `seconds` 为新建 Backtest 后的完整 run，包含数值准备、来源及立即创建的完整
结果；MarketData 和目标构造另计。`numeric_prepare_seconds`、`kernel_seconds`、
`records_and_result_seconds` 是内含分项，其余时间包括来源、目标数组及调度。分项仪器只包裹
已选择的函数，计划依据公开 execution_plan；它不改变路径选择。

完整账本摘要排除版本／来源快照和请求后端名称，其他结果字段、记录顺序与整数金额均保留。
RSS 每 20 毫秒采样一次，覆盖进程树，可能漏掉更短的瞬时尖峰；它包括输入准备和一致性验证，
不表示仅内核占用。每个 JSON 保存实际版本与安装源码摘要，不能只改版本文字重复使用旧结果。
