# 安装

使用 **Python 3.13** 和独立虚拟环境。支持 Windows、Linux；当前包不接受 Python 3.12／3.14。

```sh
python --version
python -m venv .venv
```

Windows PowerShell 激活环境：

```powershell
.venv\Scripts\Activate.ps1
```

Linux：

```sh
source .venv/bin/activate
```

安装并确认版本：

```sh
python -m pip install doribt
python -c "import doribt; print(doribt.__version__)"
```

若需要复现本手册的发行版本，可安装 `doribt==0.3.0`。

## 可选功能

| 安装命令 | 用途 |
| --- | --- |
| `python -m pip install "doribt[plot]"` | Matplotlib 图表和 PNG 导出 |
| `python -m pip install "doribt[numba]"` | Numba 执行后端 |
| `python -m pip install "doribt[numba,plot]"` | 同时使用加速和图表 |

安装 Numba 后，仍需在 `RunConfig(backend="numba")` 中选择它。首次运行有编译开销；任意 Python 策略回调不会整体转成机器码。详见[预计算与性能](../scheduled-execution.md)。

中文图表会选择系统中的中文字体。Windows 通常可以使用微软雅黑；Linux 可安装 Noto CJK 字体（Debian／Ubuntu 包名 `fonts-noto-cjk`）。缺少中文字体时，内置图表标题回退为英文，自定义基准名称保持原文。

## 运行完整示例

[第一次回测](quickstart.md)是单文件脚本，不需要克隆仓库。要运行本手册的全套示例，获取仓库中的配套脚本：

```sh
git clone https://github.com/DorisLab/DoriBT.git
cd DoriBT
python examples/quickstart.py
python examples/research.py --plot --output my-report
```

上面的图表命令需要先安装 `doribt[plot]`，`my-report` 必须不存在。示例可能导入同目录的辅助模块，运行全套示例时保留完整 `examples/` 目录。

main 分支的示例和本手册统一使用 `RunConfig`；当前发行包支持这些接口。
