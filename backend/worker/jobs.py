# backend/worker/jobs.py
# Week 2 填充

async def run_enrichment_pipeline():
    """
    Week 2 实现：
    1. 从 documents 取未处理评论
    2. Aspect 抽取 + 情感分析
    3. 写入 aspect_mentions
    4. Embedding → Milvus upsert
    """
    raise NotImplementedError("Week 2 实现")