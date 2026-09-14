# Week 1 完整开发规划文档

**项目：** VOC Agent — 户外电源竞品舆情分析系统
**阶段：** Week 1 — 基础设施 & 数据foundation
**文档状态：** 已锁定，可直接交接

---

## 1. 项目背景与目标

构建一个面向户外电源品类的 VOC（Voice of Customer）智能分析系统。系统分两层：
- **离线批处理层：** 每周定时抓取 Reddit/Amazon 评论，经过清洗、Aspect 分析、Embedding，存入 PostgreSQL 和 Milvus
- **实时 Agent 层：** 用户用自然语言提问，LLM 通过 Function Calling 路由到 SQL 工具、RAG 工具或周报工具，返回带引用的流式回答

Week 1 的目标是：**打通基础设施、定稿数据模型、完成数据摄取，为 Week 2 的 Enrichment 和 Embedding 提供干净的原始数据。**

---

## 2. 所有已锁定决策

### 2.1 基础设施决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 数据库 | Docker PostgreSQL（直接生产同款，放弃 SQLite） | SQLite 与 PostgreSQL 类型差异（JSONB/ARRAY）会导致 Alembic 迁移不兼容 |
| Python 版本 | 3.11+ | 异步特性成熟，SQLAlchemy 2.0 最佳支持 |
| 包管理 | `uv` | 速度快，与 pyproject.toml 配合 |
| PostgreSQL 异步驱动 | `asyncpg` | SQLAlchemy 2.0 async 的标准搭档 |
| ORM | SQLAlchemy 2.0（asyncio 模式） | 支持 async/await，类型安全 |
| Schema 迁移 | Alembic（autogenerate 模式） | 模型改动自动生成迁移脚本，`env.py` 配置为异步模式 |
| 向量数据库 | Milvus（Docker） | Hybrid search 支持 metadata filter + vector similarity |

### 2.2 架构决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 调度方式 | APScheduler 独立 Worker 进程 | Pipeline 是 CPU/GPU 密集任务，与 API 共进程会阻塞事件循环 |
| Worker 入口 | `python -m backend.worker.main`（独立进程） | 与 API 服务共享代码库和 DB 配置，但各自运行 |

### 2.3 Agent 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| Agent 框架 | 纯手写 Function Calling Loop，不引入 LangChain/LlamaIndex | 工具只有 3 个，30 行代码可实现，框架带来黑箱和依赖膨胀 |
| 工具调用轮次 | 支持 Multi-turn tool calls | 复杂比较类问题需要连续调用多个工具 |
| 流式输出 | 两阶段：① 工具执行中（loading 状态） → ② 最终答案逐 token 渲染 | 工具调用阶段无法流式，需前端区分两个状态 |
| 工具箱 | 3 个工具（见 2.4） | — |

### 2.4 三工具职责边界

| 工具 | 触发场景 | 返回数据类型 |
|------|----------|-------------|
| `tool_sql` | "本周哪个品牌差评最多？"、"噪音问题占比趋势" | 结构化数字、排名、统计 |
| `tool_rag` | "用户怎么描述 Delta 2 的噪音？"、"给我 5 条关于续航的原话" | 原始文本 + 来源元数据 |
| `tool_report` | "上周的市场总结"、"给我看第 8 周报告" | Markdown 文本块 |

**路由优先级（写入 System Prompt）：**
```
1. 宏观/摘要类问题 → tool_report（优先）
   └── 返回时附带提示用户可进一步追问精细数据
2. 用户明确要"原话/具体例子" → tool_rag
3. 用户要"数据/趋势/排名" → tool_sql
4. report 不存在（该周未生成）→ 自动降级到 tool_rag
```

### 2.5 数据存储决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| Milvus 向量粒度 | sentence/aspect 级别（每个 aspect mention 一个 vector） | review 级别粒度太粗，搜索噪音时会混入电池内容，降低 precision |
| PostgreSQL ↔ Milvus 关联方式 | `aspect_mentions.id`（UUID）同时作为 Milvus 的 primary key | 从 Milvus 检索结果可直接用 ID 查 PostgreSQL，无需在 Milvus 存冗余字段 |
| Milvus 跨系统 join key | `sku_code`（slug 格式，如 `ecoflow-delta2`） | 肉眼可读，方便调试，不用 UUID |

