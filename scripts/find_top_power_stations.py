# scripts/find_top_power_stations.py
# 不猜 ASIN，直接扫描数据集，找评论数最多的户外电源产品
# 输出 Top 20，我们从里面选

import json
from collections import defaultdict

REVIEW_FILE = (
    r"D:\codefield\voc-agent\data\raw\raw\review_categories\Patio_Lawn_and_Garden.jsonl"
)

# 统计每个 parent_asin 的评论数和元信息
parent_stats = defaultdict(
    lambda: {
        "count": 0,
        "ratings": [],
        "sample_title": "",
        "child_asins": set(),
    }
)

POWER_KEYWORDS = {
    "power station",
    "solar generator",
    "portable power",
    "jackery",
    "ecoflow",
    "bluetti",
    "anker solix",
    "goal zero",
    "yeti",
    "delta",
    "explorer",
    "powerhouse",
    "ac200",
    "eb",
}

print("扫描中（约3-5分钟）...")
with open(REVIEW_FILE, encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f):
        if i % 1_000_000 == 0 and i > 0:
            print(f"  {i:,} 行...")
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue

        # 用 title 过滤：只统计户外电源相关评论
        title = (r.get("title") or "").lower()
        text = (r.get("text") or "").lower()[:100]  # 只看前100字符提高性能

        combined = title + " " + text
        if not any(kw in combined for kw in POWER_KEYWORDS):
            continue

        parent = r.get("parent_asin", "")
        asin = r.get("asin", "")
        rating = r.get("rating")

        if not parent:
            continue

        s = parent_stats[parent]
        s["count"] += 1
        s["child_asins"].add(asin)
        if rating:
            s["ratings"].append(float(rating))
        if not s["sample_title"] and r.get("title"):
            s["sample_title"] = r["title"][:80]

# 排序输出 Top 25
print("\n" + "=" * 70)
print(f"{'排名':<4} {'评论数':>6} {'均分':>5} {'parent_asin':<14} {'样本标题'}")
print("=" * 70)

sorted_items = sorted(parent_stats.items(), key=lambda x: x[1]["count"], reverse=True)

for rank, (parent, s) in enumerate(sorted_items[:25], 1):
    avg = sum(s["ratings"]) / len(s["ratings"]) if s["ratings"] else 0
    child_list = ",".join(list(s["child_asins"])[:2])  # 最多显示2个child
    print(
        f"{rank:<4} {s['count']:>6} {avg:>5.1f}  {parent:<14} {s['sample_title'][:45]}"
    )
    print(f"     child示例: {child_list}")
    print()
