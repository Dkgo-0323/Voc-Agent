# Week 2 详细开发文档

## 验收状态：CONDITIONAL PASS

Week 2 的功能、迁移、Dashboard API、Embedding 1024 维度契约和小批量真实数据端到端链路均已完成验证。验收批次处理了 25 条文档，新增 38 条 PostgreSQL Mention 与 38 个 Milvus 向量，二者 UUID 差集为 0。

在扩大到全量处理前，必须完成以下修复后的复验：针对真实评论中仍可能出现的泛化 `build_quality`、技术配置误判，以及缺少明确太阳能语境的 `solar_charging`、隐喻性 `home_backup_use`，使用更新后的确定性证据规则再运行一轮不超过 5 条的真实文档验收，并人工复核新生成 Mention。不得修改既有 13 条历史 Mention，也不得重建 Milvus Collection。

只有该复验通过，且 Ruff、聚焦测试与全量 pytest 均通过后，Week 2 才可标记为 PASS 并进入全量处理。

## 前置检查清单

在开始 Week 2 之前，确认 Week 1 的交付物状态：

```
✅ PostgreSQL 运行中，7张表已迁移
✅ Milvus 运行中（docker-compose）
✅ documents 表有数据（Reddit + Amazon 已摄入）
✅ skus 表有5条记录（sku_code 已锁定）
✅ Worker 进程可以启动（APScheduler 骨架）
✅ pipelines/ 目录结构存在
```

---

## 架构变更：需要新增的数据库字段

Week 2 开始前，先讨论 Schema 变更，因为这会影响 Alembic Migration。

### `documents` 表新增字段

```
processing_status: VARCHAR(20)  DEFAULT 'raw'
    状态流转: 'raw' → 'enriched' → 'embedded' → 'failed'
    
processing_error: TEXT  NULLABLE
    失败时记录错误信息，方便 Debug
    
processed_at: TIMESTAMP  NULLABLE
    最后处理时间
```

### `aspect_mentions` 表确认字段

对照现有 Schema，确认以下字段存在：

```
id: UUID (Primary Key) ← Milvus Vector PK
sku_code: VARCHAR ← 冗余存储，避免 JOIN skus 表
document_id: UUID (FK → documents.id)
week_id: INTEGER (FK → weekly_reports? 或直接存周数)
aspect_label: VARCHAR(50) ← 18个预定义标签之一
sentiment: VARCHAR(20) ← 'positive'/'negative'/'neutral'
confidence: FLOAT ← LLM 给出的置信度
mention_text: TEXT ← 原文引用
context_window: TEXT ← 前后句，hard cap 200字符
quality_score: FLOAT ← 0-1 归一化
embed_text: TEXT ← 实际用于 Embedding 的拼接文本（存储备查）
created_at: TIMESTAMP
```

> **讨论点**：`embed_text` 要不要持久化存储？
>
> **建议存储**。原因：后续如果调整 Embedding 模型，可以直接对比新旧向量与同一文本的差异，不需要重新跑 LLM 提取。存储成本极低（TEXT 字段）。

### `weekly_reports` 表确认字段

Week 2 暂时不生成报告内容，但需要确认 `week_id` 的设计：

```
# 建议用 ISO Week Number 作为 week_id
# 例如：2024年第3周 → week_id = 202403
# 格式：YYYYWW（6位整数）
# 优点：可排序、可计算、人类可读
```

---

## Alembic Migration 计划

Week 2 需要一次新的 Migration：

```
Migration: add_processing_pipeline_fields
变更内容：
  1. documents 表：新增 processing_status, processing_error, processed_at
  2. documents 表：为 processing_status 添加索引（查询待处理记录用）
  3. aspect_mentions 表：确认 embed_text 字段存在，不存在则新增
  4. 为 aspect_mentions.sku_code 添加索引
  5. 为 aspect_mentions.aspect_label 添加索引
  6. 为 aspect_mentions.week_id 添加索引
  7. 为 aspect_mentions.quality_score 添加索引（Dashboard 排序用）
```

**索引设计原因**：Week 3 的 `tool_sql` 和 `tool_rag` 会大量使用这些字段做过滤，现在建好索引。

---

## 目录结构变更

基于现有结构，Week 2 新增以下文件：

