# 性能页的公开复现材料

这是 2026-10-13 整理的历史实测归档。测试 DoriBT 安装包的物理身份为 **0.6.0**，
文档更新没有重新测量或重新标记安装包版本。面向用户的解读见[性能页](../../../docs/performance.md)。
所有行情与目标由脚本确定性生成，不含用户账户、真实行情、密钥、环境目录或编译二进制。

## 文件与范围

- [daily-summary.json](daily-summary.json)：日线主场景、10 账户批量、100 组合扫描及安装／分派身份
- [matrix-summary.json](matrix-summary.json)：18 个语义场景，其中 17 个可比主对照与更强替代工作流
- [single-summary.csv](single-summary.csv)、[batch-summary.csv](batch-summary.csv)、[grid-summary.csv](grid-summary.csv)：便于自行分析的表格
- [environment.json](environment.json)、[artifact-provenance.json](artifact-provenance.json)：平台、依赖、PyPI wheel／sdist URL 和 SHA-256、原生构建来源
- [audit-parity.json](audit-parity.json)、[timing-qualification.json](timing-qualification.json)、[saved-economics-verification.json](saved-economics-verification.json)：36 份完整审计回归、58 行计时资格和 56 份末轮经济核验记录
- [source-results.zip](source-results.zip)：原始合成基准源码、依赖清单、114 份原始运行 JSON、4 份安装／分派证明，以及便携执行／核验入口
- [source-manifest.json](source-manifest.json)：原始文件和公开文件的 SHA-256、变换范围；[checksums.json](checksums.json) 核验本目录公开文件

归档原始合成脚本逐字保留，未重写算法来改变经济或计时结果；便携入口只处理新输出、安装身份、
线程和缓存。历史本地路径前缀在 JSON 中替换为 `${BENCHMARK_ROOT}` 等占位符，数值、版本、
产物 URL 和哈希均保留。公开 CSV 统一为仓库要求的 LF 换行；ZIP 内 CSV 保留原始 CRLF，
两者数值相同，原始与公开文件哈希在来源清单中分别记录。竞争框架进程的环境中可能残留未导入的旧 DoriBT 分发元数据；
实际 DoriBT 运行身份以 `release_attestation`／`recorded/attestations` 为准。

原始适配器仅调用各框架公开 API，不附带第三方框架源码；合成基准源码随本项目按
[Apache-2.0](../../../LICENSE) 提供，归档内附同一许可证。

## 从干净目录准备

以下命令用于 Linux x86_64／CPython 3.13；`resource` 等采样依赖与原始计时环境一致，
不把这套脚本的运行平台范围扩写为 DoriBT 本身的平台限制。先安装指定 Python，
将本目录的 ZIP 下载到一个空工作目录，再运行：

```sh
python3.13 -m zipfile -e source-results.zip reproduction
cd reproduction
python3.13 -m venv env
env/bin/python -m pip install -r requirements-common.txt "doribt[numba]==0.6.0"
env/bin/python run.py --help
env/bin/python run.py daily --engine doribt-python --smoke --output results/smoke-dori.json
env/bin/python run.py daily --engine vectorbt-rust --smoke --output results/smoke-vbt.json
```

精确原始 Python 为 3.13.5；完整直接与传递依赖在归档中锁定。安装 DoriBT 纯 wheel 的 SHA-256
应与 `artifact-provenance.json` 中的 PyPI 产物一致。复用已经安装好且隔离的目录时，
DoriBT 命令也可传 `--source /absolute/path/to/installed-root`，入口会检查实际导入版本与路径。
这不是对源码 checkout 的修改，也不依赖旧工作区位置。

`--smoke` 只检查合成输入、公开 API 和独立经济核验：日线缩为 40 bar × 2 标的，
矩阵缩为最多 4 日 × 3 标的。其计时不用于性能结论。不要给 `batch` 添加 `--smoke`：
它保留原 10 账户工作流。每次运行使用新输出名；入口拒绝覆盖已有 JSON 或复用缓存目录。

## 重跑日线、批量与大扫描

确保没有其他测试、编译或渲染竞争 CPU。以下命令逐条执行，不要并行：

```sh
env/bin/python run.py daily --engine doribt-python --output results/daily-python.json
env/bin/python run.py daily --engine doribt-numba --output results/daily-numba.json
env/bin/python run.py daily --engine doribt-numba-callback --output results/daily-callback.json
env/bin/python run.py daily --engine vectorbt-numba --output results/daily-vbt-numba.json
env/bin/python run.py daily --engine vectorbt-rust --output results/daily-vbt-rust.json
env/bin/python run.py daily --engine backtrader --output results/daily-backtrader.json
env/bin/python run.py batch --engine doribt-numba --output results/batch-dori.json
env/bin/python run.py batch --engine vectorbt-rust --output results/batch-vbt.json
```

补充 Python 回调用 `--engine doribt-python-callback`；小批量也支持 Python、Backtrader、
VectorBT Numba 与 Zipline。日线和小批量每个热轮均核验现金、持仓、权益、逐笔成交，
至少 3 轮且累计热计时不少于 10 秒。

大扫描每次为 100 个独立 100 标的组合 × 2,520 日；每进程先预热一个配置或一个 10 组合批次，
只测一次完整扫描。三次独立进程形成三轮统计，第二轮反向顺序：

