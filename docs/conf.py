"""从已安装的公开包构建中文使用手册与 API 签名。"""

from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

project = "DoriBT"
author = "DorisLab"
copyright = "2026, DorisLab"
release = package_version("doribt")
version = release
language = "zh_CN"
html_search_language = "zh"
html_search_options = {"dict": str(Path(__file__).parent / "search-terms.txt")}
extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx_copybutton"]
exclude_patterns = ["quality.md"]
root_doc = "index"
myst_heading_anchors = 4
autodoc_typehints = "none"
autodoc_docstring_signature = False
autodoc_member_order = "bysource"
html_theme = "furo"
html_title = f"DoriBT {release} 文档"
html_baseurl = "https://dorislab.github.io/DoriBT/"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "light_css_variables": {"color-brand-primary": "#ac302b", "color-brand-content": "#a72d28"},
    "dark_css_variables": {"color-brand-primary": "#ed918a", "color-brand-content": "#ed918a"},
    "source_repository": "https://github.com/DorisLab/DoriBT/",
    "source_branch": "main",
    "source_directory": "docs/",
}
html_show_sourcelink = False


def public_signatures(
    app: Any, what: str, name: str, obj: Any, options: Any, lines: list[str]
) -> None:
    # 页面手写中文语义；签名来自实际对象，避免重复展示内部英文说明。
    if name.startswith("doribt."):
        lines.clear()


def setup(app: Any) -> None:
    app.connect("autodoc-process-docstring", public_signatures)
