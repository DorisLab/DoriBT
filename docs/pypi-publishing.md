# PyPI Trusted Publisher 配置

维护者操作说明。当前是配置准备阶段：尚未创建发布工作流或向 PyPI 上传发行包。

## 在 PyPI 登记

进入 [账户 Publishing 页面](https://pypi.org/manage/account/publishing/)，在 **Add a new pending publisher → GitHub** 填写：

| 表单字段 | 值 |
| --- | --- |
| PyPI Project Name | `doribt` |
| Owner | `DorisLab` |
| Repository name | `DoriBT` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Owner 是 GitHub 仓库所有者，不是 PyPI 登录名。Workflow name 只填文件名，对应计划新增的 `.github/workflows/publish.yml`；不是工作流显示名称或完整路径。环境名必须与发布 job 完全一致。

点击 **Add** 后会出现 Pending Publisher。它允许首次成功上传时创建项目，此后自动成为普通 Publisher；登记本身不创建项目，也不保留名称。无需创建 PyPI API Token 或把密码存入 GitHub Secrets。

## GitHub 侧准备

1. 在 `DorisLab/DoriBT → Settings → Environments` 创建 `pypi` 环境，部署来源限定为发行标签 `v*`。
2. 新增 `.github/workflows/publish.yml`，发布 job 使用 `environment: pypi`，仅该 job 授予 `id-token: write`。
3. 采用 PyPA 官方 `pypa/gh-action-pypi-publish`，固定 Action 提交；发布 job 下载已通过检查的 wheel／sdist 后上传，不在有发布权限的 job 内执行策略或构建。
4. 将发行检查与发布明确串联：标签版本与包版本一致，Windows／Linux × Python／Numba、依赖审计、凭据扫描及隔离安装成功后才能上传。同名旧文件不覆盖，失败不能跳过检查继续发布。

工作流具体触发方式、构建产物传递和发行检查串联在实现时一起验收；不能仅添加上传步骤就把任意 Release 视为通过。

## 首次发行顺序

建议首次 PyPI 版本为 `0.2.0`。当前源码仍为 `0.2.0.dev0`；正式发行时同步包版本、锁文件和 CHANGELOG，核对包元数据及所包含文件。完整文档站可以稍后完成，发行说明仍须准确。

完成 Trusted Publisher 与工作流配置后，提交候选并运行发行门禁，再上传 wheel 和 sdist。成功后从 PyPI 安装，检查版本、基础依赖、可选 extras 与最小回测。只有这一步完成后，文档才可以采用以下安装方式（当前要求 Python 3.13）：

```sh
python -m pip install doribt
python -m pip install "doribt[numba,plot]"
```

GitHub Release 可同时提供版本说明、校验和与相同发行资产。随后按实际发布版本重写安装教程及文档中心。

依据：[首次创建项目](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)、[字段与环境匹配](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)、[通过 OIDC 发布](https://docs.pypi.org/trusted-publishers/using-a-publisher/)。
