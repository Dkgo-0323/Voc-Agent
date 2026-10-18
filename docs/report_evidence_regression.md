# 周报证据可追溯性回归检查

检查日期：2026-10-18。数据库结构保持不变。

## 结论与模块

**周报尚不支持证据关联。** 检索到真实评论并不表示某条周报结论已经与该评论建立可审计关系。

- `backend/app/reporting/service.py`：收集统计、检索正负面证据、校验候选正文、保存周报。
- `backend/app/agent/tool_rag.py`：Milvus 命中经 PostgreSQL 水合、范围及质量校验后才可成为证据；`build_answer_citations` 只接受检索结果内的 mention UUID。
- `backend/app/agent/schemas.py`：`WeeklyReportPayload` 只有周报标识、范围、正文、摘要及生成时间，没有评论引用字段。report UUID 不是 mention UUID。
- `backend/app/api/reports.py`：候选校验通过后才发送 `report_delta`，事务提交后发送 `report_completed`。
- `backend/app/agent/tool_report.py`：只读已存周报，不会将正文转成评论引用。

## 固定场景与预期

| 场景 | 自动检查与预期 |
| --- | --- |
| 有检索证据 | 固定 SKU、周和充电投诉，经过真实 RAG 服务与模拟存储水合后，引用保留 mention/document UUID、来源 URL 和原文片段；即使已有有效证据，额外未知 UUID 也被拒绝。 |
| 无证据 | 只有向量命中、关系库无记录时返回 EMPTY；不能用命中 UUID 构造引用。周报检索均为空时保留统计和正负面缺失警告，不伪造评论。 |
| 周报缺少证据关联 | 即使生成时有证据，模型也不能在正文或摘要中输出 UUID、HTTP(S) URL 或 Evidence/Citations 章节；失败时不发送正文、不保存、不提交，返回终止错误。正常生成及读取测试继续通过。 |

## 验证

在仓库根目录执行：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_tool_rag.py tests/test_report_generation.py tests/test_tool_report.py -q
.venv\Scripts\python.exe -m ruff check backend/app/reporting/service.py tests/test_tool_rag.py tests/test_report_generation.py
git diff --check
```

目标测试：45 passed；Ruff 通过。依赖已有 pkg_resources 和 Marshmallow 弃用警告。
扩展运行上述三个文件及 `tests/test_agent_router.py`、`tests/test_agent_schemas.py`、`tests/test_dashboard_api.py`：104 passed，3 条依赖弃用警告；`git diff --check` 通过。
测试使用固定场景和模拟依赖，不要求数据库、Milvus 或在线模型，也不证明线上评论真实性。

## 限制与下一步

校验确定性拒绝上述引用格式，并非自然语言事实核查，不能保证所有伪造引用格式或无证据主题陈述都被识别。无证据时的提示传入模型，但目前没有逐结论支持性校验。历史周报仍原样读取，不回填或篡改内容。

下一步应单独设计周报结论到 mention 的持久关联，记录生成使用的证据快照和范围，再允许展示可点击引用；上线前补充真实数据库集成测试及逐结论支持性检查。不得把临时 RAG 命中列表当作既有周报的证据映射。