### 2.6 对话会话决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| Chat History 存储 | PostgreSQL `chat_messages` 表（不用 Redis） | MVP 对话量级小，PG 加索引查 20 条消息 < 1ms，Redis 是过度工程 |
| Session 创建时机 | 用户主动点"新对话"时创建 | — |
| 用户身份绑定 | MVP 阶段不绑定，`created_by` 字段 nullable 预留扩展 | — |
| 鉴权方式 | 单密码 + JWT Token（7 天有效期） | 内部工具，无需用户注册体系 |
| 鉴权实现位置 | `backend/app/core/security.py` | — |
| Agent 中间步骤存储 | 存入 `chat_messages` 的 JSONB 字段（`tool_calls` + `tool_results`） | 保留调试能力；`tool_results` 只存元数据（条数/耗时），不存原始数据体 |

### 2.7 Amazon 数据源决策

| 决策项 | 选择 |
|--------|------|
| MVP 数据源 | Julian McAuley Amazon Reviews 静态数据集（离线导入） |
| 原因 | Amazon 反爬严格，MVP 阶段优先跑通 pipeline 逻辑；真实爬虫在 Week 2 后接入 |
| Reddit 数据源 | PRAW 官方 API（实时抓取，无反爬问题） |

---

## 3. SKU 列表（已锁定）

| brand | model | sku_code | capacity_tier | 容量(Wh) | 亚马逊 Parent ASIN | 数据集评论数 | is_competitor | 系统测试定位 / 演示价值 |
|-------|-------|----------|---------------|---------|-------------------|------------|--------------|----------------------|
| EcoFlow | DELTA 2 | `ecoflow-delta2` | mid | 1024 | B0BNL7R3L1 | 229 | FALSE | 系统核心 Baseline：自家主打产品，主要用于验证 RAG 检索质量与专属特征（如快充）的提取。 |
| Jackery | Explorer 1000 | `jackery-explorer-1000` | mid | 1002 | B0BMQ9FGFS | 1714 | TRUE | 同档位正面竞品：与 DELTA 2 处于同一生态位，评论量极大，用于演示"本周自家产品对比杰克瑞有哪些核心痛点"等多表 Join 场景，以及 tool_sql 高并发聚合与时序趋势压测。 |
| Jackery | Explorer 240 | `jackery-explorer-240` | entry | 240 | B09YM1BXKP | 3653 | TRUE | 入门档数据之王：数据集内评论量最大的 SKU，适合做 tool_sql 的全量聚合压测与长周期时序分析。同时也用于验证 entry 档 vs mid 档的跨容量对比抑制逻辑。 |
| Jackery | Explorer 300 | `jackery-explorer-300` | entry | 293 | B0C7W65JP8 | 32 | TRUE | 便携入门档补充：评论量少，用于测试系统在低数据量 SKU 上的降级表现和零结果提示策略。 |
| Anker | SOLIX F2000 (767) | `anker-solix-f2000` | large | 2048 | B0BP2DT79S | 34 | TRUE | 大容量高端标杆：知名消费电子巨头出品，评论质量极高，适合用于测试系统对高级 Aspect（如智能 App 控制、双轮拉杆设计）的语义解析。 |

**SKU 选定调整说明：**
- `jackery-explorer-1000`：ASIN 从旧版 `B0833FBN8B`（0条评论）切换至 parent ASIN `B0BMQ9FGFS`（1714条），解决数据集匹配问题
- `bluetti-ac200p`：**彻底放弃**，数据集中无可用数据，且无其他 large 档替补
- `jackery-explorer-240`：**新增**，3653条评论为全数据集最大量，填补第5个 SKU 槽位
- `ecoflow-delta2`：ASIN 从 `B0B9XB57XM` 切换至 parent ASIN `B0BNL7R3L1`（229条）
- `anker-solix-f2000`：ASIN 从 `B09XM7WDZ2` 切换至 parent ASIN `B0BP2DT79S`（34条）
- `jackery-explorer-300`：ASIN 从 `B082TMBYR6` 切换至 parent ASIN `B0C7W65JP8`（32条）
- **总评论数：~5,662 条**，完全满足 Week 1 验收需求
- 所有 ASIN 统一使用 **parent ASIN**，因为 McAuley 数据集中评论关联的是 parent 而非子变体

