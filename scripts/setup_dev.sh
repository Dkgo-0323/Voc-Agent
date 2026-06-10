#!/bin/bash
# scripts/setup_dev.sh
# 首次开发环境搭建脚本

set -e  # 任意命令失败则退出

echo "=== VOC Agent 开发环境初始化 ==="

# 1. 复制 .env 文件
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ .env 文件已创建，请填写真实的 API Keys"
else
    echo "⏭️  .env 文件已存在，跳过"
fi

# 2. 安装 Python 依赖（uv）
echo "📦 安装 Python 依赖..."
uv sync

# 3. 安装 spaCy 英语模型（Presidio NLP 后端）
echo "📦 安装 spaCy 英语模型..."
uv run python -m spacy download en_core_web_lg

# 4. 启动 Docker 服务
echo "🐳 启动 Docker 服务..."
docker-compose up -d

# 5. 等待 PostgreSQL 就绪
echo "⏳ 等待 PostgreSQL 就绪..."
until docker exec voc_postgres pg_isready -U voc -d vocdb; do
    sleep 2
done
echo "✅ PostgreSQL 就绪"

# 6. 等待 Milvus 就绪
echo "⏳ 等待 Milvus 就绪..."
until curl -sf http://localhost:9091/healthz > /dev/null; do
    sleep 3
done
echo "✅ Milvus 就绪"

echo ""
echo "=== 环境初始化完成 ==="
echo "启动 API 服务：uv run uvicorn backend.app.main:app --reload --port 8000"
echo "健康检查：    curl http://localhost:8000/health"