```
voc-agent/
├── pipelines/
│   ├── enrichment/                    # 新增
│   │   ├── __init__.py
│   │   ├── aspect_extractor.py        # LLM 调用 + Structured Output 解析
│   │   ├── quality_scorer.py          # Quality Score 规则公式
│   │   └── prompts.py                 # Enrichment 专用 Prompts（独立管理）
│   ├── embedding/                     # 新增
│   │   ├── __init__.py
│   │   ├── embedder.py                # 智谱 embedding-3 封装
│   │   └── milvus_repo.py             # Milvus Collection CRUD
│   └── ingestion/                     # 已存在，本周不动
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── dashboard.py           # 新增：3个 Dashboard 端点
│   │   └── db/
│   │       └── repositories/          # 新增目录
│   │           ├── __init__.py
│   │           ├── document_repo.py   # Document 查询/状态更新
│   │           └── aspect_repo.py     # AspectMention 写入/聚合查询
│   └── worker/
│       └── jobs.py                    # 填充 Pipeline 逻辑（本周核心）
│
└── docs/
    └── aspect_labels.md               # 新增：18个标签的定义文档
```

---

## Day-by-Day 开发计划

### Day 1：Schema 变更 + Repository 层

**目标**：打好数据访问基础，后续所有模块依赖这一层。

#### 上午：Alembic Migration

执行 Migration，验证：
```sql
-- 验证 documents 表
SELECT processing_status, COUNT(*) 
FROM documents 
GROUP BY processing_status;
-- 预期：所有记录都是 'raw'

-- 验证索引
SELECT indexname FROM pg_indexes 
WHERE tablename = 'aspect_mentions';
```

#### 下午：Repository 层实现

**`document_repo.py`** 需要实现的方法：

```
# 查询
fetch_unprocessed(limit: int) → List[Document]
    WHERE processing_status = 'raw'
    ORDER BY created_at ASC
    LIMIT limit
    作用：Pipeline 每次批量取待处理记录

fetch_by_status(status: str) → List[Document]
    作用：Debug 和监控用

# 更新
update_status(doc_id: UUID, status: str, error: str = None)
    作用：Pipeline 各阶段完成后更新状态

# 批量更新（性能考虑）
bulk_update_status(doc_ids: List[UUID], status: str)
    作用：一批文档处理完后，一次性更新状态
```

**`aspect_repo.py`** 需要实现的方法：

```
# 写入
bulk_insert(mentions: List[AspectMentionCreate]) → List[UUID]
    作用：一个 Document 提取出的所有 Aspect 一次性插入
    返回：插入的 UUID 列表（后续 Milvus Upsert 用）

# 查询（Dashboard API 用）
get_sentiment_breakdown(week_id: int, sku_code: str = None)
    → {positive: int, negative: int, neutral: int}

get_top_aspects(week_id: int, sku_code: str = None, limit: int = 10)
    → [{aspect_label, count, avg_sentiment_score}]

get_sku_trends(sku_code: str, week_ids: List[int])
    → [{week_id, aspect_label, positive_count, negative_count}]
```

**关键设计**：Repository 层只做数据访问，不包含业务逻辑。所有方法接收/返回 Pydantic Schema 或基础类型，不暴露 SQLAlchemy Model 对象给上层。

---

### Day 2：Enrichment Pipeline

**目标**：实现 Aspect 提取 + Quality Score 计算，写入 `aspect_mentions`。

#### 上午：Prompt 设计（最重要的部分）

**`prompts.py`** 中定义 System Prompt：

