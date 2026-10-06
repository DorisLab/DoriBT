"""严格构建文档，校验站内链接，并在仓库外运行使用教程。"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if value := values.get("id"):
            self.ids.add(value)
        key = "href" if tag in {"a", "link"} else "src"
        if tag in {"a", "link", "script", "img"} and (value := values.get(key)):
            self.links.append(value)


def check_links(site: Path) -> None:
    pages = {p.resolve(): Page(p) for p in site.rglob("*.html")}
    failures = []
    for source, page in pages.items():
        for href in page.links:
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc:
                continue
            target = (source.parent / unquote(parsed.path)).resolve() if parsed.path else source
            if target.is_dir():
                target /= "index.html"
            if not target.is_relative_to(site) or not target.exists():
                failures.append(f"{source.name}: {href}")
            elif parsed.fragment and target in pages:
                if unquote(parsed.fragment) not in pages[target].ids:
                    failures.append(f"{source.name}: {href}")
    if failures:
        raise RuntimeError("站内链接或锚点无效：\n" + "\n".join(failures))
    print(f"站内链接、锚点与静态资源通过：{len(pages)} 个页面")


def check_search(site: Path) -> None:
    text = (site / "searchindex.js").read_text(encoding="utf-8")
    index = json.loads(text.removeprefix("Search.setIndex(").removesuffix(")"))
    terms = set(index["terms"]) | set(index["titleterms"])
    missing = {"佣金", "最低佣金", "部分成交", "runconfig"} - terms
    if missing:
        raise RuntimeError(f"中文／API 搜索索引缺少必要词条：{sorted(missing)}")
    api = Page(site / "api.html")
    if not {"doribt.Backtest.run", "doribt.RunConfig", "doribt.Context.order"} <= api.ids:
        raise RuntimeError("API 签名未生成可引用的对象锚点")


def run_examples(python: str, backend: str) -> None:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", MPLBACKEND="Agg")
    with tempfile.TemporaryDirectory(prefix="doribt-tutorial-") as temporary:
        work = Path(temporary)
        shutil.copytree(
            ROOT / "examples", work / "examples", ignore=shutil.ignore_patterns("__pycache__")
        )
        tutorial = (ROOT / "docs/guide/data.md").read_text(encoding="utf-8")
        csv = re.search(r"```text\n(session,.*?)\n```", tutorial, re.DOTALL)
        if csv is None:
            raise RuntimeError("行情教程缺少 CSV 示例")
        (work / "bars.csv").write_text(csv[1] + "\n", encoding="utf-8")
        commands = [
            ["examples/quickstart.py"],
            ["examples/csv_backtest.py"],
            ["examples/market_data.py"],
            *[
                [f"examples/{name}.py", "--backend", backend]
                for name in (
                    "sma",
                    "strategies",
                    "dividends",
                    "historical_rules",
                    "minute",
                    "slippage",
                )
            ],
            ["examples/minute.py", "--backend", backend, "--precomputed"],
            ["examples/research.py", "--backend", backend, "--plot", "--output", "report"],
        ]
        for command in commands:
            print("教程验证：", " ".join(command), flush=True)
            subprocess.run([python, *command], cwd=work, env=env, check=True)
        check_snippets(python, work, env)


def check_snippets(python: str, work: Path, env: dict[str, str]) -> None:
    # 片段复用人工数据；完整示例已单独执行，这里验证正文中的可组合调用。
    preamble = (
        "from strategies import synthetic_market, moving_average\n"
        "from doribt import *\n"
        "data = synthetic_market()\n"
        "result = Backtest(data, config=RunConfig()).run(moving_average)\n"
    )
    for name in ("minutes", "parameters", "reports", "extensions"):
        text = (ROOT / f"docs/guide/{name}.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```python\n(.*?)\n```", text, re.DOTALL)
        script = work / "examples" / f"tutorial_{name}.py"
        script.write_text(preamble + "\n".join(blocks), encoding="utf-8")
        subprocess.run([python, str(script)], cwd=work, env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="验证示例所用的已安装包解释器")
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    site = ROOT / ".quality/docs-site"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "sphinx",
            "-E",
            "-W",
            "--keep-going",
            "-n",
            "-b",
            "html",
            "docs",
            str(site),
        ],
        cwd=ROOT,
        check=True,
    )
    check_links(site.resolve())
    check_search(site)
    # Linux 虚拟环境的 Python 通常是软链接；解析真实路径会丢失环境。
    run_examples(os.path.abspath(args.python), args.backend)
    print("文档构建与教程验证通过")


if __name__ == "__main__":
    main()