**`capacity_tier` 字段说明：**
- `entry`：< 500Wh（小容量便携场景）— 本列表含 Explorer 240 (240Wh) 和 Explorer 300 (293Wh)
- `mid`：500–1500Wh（家庭应急 + 长时户外）— 本列表含 DELTA 2 (1024Wh) 和 Explorer 1000 (1002Wh)
- `large`：> 1500Wh（大容量家庭应急 + 高功率场景）— 本列表含 SOLIX F2000 (2048Wh)
- 设计原因：`tool_sql` 做竞品对比时自动限定同档位，避免跨容量级别的无意义比较

**自家产品选择理由：**
EcoFlow DELTA 2 处于竞争最激烈的 mid 档（同档竞品 Jackery Explorer 1000），aspect 维度丰富（用户明确提及噪音、快充等特性），适合做 RAG 检索质量验证。

---

## 4. DB Schema 完整定义

### 4.1 ER 关系总览

```
skus
 └──< documents (sku_id → skus.id)
       └──< aspect_mentions (document_id → documents.id)
                    │
                    └── id 同时作为 Milvus vector primary key

weekly_reports (sku_id → skus.id, UNIQUE: sku_id + week_id)
 └──< weekly_topics (weekly_report_id → weekly_reports.id)

chat_sessions
 └──< chat_messages (session_id → chat_sessions.id)
```

### 4.2 各表字段详细定义

**`skus`**
```
id                UUID, PK
brand             VARCHAR NOT NULL
model             VARCHAR NOT NULL
sku_code          VARCHAR UNIQUE NOT NULL    # slug格式，跨系统join key
category          VARCHAR DEFAULT 'portable-power-station'
capacity_wh       INTEGER
capacity_tier     VARCHAR                   # 'entry' | 'mid' | 'large'
is_competitor     BOOLEAN NOT NULL
created_at        TIMESTAMP WITH TIME ZONE
```

**`documents`**
```
id                UUID, PK
sku_id            UUID, FK → skus.id
platform          VARCHAR NOT NULL           # 'reddit' | 'amazon'
external_id       VARCHAR NOT NULL           # 原始平台ID
title             TEXT                       # Reddit帖标题，Amazon评论无则null
body              TEXT NOT NULL              # 清洗后正文（PII已脱敏）
rating            SMALLINT                   # Amazon星级，Reddit则null
author_hash       VARCHAR                    # Presidio脱敏后的作者标识
source_url        TEXT
published_at      TIMESTAMP WITH TIME ZONE
week_id           INTEGER NOT NULL           # ISO周数，如202408（冗余存储方便过滤）
ingested_at       TIMESTAMP WITH TIME ZONE
UNIQUE(platform, external_id)               # 防重复抓取
```

**`aspect_mentions`**
```
id                UUID, PK                   # 与Milvus vector ID一一对应
document_id       UUID, FK → documents.id
aspect_label      VARCHAR NOT NULL           # 'noise'|'battery_life'|'portability'...
sentiment         VARCHAR NOT NULL           # 'positive'|'negative'|'neutral'
sentiment_score   FLOAT                      # -1.0 ~ 1.0
mention_text      TEXT NOT NULL              # 该aspect的原句
context_window    TEXT                       # 前后各一句的完整上下文
quality_score     FLOAT                      # 可操作性评分（enrichment产出）
week_id           INTEGER NOT NULL           # 冗余，方便查询
created_at        TIMESTAMP WITH TIME ZONE
```

**`weekly_reports`**
```
id                UUID, PK
sku_id            UUID, FK → skus.id
week_id           INTEGER NOT NULL
report_md         TEXT                       # 完整Markdown内容
summary           TEXT                       # ≤200字摘要，tool_report优先返回此字段
generated_at      TIMESTAMP WITH TIME ZONE
UNIQUE(sku_id, week_id)
```

**`weekly_topics`**
```
id                UUID, PK
weekly_report_id  UUID, FK → weekly_reports.id
sku_id            UUID, FK → skus.id         # 冗余，方便直接查询
week_id           INTEGER NOT NULL            # 冗余
topic_label       VARCHAR NOT NULL            # 'charging_speed'|'noise_complaint'...
topic_summary     TEXT                        # 该话题一句话描述
mention_count     INTEGER
avg_sentiment     FLOAT
top_aspects       JSONB                       # [{"aspect": "noise", "count": 23}]
```

**`chat_sessions`**
```
id                UUID, PK
title             VARCHAR                     # 前几字自动生成
created_by        VARCHAR                     # nullable，预留多用户扩展
is_active         BOOLEAN DEFAULT TRUE        # 软删除
created_at        TIMESTAMP WITH TIME ZONE
updated_at        TIMESTAMP WITH TIME ZONE
```