```
角色：你是户外电源产品（便携储能电站）的用户评论分析专家。

任务：从给定的用户评论中提取 Aspect 提及，返回结构化 JSON。

【Aspect 标签列表】（必须从以下18个中选择，不允许创造新标签）：
核心性能类：
- battery_capacity: 续航时长、实际容量表现
- charging_speed: 充电效率（AC/DC/Solar充入速度）
- solar_charging: 太阳能充电表现
- ac_output_power: 交流输出功率是否满足设备需求
- output_ports: 端口种类、数量、布局

硬件质量类：
- build_quality: 物理做工、材质、耐用性
- noise_level: 风扇噪音、静音表现
- weight_portability: 重量、便携性、手柄
- thermal_management: 散热、过热保护
- display_interface: 显示屏、按键交互

软件生态类：
- app_connectivity: 手机App、蓝牙/WiFi连接
- setup_complexity: 首次设置难易度

商业服务类：
- price_value: 价格感知、性价比
- customer_service: 售后服务、退换货体验
- warranty_reliability: 长期可靠性、质保兑现

场景类：
- camping_outdoor_use: 露营、户外活动场景
- home_backup_use: 家庭备电、停电应急场景
- van_rv_use: 车载、房车长期使用场景

【输出规则】：
1. 每条评论最多提取3个 Aspect（选最重要的）
2. mention_text 必须是评论原文的直接摘录，最多60字符
3. context_window 是 mention_text 的前后句，最多200字符
4. sentiment 从 positive/negative/neutral 三选一
5. confidence 是你对 sentiment 判断的置信度（0.0-1.0）
6. 如果评论内容不涉及产品本身（纯物流投诉、刷单内容），返回空列表

【输出格式】（严格 JSON，不要有任何额外文字）：
{
  "aspects": [
    {
      "aspect_label": "noise_level",
      "sentiment": "negative",
      "confidence": 0.92,
      "mention_text": "fan is extremely loud",
      "context_window": "I use it in my bedroom. The fan is extremely loud and turns on unpredictably."
    }
  ]
}
```

> **Prompt 工程决策**：
> 1. 给每个标签加了一行中文描述。原因：LLM 在有定义的情况下选择准确率更高，避免把「充电速度」误判为 `battery_capacity`。
> 2. `mention_text` 限制60字符。原因：强迫 LLM 做精准提取，不是总结。
> 3. 明确排除刷单/物流内容。原因：Amazon 数据里这类噪声占比约 15-20%。

#### 下午：`aspect_extractor.py` 实现

**预过滤规则（方案A，在调用 LLM 之前执行）**：

```
过滤条件（满足任意一条则跳过该 Document）：
1. text 长度 < 30 字符
2. text 长度 > 3000 字符（超长评论切片处理，见下方说明）
3. 语言检测不是英文（langdetect 库，一行代码）
4. 包含以下关键词（纯物流噪声）：
   ['shipping', 'arrived', 'package', 'delivery', 'fedex', 'ups']
   且不包含任何产品功能词
```

**超长评论处理**：

```
问题：有些 Amazon 评论超过 3000 字符，直接送给 LLM 会超出上下文
策略：按句子切分，取前 2000 字符
原因：
  - 用户通常在开头说最重要的点
  - 保持简单，MVP 不做复杂的滑动窗口
  - 3000 字符约等于 750 token，加上 Prompt 约 1000 token，
    在 gpt-4o-mini 的 8k 上下文内完全安全
```

**批量调用策略**：

```
批次大小：10条 Document / 次 API 调用
原因：
  - 不是一次一条（太慢，API 调用开销大）
  - 不是一次100条（LLM 在处理大批量时准确率下降）
  - 10条是质量和速度的平衡点

并发：asyncio.gather，最多3个并发批次
原因：
  - OpenAI API 有 Rate Limit（TPM限制）
  - 3个并发足够快，不触发限流
```

> **讨论点**：批量调用时，是每批次一次 API 调用（把10条文本都放在一个 Prompt 里），还是10次独立调用？
>
> **建议：每批次一次 API 调用**，把10条文本编号后放在同一个 User Message 里。原因：减少 API 调用次数，降低延迟。代价是 Response 解析稍复杂，需要对应回每条文本的结果。

#### `quality_scorer.py` 实现

Quality Score 计算公式（0-1归一化）：

```python
# 各维度权重
W_SPECIFICITY = 0.35    # 最重要：mention_text 是否具体
W_CONFIDENCE  = 0.30    # LLM 的 sentiment 置信度
W_LENGTH      = 0.20    # 文本长度适中
W_SOURCE      = 0.15    # 数据来源可信度

# Specificity Score（规则计算）
# 高分条件：
#   - mention_text 包含具体数字（"2 hours", "1000W"）→ +0.3
#   - mention_text 包含比较词（"better", "worse", "than"）→ +0.2
#   - mention_text 不是泛泛评价词（"great", "good", "bad"）→ +0.2
#   - aspect_label 是核心性能类（不是场景类）→ +0.2
#   - mention_text 长度在 20-60 字符之间 → +0.1

# Length Score（倒U形曲线）
# mention_text + context_window 总长度
# < 50字符 → 0.3（信息量不足）
# 50-300字符 → 1.0（理想区间）
# > 300字符 → 0.6（可能是噪声）

# Source Weight
# Amazon Review（有星级） → 0.9
# Amazon Review（无星级） → 0.7
# Reddit Comment（score > 10）→ 0.8
# Reddit Comment（score 0-10）→ 0.6
# Reddit Post → 0.7

# 交叉验证 Bonus（仅 Amazon）
# 若 sentiment='negative' 但原始星级 >= 4 → confidence * 0.7（降权，矛盾信号）
# 若 sentiment='positive' 且原始星级 >= 4 → quality_score * 1.1（上限1.0）
```

