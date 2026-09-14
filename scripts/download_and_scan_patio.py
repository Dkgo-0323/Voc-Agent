# scripts/download_and_scan_patio.py
# 目标：下载 Patio_Lawn_and_Garden 品类，扫描目标 ASIN，输出命中报告

import gzip
import json
import os

from huggingface_hub import hf_hub_download, list_repo_files

TARGET_ASINS = {
    "B0B9XB57XM": "ecoflow-delta2",
    "B082TMBYR6": "jackery-explorer-300",
    "B0833FBN8B": "jackery-explorer-1000",
    "B09XM7WDZ2": "anker-solix-f2000",
    "B08MZJW943": "bluetti-ac200p",
}

REPO_ID = "McAuley-Lab/Amazon-Reviews-2023"
CATEGORY = "Patio_Lawn_and_Garden"
LOCAL_DIR = "data/raw"

# ── Step 1: 列出仓库文件，确认正确文件名 ──────────────────────────
print("=== 列出仓库中 Patio 相关文件 ===")
try:
    all_files = list(list_repo_files(REPO_ID, repo_type="dataset"))
    patio_files = [f for f in all_files if "Patio" in f and "review" in f.lower()]
    print("找到以下文件：")
    for f in patio_files:
        print(f"  {f}")
except Exception as e:
    print(f"列出文件失败: {e}")
    # 降级：直接猜文件名
    patio_files = [
        "raw_review_Patio_Lawn_and_Garden.jsonl",
        "raw_review_Patio_Lawn_and_Garden.jsonl.gz",
    ]
    print(f"降级使用预设文件名: {patio_files}")

# ── Step 2: 下载文件 ──────────────────────────────────────────────
local_path = None
os.makedirs(LOCAL_DIR, exist_ok=True)

for filename in patio_files:
    try:
        print(f"\n尝试下载: {filename}")
        local_path = hf_hub_download(
            repo_id=REPO_ID,
            filename=filename,
            repo_type="dataset",
            local_dir=LOCAL_DIR,
            local_dir_use_symlinks=False,
        )
        print(f"✅ 下载成功: {local_path}")
        break
    except Exception as e:
        print(f"❌ 失败: {str(e)[:120]}")

if not local_path:
    print("\n所有下载尝试均失败，请检查网络或手动下载")
    print(
        f"手动下载地址: https://huggingface.co/datasets/{REPO_ID}/resolve/main/raw_review_{CATEGORY}.jsonl"
    )
    exit(1)

# ── Step 3: 流式扫描，统计每个 ASIN 的命中情况 ──────────────────
print(f"\n=== 开始扫描: {local_path} ===")

# 命中统计结构
hits = {
    asin: {"sku": sku, "count": 0, "samples": []} for asin, sku in TARGET_ASINS.items()
}
total_lines = 0

open_func = gzip.open if local_path.endswith(".gz") else open

with open_func(local_path, "rt", encoding="utf-8", errors="ignore") as f:
    for line in f:
        total_lines += 1
        if total_lines % 200_000 == 0:
            found_count = sum(1 for v in hits.values() if v["count"] > 0)
            print(f"  进度: {total_lines:,} 行 | 已命中 SKU: {found_count}/5")

        try:
            review = json.loads(line)
        except json.JSONDecodeError:
            continue

        # 同时检查 asin 和 parent_asin
        for field in ("asin", "parent_asin"):
            asin_val = review.get(field, "")
            if asin_val in hits:
                hits[asin_val]["count"] += 1
                # 只保留前3条样本
                if len(hits[asin_val]["samples"]) < 3:
                    hits[asin_val]["samples"].append(
                        {
                            "rating": review.get("rating"),
                            "text": review.get("text", "")[:120],
                            "timestamp": review.get("timestamp"),
                            "matched_field": field,
                        }
                    )

# ── Step 4: 输出报告 ──────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"扫描完成 | 总行数: {total_lines:,}")
print(f"{'=' * 60}")

all_found = True
for asin, info in hits.items():
    status = "✅" if info["count"] > 0 else "❌"
    print(f"\n{status} {info['sku']} ({asin}): {info['count']} 条评论")
    for s in info["samples"]:
        print(f"   [{s['rating']}★ | {s['matched_field']}] {s['text'][:80]}...")
    if info["count"] == 0:
        all_found = False

print(f"\n{'=' * 60}")
if all_found:
    print("🎉 所有 5 个 ASIN 均已找到！可以开始写入 documents 表")
else:
    missing = [v["sku"] for v in hits.values() if v["count"] == 0]
    print(f"⚠️  以下 SKU 未找到：{missing}")
    print("建议：检查这些产品的 parent_asin（见方案C）或查看其他品类")
