# 真实问答回归与反馈闭环

目标：让开发者在交付前发现“没有查询就回答”“答非所问”“漏答复合问题”“查错产品/时间”等问题。

## 当前执行约束

`backend/app/agent/request_scope.py` 在每轮请求内解析当前支持的产品别名，并在代词追问时使用最近的用户产品上下文；产品切换优先于旧上下文。它为可识别的数据请求提供独立于模型回答标签的检查。实际工具执行前限定产品范围，去除没有请求依据的时间和情绪筛选，保留显式范围及比较请求。

定性请求漏查时，在现有调用预算内补做检索；复合请求仍缺少查询时不能报告完整成功。转述证据同样需要引用补全，补全失败则拒绝输出未经核验的回答。正常系统说明和提问示例不强制查询。

这是对当前产品与常见表达的保守约束，并非完整自然语言理解器。新别名、复杂相对日期和新产品需要扩充解析及回归用例；自动工具/引用校验也不能替代证据是否支持结论的语义审查。

## 两层验证

1. `tests/test_conversation_e2e.py` 验证评测器本身：故意注入错误数量、失败工具、错误产品、错误会话、丢失引用和 SSE 错误，确保不会误报通过。普通 Backend CI 自动运行，无模型费用。
2. `scripts/run_conversation_e2e.py` 启动真实 FastAPI lifespan，登录后调用真实 `/api/ask`，使用配置中的模型、PostgreSQL、Milvus，再按 SSE 回执读取数据库中的同一条回答。没有预写模型答案，也没有替换工具。属于 API 端到端回归；不包含浏览器渲染、反向代理和网络传输验证。

开发集 22 个场景、25 轮，覆盖原始报错、整体评价、评论数、错别字、续航、噪声、充电、情绪分布、趋势、同档比较、产品目录、多轮代词、切换产品、未知产品、未来时间、不可支持的续航结论、诱导编造和普通系统说明。另有 2 个独立场景、3 轮保留集。

## 运行

从仓库根目录运行，使用现有 `.env`。脚本只新增测试聊天记录，不重抓评论、不修改源评论、不生成周报。会产生真实模型调用费用。默认错误即停，`--keep-going` 继续其他独立场景，`--repeat` 可重复 1–5 次观察不稳定性。SDK 重试关闭；每轮最多 8 个模型请求、3 次工具调用，启动还包含一次 embedding 维度验证。

```powershell
.venv/Scripts/python.exe scripts/run_conversation_e2e.py --case reported_failure --output artifacts/e2e/reported.json
.venv/Scripts/python.exe scripts/run_conversation_e2e.py --keep-going --output artifacts/e2e/development.json
.venv/Scripts/python.exe scripts/run_conversation_e2e.py --suite holdout --keep-going --output artifacts/e2e/holdout.json
.venv/Scripts/python.exe scripts/run_conversation_e2e.py --case reported_failure --repeat 3 --output artifacts/e2e/stability.json
.venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_conversation_e2e.py
.venv/Scripts/python.exe scripts/build_semantic_review.py --report artifacts/e2e/development.json --output artifacts/e2e/semantic-bundle.json
```

也可通过 `VOC_E2E_PASSWORD` 指定登录密码。报告不保存 JWT 或密钥，但包含模型回答、引用及测试聊天标识，应按本地反馈数据管理。退出码 0 为全部自动检查通过，1 为业务检查失败或执行不完整，2 为启动/基础设施失败。进程中断时保留已完成结果，`complete=false`，不能当作整套通过。

## 判断标准

自动硬检查：SSE 必须有且仅有一个最终事件；HTTP 200 内的 error 也判失败；回答非空、语言匹配；统计/反馈问题有实际执行且成功的必要工具；SKU 范围正确；所需统计操作正确；SSE 与数据库的会话、回答、状态和引用一致；引用必须在真实数据库存在且产品和文档匹配。

评论数 oracle 独立执行 `count(distinct document_id)`，沿用系统启用产品及质量阈值，与模型输出核对；它代表当前 VOC 可分析评论数，不代表电商平台总评论数。数字出现在回答中只是初步检查，不能证明模型正确解释了指标，仍要语义审查。

语义审查：每题保留 rubric，检查各子问题是否回答、实际结论是否被证据支持、是否把评论数与提及数混淆、是否把少量案例推广为总体结论、是否忽略样本量、无证据时是否如实说明。报告初始 `semantic_review=pending`，自动通过绝不等于语义审查通过。可由开发者或独立评审模型结合问题、回答、工具证据逐条判定；评审模型应看证据并说明理由，不能仅凭语言流畅度给分。

`build_semantic_review.py` 汇总真实回答、引用原文并按保存的参数重新执行只读统计，生成可复核材料，不调用模型。材料保存源报告哈希；重新查询的oracle属于当前数据，不能当成原回放时的数据快照。语义结论单独保存，保留自动检查原始结果，避免把模型可读性评分当成数据真实性证明。

## 从失败反推修改

每条结果记录问题、SSE、持久化工具参数与状态、数据库 oracle、失败代码、修复方向和耗时。先确定失败层，再修改：

| 失败 | 优先检查 |
| --- | --- |
| 缺少统计或检索 | 工具选择、误判 general_guidance、格式修复是否改变了请求类型 |
| 错误 SKU/时间 | 产品别名、指代解析、凭空增加的过滤条件 |
| 评论数错误 | 文档去重、质量阈值、过滤范围、评论与提及的区别 |
| 无引用/引用不符 | 检索命中、证据回查、模型引用协议 |
| 工具失败 | 参数校验、数据库/向量库、provider 兼容性 |
| 工具都成功但漏答 | 子问题覆盖、证据相关性、最终归纳 |

修复后顺序：重跑失败题 → 相关多轮题 → 完整开发集 → 保留集 → 对关键题重复多次。不要改低断言、放开依据校验、为单句返回写死答案。开发集用于调优，保留集用于观察泛化；保留集暴露的问题加入未来开发集时，应补充新保留题。

发布要求：相关确定性测试通过；真实问题集执行完整且硬检查通过；语义审查没有遗漏；保留集通过。数据缺失时应明确区分“正确拒答”和“检索异常导致没查到”，不能删除失败题来提高通过率。浏览器端的输入、流式展示与引用交互仍需独立 UI 回归。