**交叉验证逻辑很重要**：Amazon 评论有星级，可以用来验证 LLM 的 sentiment 判断。1星评论说 "great product" 是噪声，4星评论批评某个具体功能是高质量负面 Aspect。

---

### Day 3：Milvus Integration

**目标**：建立 Milvus Collection，实现 Embedding 生成和 Upsert。

**正式 Embedding 契约**：智谱 `embedding-3`，服务地址
`https://open.bigmodel.cn/api/paas/v4/`。向量维度只读取
`EMBEDDING_DIMENSIONS`（当前为 1024），应用启动时必须同时校验 API
实际返回维度与既有 Milvus Collection Schema。

#### 上午：Milvus Collection 设计

**Collection Schema 最终定义**：

```python
# Collection 名称：aspect_mentions_vectors_1024
# 分区策略：按 sku_code 分区（5个 SKU = 5个分区）
# 原因：按 SKU 查询是最频繁的操作，分区可以大幅减少搜索范围

Fields:
  id: VARCHAR(36), is_primary=True    # aspect_mentions.id (UUID)
  vector: FLOAT_VECTOR(1024)          # embedding-3；实际值读取 EMBEDDING_DIMENSIONS
  sku_code: VARCHAR(50)               # 标量过滤
  aspect_label: VARCHAR(50)           # 标量过滤
  sentiment: VARCHAR(20)              # 标量过滤
  week_id: INT64                      # 标量过滤（时间范围）
  quality_score: FLOAT                # 质量阈值过滤

Index（向量索引）：
  类型：HNSW
  参数：M=16, ef_construction=256
  度量：COSINE
  原因：HNSW 在中小规模数据（<100万）下召回率和速度最优

Index（标量索引）：
  sku_code: STL_SORT（枚举值）
  aspect_label: STL_SORT（枚举值）
  sentiment: STL_SORT（枚举值）
  week_id: STL_SORT（整数范围）
  quality_score: STL_SORT（浮点范围）
```

> **分区 vs 不分区的讨论**：
>
> MVP 阶段数据量可能只有几万条 Aspect Mentions，分区的性能收益几乎感知不到。但**建议现在就设计分区**，原因：后续扩展到更多 SKU 时不需要重建 Collection，而 Milvus 不支持在线修改分区策略。

#### 下午：`embedder.py` + `milvus_repo.py`

**`embedder.py`** 核心逻辑：

```
embed_text 构造规则（最终确认）：
  template = "[{sku_name}] [{aspect_label}]: {mention_text}"
  if context_window:
      template += ". Context: {context_window[:200]}"
  
  示例输出：
  "[EcoFlow DELTA 2] [noise_level]: fan is extremely loud. 
   Context: I use it in my bedroom. The fan is extremely loud 
   and turns on unpredictably."

批量 Embedding：
  - 每批：64条（智谱 embedding-3 支持批量输入）
  - 并发：不需要，Embedding API 批量调用本身已经很快
  - 错误处理：单条失败不影响整批，记录失败 ID 重试
```

**`milvus_repo.py`** 需要实现的方法：

```
setup_collection()
    创建 Collection + Index（幂等，存在则跳过）

upsert_vectors(records: List[MilvusRecord]) → int
    批量插入，返回成功数量
    批次大小：500条/次（Milvus 推荐值）

search(
    query_vector: List[float],
    sku_code: str = None,
    aspect_label: str = None,
    sentiment: str = None,
    week_id_range: Tuple[int, int] = None,
    quality_threshold: float = 0.5,
    top_k: int = 20
) → List[SearchResult]
    混合搜索：向量相似度 + 标量过滤
    返回：[(id: UUID, score: float, metadata: dict)]
    注意：top_k=20 是初始值，Week 3 调优时可能调整

delete_by_sku(sku_code: str)
    删除某个 SKU 的所有向量（数据重跑时用）
```