**`chat_messages`**
```
id                UUID, PK
session_id        UUID, FK → chat_sessions.id
role              VARCHAR NOT NULL            # 'user' | 'assistant'
content           TEXT NOT NULL               # 用户输入 或 最终回答
tool_calls        JSONB                       # assistant发起的工具调用（nullable）
tool_results      JSONB                       # 工具返回的元数据，非原始数据（nullable）
cited_ids         JSONB                       # 引用的aspect_mention UUIDs列表
created_at        TIMESTAMP WITH TIME ZONE

# tool_calls 结构示例：
# [{"tool_name": "tool_rag", "arguments": {"aspect": "noise", "sku_code": "ecoflow-delta2", "limit": 5}}]

# tool_results 结构示例（只存元数据）：
# [{"tool_name": "tool_rag", "result_count": 5, "execution_ms": 120}]

# cited_ids 结构示例：
# ["uuid-1", "uuid-2", "uuid-3"]
```

### 4.3 Milvus Collection Schema

```
Collection name: aspect_mentions

Fields:
  id              VARCHAR        # 与 PostgreSQL aspect_mentions.id 相同
    embedding       FLOAT_VECTOR   # dim 读取 EMBEDDING_DIMENSIONS（embedding-3 当前为 1024）
  sku_code        VARCHAR        # metadata filter用（slug格式）
  aspect_label    VARCHAR        # metadata filter用
  sentiment       VARCHAR        # metadata filter用
  week_id         INTEGER        # metadata filter用
  platform        VARCHAR        # metadata filter用

Scalar Index: sku_code, aspect_label, week_id
Vector Index: HNSW（适合MVP规模 < 100万向量）
```

---

## 5. 目录结构（Week 1 涉及部分）

```
voc-agent/
├── docker-compose.yml               # PostgreSQL + Milvus
├── .env.example                     # 所有环境变量模板
├── pyproject.toml                   # 依赖声明
├── alembic.ini                      # Alembic配置
├── docs/
│   └── prompts.md                   # 占位：Agent路由优先级规则
├── backend/
│   └── app/
│       ├── main.py                  # FastAPI app + lifespan事件
│       ├── core/
│       │   ├── settings.py          # Pydantic BaseSettings，读取.env
│       │   ├── database.py          # 异步engine + AsyncSession工厂
│       │   └── security.py          # JWT签发/验证（骨架）
│       └── db/
│           ├── models.py            # 所有ORM模型（7张表）
│           ├── seed.py              # SKU初始数据写入脚本
│           └── migrations/
│               ├── env.py           # 异步模式配置（关键）
│               └── versions/
│                   └── 0001_initial.py
│   └── worker/
│       ├── main.py                  # 独立进程入口（骨架）
│       └── jobs.py                  # 占位，Week 2填充
└── pipelines/
    ├── config/
    │   └── targets.py               # SKU → 抓取目标映射
    ├── ingestion/
    │   ├── reddit_fetcher.py        # PRAW实时抓取
    │   └── amazon_loader.py         # McAuley数据集静态导入
    └── sanitize/
        └── pii_cleaner.py           # Presidio匿名化
```

---

## 6. Day-by-Day 执行计划

### Day 1-2：基础设施层
**交付物：** `docker-compose up` 成功，FastAPI 启动，PostgreSQL 连接正常

```
- docker-compose.yml（PostgreSQL 15 + Milvus 2.x）
- .env.example（DB连接串、Reddit API Key、JWT Secret等）
- pyproject.toml（asyncpg, sqlalchemy, alembic, fastapi, pydantic-settings, praw, presidio-analyzer）
- backend/app/core/settings.py
- backend/app/core/database.py（async engine）
- backend/app/main.py（GET /health 端点）
```

### Day 3：Schema 落地 + Alembic
**交付物：** `alembic upgrade head` 在 Docker PG 建出 7 张表，seed 脚本跑通

```
- backend/app/db/models.py（7张表的ORM定义）
- alembic.ini + migrations/env.py（异步模式）
- alembic revision --autogenerate → 0001_initial.py
- backend/app/db/seed.py（写入5条SKU数据）
```

**注意：** `env.py` 必须配置 `run_async_migrations`，否则与 asyncpg 不兼容（常见坑）

