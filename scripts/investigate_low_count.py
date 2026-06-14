import json

REVIEW_FILE = r"D:\codefield\voc-agent\data\raw\raw\review_categories\Patio_Lawn_and_Garden.jsonl"

# 这 3 个 ASIN 的名称映射
KNOWN_ASINS = {
    "B0B9XB57XM": "ecoflow-delta2",       # 191条，相对合理
    "B082TMBYR6": "jackery-explorer-300",  # 32条，偏少
    "B09XM7WDZ2": "anker-solix-f2000",     # 21条，偏少
}

found_parents = {}   # child → parent 的映射集合
child_counts = {}    # 动态统计这 3 个 child asin 自身在文件中的评论数
parent_counts = {}   # 全局统计所有 parent_asin 的总评论数

print("=== 分析已找到的 3 个 ASIN 的 parent_asin 分布 ===\n")

with open(REVIEW_FILE, "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f):
        if i % 1_000_000 == 0 and i > 0:
            print(f"  扫描进度: {i:,}")
        try:
            r = json.loads(line)
        except:
            continue

        asin   = r.get("asin", "")
        parent = r.get("parent_asin", "")

        # 修复逻辑漏洞：全局统计所有 parent_asin 的总评论数（包含该 parent 下的所有变体）
        if parent:
            parent_counts[parent] = parent_counts.get(parent, 0) + 1

        # 针对已知 ASIN 进行记录
        if asin in KNOWN_ASINS:
            if asin not in found_parents:
                found_parents[asin] = set()
            found_parents[asin].add(parent)

            # 动态统计当前 child 自身的评论数
            child_counts[asin] = child_counts.get(asin, 0) + 1

print("\n=== 结果 ===")
for asin, sku in KNOWN_ASINS.items():
    parents = found_parents.get(asin, set())
    current_child_count = child_counts.get(asin, 0)  # 获取当前 child 的实际评论数
    
    print(f"\n{sku} ({asin})")
    print(f"  当前 child 自身的实际评论数: {current_child_count}")
    print(f"  关联的 parent_asin: {parents}")
    
    for p in parents:
        total = parent_counts.get(p, 0)  # 全局 parent 总数（int）
        print(f"  parent [{p}] 下的总评论数 (包含所有变体): {total}")
        
        # 修复 TypeError：这里对比的双方 current_child_count 和 total 都是 int 类型
        if total > current_child_count:
            print(f"  ⚠️  parent 级别有更多评论（多了 {total - current_child_count} 条）！存在归集问题，应改用 parent_asin 过滤")