**`search` 方法的过滤表达式设计**：

```python
# Milvus 过滤表达式示例（在代码注释里说明，不是实际代码）
# 单 SKU 查询：
expr = 'sku_code == "ecoflow-delta2"'

# SKU + Aspect + 质量过滤：
expr = 'sku_code == "ecoflow-delta2" and aspect_label == "noise_level" and quality_score >= 0.5'

# SKU + 时间范围：
expr = 'sku_code == "ecoflow-delta2" and week_id >= 202401 and week_id <= 202404'

# 复杂组合（Week 3 tool_rag 会用到）：
expr = 'sku_code in ["ecoflow-delta2", "jackery-explorer-1000"] and sentiment == "negative" and quality_score >= 0.6'
```

---

### Day 4：APScheduler Job 串联

**目标**：把 Day 1-3 的组件串联成完整 Pipeline，验证端到端流程。

#### `jobs.py` Pipeline 设计

**完整流程图**：

```
weekly_pipeline_job()
│
├── Stage 0: Pre-check
│   └── 检查 Milvus Collection 是否存在，不存在则创建
│
├── Stage 1: Fetch Unprocessed Documents
│   ├── document_repo.fetch_unprocessed(limit=500)
│   ├── 预过滤（长度、语言、物流噪声）
│   └── 过滤后记录数量到日志
│
├── Stage 2: Aspect Extraction (Enrichment)
│   ├── 分批（10条/批）调用 LLM
│   ├── 解析 JSON Response
│   ├── 计算 Quality Score
│   ├── aspect_repo.bulk_insert(mentions)
│   ├── document_repo.update_status(doc_id, 'enriched')
│   └── 失败时：update_status(doc_id, 'failed', error_msg)
│
├── Stage 3: Embedding + Milvus Upsert
│   ├── 查询 status='enriched' 的 aspect_mentions（通过 document_id）
│   ├── 构造 embed_text
│   ├── 批量生成 Embeddings（64条/批）
│   ├── milvus_repo.upsert_vectors(records)
│   └── document_repo.update_status(doc_id, 'embedded')
│
└── Stage 4: Logging & Metrics
    ├── 记录本次运行统计：处理数量、成功/失败、耗时
    └── 写入日志（结构化 JSON 日志）
```

**幂等性保护细节**：

```
Stage 2 入口检查：
  WHERE processing_status = 'raw'
  → 已经是 'enriched'/'embedded' 的跳过

Stage 3 入口检查：
  WHERE processing_status = 'enriched'
  → 只处理 enriched 状态，embedded 的跳过

重跑策略：
  'failed' 状态的文档不会自动重跑
  需要手动执行：document_repo.reset_failed_documents()
  原因：自动重跑可能导致无限循环（如 LLM API 持续报错）
```

**APScheduler 配置**：

```python
# 调度策略
trigger: 'cron'
day_of_week: 'sun'    # 每周日凌晨执行
hour: 2               # 凌晨2点（避开 API 高峰）
timezone: 'UTC'

# 防止并发执行
max_instances: 1      # 同一时间只运行一个实例
coalesce: True        # 如果错过执行时间，只补跑一次

# 开发测试时
# 可以临时改成 interval trigger，每5分钟执行一次小批量
```

#### 端到端验证 Checklist

```
□ 从 documents 表取出一条 raw 记录
□ 预过滤：确认合规（长度 > 30，英文，无物流关键词）
□ LLM 调用：返回有效 JSON，包含至少1个 Aspect
□ Quality Score：0-1 之间，各维度权重加和正确
□ PostgreSQL 写入：aspect_mentions 有对应记录
□ embed_text：拼接格式正确，< 300 字符
□ Embedding：API 返回维度、EMBEDDING_DIMENSIONS 与 Milvus Schema 一致（当前 1024）
□ Milvus Upsert：用 UUID 查询 Milvus，能找到该向量
□ processing_status：document 状态已更新为 'embedded'
□ 幂等性：重跑 Pipeline，该 document 不会被重复处理
```

---

### Day 5：Dashboard APIs

**目标**：实现3个端点，用真实数据验证聚合逻辑。

#### API 设计（最终版）

**`GET /api/weeks`**