### Day 4-5：数据摄取层
**交付物：** `documents` 表有真实数据（Reddit + Amazon 各至少覆盖目标 SKU）

```
- pipelines/config/targets.py（SKU到抓取关键词/ASIN的映射）
- pipelines/ingestion/reddit_fetcher.py（PRAW，按sku_code分类写入）
- pipelines/ingestion/amazon_loader.py（McAuley数据集过滤目标SKU写入）
- pipelines/sanitize/pii_cleaner.py（Presidio，输出author_hash）
```

**`targets.py` 需定义的映射：**
```python
TARGETS = {
    "ecoflow-delta2": {
        "amazon_asin": ["B0BNL7R3L1"],           # parent ASIN, 229条
        "reddit_keywords": ["ecoflow delta 2", "delta2"],
        "reddit_subreddits": ["SolarDIY", "preppers", "vandwellers", "camping"]
    },
    "jackery-explorer-1000": {
        "amazon_asin": ["B0BMQ9FGFS"],           # parent ASIN, 1714条
        "reddit_keywords": ["jackery 1000", "jackery explorer 1000"],
        "reddit_subreddits": ["SolarDIY", "preppers", "vandwellers", "camping"]
    },
    "jackery-explorer-240": {
        "amazon_asin": ["B09YM1BXKP"],           # parent ASIN, 3653条
        "reddit_keywords": ["jackery 240", "jackery explorer 240"],
        "reddit_subreddits": ["SolarDIY", "preppers", "vandwellers", "camping"]
    },
    "jackery-explorer-300": {
        "amazon_asin": ["B0C7W65JP8"],           # parent ASIN, 32条
        "reddit_keywords": ["jackery 300", "jackery explorer 300"],
        "reddit_subreddits": ["SolarDIY", "preppers", "vandwellers", "camping"]
    },
    "anker-solix-f2000": {
        "amazon_asin": ["B0BP2DT79S"],           # parent ASIN, 34条
        "reddit_keywords": ["anker solix f2000", "anker 767", "anker power station"],
        "reddit_subreddits": ["SolarDIY", "preppers", "vandwellers", "camping"]
    },
}
```

### Day 6-7：验收 + Worker 骨架
**交付物：** 端到端验收通过，Worker 进程能独立启动

```
- backend/worker/main.py（APScheduler骨架，Week 2填充job逻辑）
- backend/worker/jobs.py（占位文件）
- 运行端到端验收检查表
```

---

## 7. Week 1 验收标准（Checklist）

```
基础设施：
  ✅ docker-compose up -d 启动 PostgreSQL + Milvus 无报错
  ✅ GET /health 返回 200

数据模型：
  ✅ alembic upgrade head 建出 7 张表（无报错）
  ✅ seed.py 运行后 skus 表有 5 条数据，sku_code 字段格式正确

数据摄取：
  ✅ documents 表有来自 reddit 的数据（至少覆盖 ecoflow-delta2）
  ✅ documents 表有来自 amazon 的数据（McAuley 数据集导入）
  ✅ UNIQUE(platform, external_id) 约束有效（重复运行不报错，不重复插入）
  ✅ body 字段已完成 PII 脱敏（无真实人名/邮件/电话）

Worker：
  ✅ python -m backend.worker.main 启动不报错（即使 job 为空）
```

---

## 8. Week 2 预告（交接用）

Week 1 结束后，Week 2 接手时需要：

1. **输入：** `documents` 表中干净的原始评论数据
2. **Week 2 核心任务：**
   - 本地 Enrichment Pipeline：Aspect 抽取 + 情感分析 + 质量打分 → 写入 `aspect_mentions` 表
   - Embedding 计算：对 `mention_text` + `context_window` 做向量化
   - Milvus 写入：按 4.3 节 Collection Schema 批量 upsert
   - APScheduler Job 注册：在 `worker/jobs.py` 填充实际的 pipeline 调用逻辑
3. **注意事项：**
   - `aspect_mentions.id` 必须与 Milvus vector ID 保持一致（Week 2 写入时需显式指定）
- Embedding 模型与 Milvus Collection `dim` 必须和 `EMBEDDING_DIMENSIONS` 一致（正式采用 `embedding-3`，当前为 1024）

---

*文档版本：v1.1 | 对应开发阶段：Week 1 | 所有决策已锁定 | SKU 列表已按数据集实勘结果最终定稿*