```sh
for trial in 1 2 3; do
  engines="doribt-numba vectorbt-numba vectorbt-rust"
  if [ "$trial" = 2 ]; then engines="vectorbt-rust vectorbt-numba doribt-numba"; fi
  for engine in $engines; do
    env/bin/python run.py grid --engine "$engine" --output "results/grid-$engine-$trial.json"
  done
done
```

不要将单进程的 `measured_repetitions=1` 描述为多次中位数；汇总三份 `execution_seconds`
后才有三轮中位数。默认 Python 大扫描是单次观察；Backtrader 和 Zipline 的大扫描没有实测。
便携命令不设隐式超时，若自行设置超时，应记录其是否包含导入、准备、编译与核验。

## 重跑语义矩阵

先检查一个最小场景，再运行完整输入：

```sh
env/bin/python run.py matrix --engine dori --scenario daily_sparse_targets --smoke --output results/matrix-smoke.json
env/bin/python verify_matrix.py results/matrix-smoke.json --kind pure
env/bin/python run.py matrix --engine dori --scenario minute_dense_targets --output results/minute-dori.json
env/bin/python verify_matrix.py results/minute-dori.json --kind pure
env/bin/python run.py matrix --engine vbt --scenario minute_dense_targets --output results/minute-vbt.json
env/bin/python verify_matrix.py results/minute-vbt.json --kind vectorbt
```

完整场景名保留于 `sources/matrix/matrix_workloads.py` 的 `SCENARIOS`。逐一替换 `--scenario`
即可重跑全部 18 个 DoriBT 场景；VectorBT 不运行 `daily_corporate_actions`。
输入的频率、密度、规则与参数由原脚本决定，不能只靠场景名类推其他市场情形。

`verify_matrix.py` 必须在计时结束后执行，它重新核验最后一次热轮的 NPZ：17 个可比场景
使用各自独立整数参考，完整 DoriBT 输入还核对归档的全部公开字段哈希（`run_info` 来源元数据单列）。
公司行动只支持对完整输入作归档审计回归，没有独立外部经济 oracle，也不能给它作跨框架速度比。
原先冻结旧基线的庞大 NPZ 不包含在轻量包中；原始旧基线审计差异保留在 `audit-parity.json`，
新复现则直接对本次归档的完整公开字段指纹核验，不声称重新运行了更早的包。

更强替代工作流使用同一个合成输入与核验：

```sh
MATRIX_TARGET_CALLBACK_MODE=rust env/bin/python run.py matrix --engine vbt --scenario minute_dense_callback --output results/alternative-rust.json
env/bin/python verify_matrix.py results/alternative-rust.json --kind rust-alternative
MATRIX_STATEFUL_NUMBA=1 env/bin/python run.py matrix --engine vbt --scenario minute_stateful_orders --output results/alternative-numba.json
env/bin/python verify_matrix.py results/alternative-numba.json --kind numba-alternative
```

便携入口为每个进程创建空缓存，历史矩阵则仅在每个 DoriBT 批次开始时清空缓存。
这是明确的复现入口差异：**新首轮耗时不能直接横比历史矩阵每行首轮**；预热后的主计时定义相同。
日线原始对比本来就是每进程新缓存。五项数值库线程始终为 1。

## 可选原生构建

原生范围仅 Linux x86_64／CPython 3.13／GIL；准备编译器和可用的 stable-ABI Python 头文件。
原环境实际使用 CPython 3.12.14 开发头文件、CPython 3.13.5 运行，编译器和二进制哈希记录于
`artifact-provenance.json`，不能将本机二进制当作跨平台发行包。

在单独虚拟环境重现，避免混淆默认纯包：

```sh
python3.13 -m venv native-env
native-env/bin/python -m pip install -r requirements-common.txt
native-env/bin/python -m pip download --no-deps --no-binary=:all: doribt==0.6.0 -d artifacts
# 核对 sdist 哈希；如默认头文件不满足稳定 ABI，显式指定已验证的头文件目录。
DORIBT_BUILD_NATIVE=required native-env/bin/python -m pip wheel --no-deps artifacts/doribt-0.6.0.tar.gz -w native-wheel
native-env/bin/python -m pip install native-wheel/doribt-*.whl
native-env/bin/python run.py matrix --engine dori --native --scenario minute_dense_targets --output results/native-minute.json
native-env/bin/python verify_matrix.py results/native-minute.json --kind native
```

需要替代头文件时，在构建命令前添加 `DORIBT_NATIVE_INCLUDE=/path/to/verified/include`。
`--native` 强制加载扩展，并在矩阵热计时后的独立运行中核验 C 调用。
日线和大扫描可用相同 `--native` 选项，但原日线预计算路径不调用记录物化器；
其纯／原生差异不能直接当作 C 加速收益。

## Zipline 的独立环境

```sh
python3.12 -m venv zipline-env
zipline-env/bin/python -m pip install -r requirements-zipline.txt
zipline-env/bin/python run.py daily --engine zipline --output results/daily-zipline.json
```

Zipline-reloaded 使用独立 Python 3.12／pandas 2.3 环境；其他配置是 Python 3.13／pandas 3.0。
合成适配器保留官方 slippage 扩展和日频事件的时间戳约定，不依赖外部行情服务。

## 文档归档验证

本次只执行归档解压、源码哈希与路径检查、命令帮助及小规模功能验证；没有为了文档再跑完整性能套件。
验证范围与结果见 [validation.json](validation.json)。该文件里的功能耗时不用于更新任何主性能数值。