```
响应：
[
  {
    "week_id": 202403,
    "week_start": "2024-01-15",
    "week_end": "2024-01-21",
    "doc_count": 1250,
    "mention_count": 3420,
    "skus_covered": ["ecoflow-delta2", "jackery-explorer-1000", ...]
  }
]

实现：直接从 aspect_mentions GROUP BY week_id 聚合
注意：week_start/week_end 从 week_id 反解（202403 → 第3周的起止日期）
```

**`GET /api/overview?week_id=202403`**

```
响应：
{
  "week_id": 202403,
  "summary": {
    "total_mentions": 3420,
    "sentiment_breakdown": {
      "positive": 1820,
      "negative": 980,
      "neutral": 620
    }
  },
  "top_aspects": [
    {
      "aspect_label": "battery_capacity",
      "mention_count": 520,
      "positive_rate": 0.72
    }
  ],
  "sku_rankings": [
    {
      "sku_code": "ecoflow-delta2",
      "sku_name": "EcoFlow DELTA 2",
      "mention_count": 820,
      "sentiment_score": 0.68
    }
  ]
}

sentiment_score 计算：(positive - negative) / total，范围 -1 到 1
```

**`GET /api/skus/{sku_code}/trends?weeks=4`**

```
响应：
{
  "sku_code": "ecoflow-delta2",
  "sku_name": "EcoFlow DELTA 2",
  "capacity_tier": "mid",
  "trends": [
    {
      "week_id": 202403,
      "aspect_label": "battery_capacity",
      "positive_count": 45,
      "negative_count": 12,
      "neutral_count": 8,
      "avg_quality_score": 0.74
    }
  ]
}

注意：weeks 参数限制最大值为12（避免过大查询）
```

#### Router 和错误处理

```
所有端点统一处理：
  - week_id 不存在 → 404 with message
  - sku_code 不在5个锁定 SKU 内 → 400 with valid options
  - weeks 参数 > 12 → 400 with max value hint
  - 数据库连接失败 → 503 with retry hint

Response Model：
  使用 Pydantic V2 BaseModel 严格定义
  原因：Week 4 前端开发时，有明确的类型契约，减少联调成本
```

---

## 本周完成标准（Definition of Done）

```
Week 2 完成标准：

Pipeline 层：
□ 给定5个 SKU 的全量 documents，能跑完完整 Pipeline
□ aspect_mentions 表有数据，quality_score 分布在 0.3-0.9 之间（合理范围）
□ Milvus 中有对应向量，UUID 与 PostgreSQL 对齐
□ Pipeline 重跑不产生重复数据（幂等性验证）
□ 日志清晰记录每个 Stage 的处理数量和耗时

API 层：
□ 3个 Dashboard 端点返回正确数据
□ Pydantic Response Model 严格定义
□ 基本错误处理（404/400/503）

质量层：
□ 随机抽取20条 aspect_mentions，人工检查：
  - aspect_label 是否分类正确
  - mention_text 是否是原文引用
  - sentiment 与 mention_text 是否一致
  - quality_score 高分的是否真的比低分的更有价值
```

---

## 遗留讨论点（需要在开发中决策）

在实际开发中，你可能会遇到以下决策点，建议的处理方式：

**Q1: LLM 返回的 JSON 格式错误怎么办？**
建议：最多重试2次（同一批次），2次失败后把这批 Document 标记为 `failed`，记录原始 LLM Response 到 `processing_error` 字段，继续处理下一批。不要因为单批失败阻塞整个 Pipeline。

**Q2: 同一个 Document 被提取出3个 Aspect，其中1个 Aspect 写入 PostgreSQL 失败怎么办？**
建议：用事务，一个 Document 的所有 Aspect Mentions 要么全部成功，要么全部回滚。Document 状态不更新，等下次重跑。

**Q3: Milvus Upsert 失败但 PostgreSQL 已写入怎么办？**
建议：这是最棘手的不一致场景。处理方式：Milvus Upsert 失败时，**不更新** Document 状态（保持 `enriched`），下次 Pipeline 运行时，Stage 3 会重新对 `enriched` 状态的 Document 做 Embedding + Upsert。由于 Milvus 的 Upsert 是幂等的（相同 UUID 会覆盖），重跑安全。

**Q4: 本周的 week_id 如何确定？**
建议：`week_id = int(datetime.now().strftime('%Y%W'))`，即当前年份+周数。历史数据（Amazon McAuley 数据集的评论）统一用摄入时间的周数，不用评论原始时间。原因：保持 week_id 的一致性，简化 MVP 阶段的数据管理。
