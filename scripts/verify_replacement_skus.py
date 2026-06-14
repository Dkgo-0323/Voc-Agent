# scripts/verify_replacement_skus.py
# 快速验证替换 SKU 的评论数，同时输出最终 TARGET_ASINS 配置

import json

REVIEW_FILE = r"D:\codefield\voc-agent\data\raw\raw\review_categories\Patio_Lawn_and_Garden.jsonl"

# 同时验证替换候选 + 建立完整 parent_asin 映射
CHECK_ASINS = {
    # 已确认保留（用 parent_asin）
    "B0BNL7R3L1": "ecoflow-delta2 [parent]",
    "B0C7W65JP8": "jackery-explorer-300 [parent]",
    "B0BP2DT79S": "anker-solix-f2000 [parent]",

    # 替换候选
    "B0B4HWXRQK": "jackery-explorer-1000-pro [候选]",  # Jackery 1000 Pro
    "B09MTQFNFQ": "bluetti-ac200max [候选]",            # Bluetti AC200MAX
    "B09JQFLN1M": "ecoflow-delta-pro [备选]",           # EcoFlow Delta Pro

    # 同时查这些 child asin，确认 parent 映射正确
    "B0B9XB57XM": "ecoflow-delta2 [child验证]",
    "B082TMBYR6": "jackery-explorer-300 [child验证]",
    "B09XM7WDZ2": "anker-solix-f2000 [child验证]",
}

counts = {asin: 0 for asin in CHECK_ASINS}
parent_map = {}  # child → parent (顺便收集)

print("扫描中，约需 3-5 分钟...")
with open(REVIEW_FILE, "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f):
        if i % 1_000_000 == 0 and i > 0:
            print(f"  {i:,} 行...")
        try:
            r = json.loads(line)
        except:
            continue

        asin   = r.get("asin", "")
        parent = r.get("parent_asin", "")

        for check in [asin, parent]:
            if check in counts:
                counts[check] += 1

        # 顺便记录新候选的 parent
        if asin in CHECK_ASINS:
            parent_map[asin] = parent
        if parent in CHECK_ASINS:
            parent_map[parent] = parent  # parent 映射自身

print("\n" + "="*60)
print("=== 验证结果 ===\n")

print("【已确认保留的 SKU（用 parent_asin）】")
for asin in ["B0BNL7R3L1", "B0C7W65JP8", "B0BP2DT79S"]:
    print(f"  {counts[asin]:>4} 条  {asin}  {CHECK_ASINS[asin]}")

print("\n【替换候选 SKU】")
for asin in ["B0B4HWXRQK", "B09MTQFNFQ", "B09JQFLN1M"]:
    c = counts[asin]
    status = "✅ 可用" if c >= 30 else ("⚠️ 偏少" if c > 0 else "❌ 无数据")
    print(f"  {c:>4} 条  {asin}  {CHECK_ASINS[asin]}  {status}")
    if asin in parent_map and parent_map[asin] != asin:
        print(f"           → parent: {parent_map[asin]}")

print("\n【child asin 验证（应与 parent 数量一致或接近）】")
for asin in ["B0B9XB57XM", "B082TMBYR6", "B09XM7WDZ2"]:
    print(f"  {counts[asin]:>4} 条  {asin}  {CHECK_ASINS[asin]}")