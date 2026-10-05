# 参与 DoriBT

欢迎提交错误报告、带来源的交易规则说明、可复现测试和小范围改进。维护者优先处理实际研究需求，不承诺问题响应或合并时间。

提交问题时，请提供 Python／依赖版本、执行后端、最小输入、预期与实际结果。请使用合成数据或确认可公开的数据；不要上传账号、令牌、私人策略和无权再分发的行情。

修改前阅读 [README](README.md)、[当前模型](docs/model.md)、[API 设计](docs/api-design.md)和[开发目标](docs/roadmap.md)。行为改动同时更新对应契约与有独立预期的测试；不能只以两个相似实现结果相同证明规则正确。新增规则请附交易所等一手来源及适用日期。

```sh
uv sync --locked --extra numba
uv run --no-sync python scripts/check.py --backend numba --audit
```

基础安装、定向检查与凭据扫描见[质量检查](docs/quality.md)。不得用跳过失败检查、删除断言、扩大忽略范围或放宽账本容差获取绿灯。依赖漏洞若无法立即修复，应提交有依据和期限的处理提案；当前没有忽略清单。

通过分支和 Pull Request 提交变更。提交信息使用 Conventional Commits；说明行为、验证与已知限制。`experimental` 可以演进，但实际变更须写入版本记录。推送前核对仓库本地的作者邮箱、署名和远程；SSH 认证身份不等于提交作者身份。

提交的贡献遵循本仓库 Apache-2.0 许可。
