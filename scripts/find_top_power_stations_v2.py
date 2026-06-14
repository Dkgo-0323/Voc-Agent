# scripts/find_top_power_stations_v2.py
# 正确方案：先从 metadata 找电源产品，再统计 review 数量

from huggingface_hub import hf_hub_download, list_repo_files
import json
from collections import defaultdict

REPO_ID   = "McAuley-Lab/Amazon-Reviews-2023"
LOCAL_DIR = "data/raw"

REVIEW_FILE = r"D:\codefield\voc-agent\data\raw\raw\review_categories\Patio_Lawn_and_Garden.jsonl"

# ── Step 1: 找并下载 Patio metadata 文件 ─────────────────────────
print("=== Step 1: 获取 metadata 文件 ===")
all_files = list(list_repo_files(REPO_ID, repo_type="dataset"))

# 打印所有文件名供参考，找 meta 相关的
meta_candidates = [f for f in all_files if "Patio" in f]
print("Patio 相关文件：")
for f in meta_candidates:
    print(f"  {f}")

meta_file_path = None
meta_keywords  = ["meta", "Meta", "metadata", "item"]

for f in meta_candidates:
    if any(kw in f for kw in meta_keywords):
        try:
            print(f"\n下载: {f}")
            meta_file_path = hf_hub_download(
                repo_id=REPO_ID,
                filename=f,
                repo_type="dataset",
                local_dir=LOCAL_DIR,
                local_dir_use_symlinks=False,
            )
            print(f"✅ 下载成功: {meta_file_path}")
            break
        except Exception as e:
            print(f"❌ 失败: {str(e)[:80]}")

if not meta_file_path:
    print("\n⚠️  未找到 metadata 文件，尝试直接猜文件名...")
    for fname in [
        "raw/meta_categories/Patio_Lawn_and_Garden.jsonl",
        "meta_Patio_Lawn_and_Garden.jsonl",
        "raw/meta_Patio_Lawn_and_Garden.jsonl",
    ]:
        try:
            meta_file_path = hf_hub_download(
                repo_id=REPO_ID,
                filename=fname,
                repo_type="dataset",
                local_dir=LOCAL_DIR,
                local_dir_use_symlinks=False,
            )
            print(f"✅ 下载成功: {meta_file_path}")
            break
        except:
            pass

if not meta_file_path:
    print("❌ 无法获取 metadata 文件，退出")
    exit(1)

# ── Step 2: 扫描 metadata，提取电源产品 parent_asin ──────────────
print(f"\n=== Step 2: 扫描 metadata，找电源产品 ===")

POWER_BRANDS = {
    "jackery", "ecoflow", "bluetti", "anker", "goal zero",
    "goalzero", "rockpals", "pecron", "vtoman", "fossibot",
    "allpowers", "growatt", "zendure", "powerwin", "oupes",
}

POWER_TITLE_KEYWORDS = {
    "power station", "solar generator", "portable power",
    "power house", "powerhouse", "solar power",
    "battery station", "power bank station",
    "generator station", "lifepo4 station",
}

power_asins = {}  # parent_asin → {title, brand, capacity_hint}

lines = 0
with open(meta_file_path, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        lines += 1
        if lines % 200_000 == 0:
            print(f"  进度: {lines:,} 行，已找到电源产品: {len(power_asins)}")
        try:
            item = json.loads(line)
        except:
            continue

        parent = item.get("parent_asin", "")
        title  = (item.get("title")  or "").lower()
        brand  = (item.get("brand")  or "").lower()

        if not parent:
            continue

        # 品牌匹配 或 标题关键词匹配
        brand_hit = any(b in brand for b in POWER_BRANDS)
        title_hit = any(kw in title for kw in POWER_TITLE_KEYWORDS)

        if brand_hit or title_hit:
            # 从标题提取容量信息
            capacity = ""
            import re
            cap_match = re.search(r'(\d{3,4})\s*wh', title)
            if cap_match:
                capacity = cap_match.group(1) + "Wh"

            power_asins[parent] = {
                "title":    item.get("title", "")[:80],
                "brand":    item.get("brand", ""),
                "capacity": capacity,
                "child_asins": set(),
            }

print(f"\n扫描完成，共 {lines:,} 行")
print(f"找到电源产品 parent_asin: {len(power_asins)} 个")

# ── Step 3: 扫描 review 文件，统计这些 parent_asin 的评论数 ───────
print(f"\n=== Step 3: 统计电源产品评论数 ===")

review_counts = defaultdict(lambda: {"count": 0, "ratings": []})

with open(REVIEW_FILE, "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f):
        if i % 2_000_000 == 0 and i > 0:
            print(f"  进度: {i:,} 行...")
        try:
            r = json.loads(line)
        except:
            continue

        parent = r.get("parent_asin", "")
        asin   = r.get("asin", "")
        rating = r.get("rating")

        if parent in power_asins:
            review_counts[parent]["count"] += 1
            power_asins[parent]["child_asins"].add(asin)
            if rating:
                review_counts[parent]["ratings"].append(float(rating))

# ── Step 4: 排序输出 ──────────────────────────────────────────────
print(f"\n{'='*80}")
print(f"{'排名':<4} {'评论数':>6} {'均分':>5} {'容量':>8}  {'品牌':<12} {'parent_asin':<14} 产品名")
print(f"{'='*80}")

results = []
for parent, info in power_asins.items():
    cnt  = review_counts[parent]["count"]
    rats = review_counts[parent]["ratings"]
    avg  = sum(rats) / len(rats) if rats else 0.0
    results.append((parent, info, cnt, avg))

results.sort(key=lambda x: x[2], reverse=True)

for rank, (parent, info, cnt, avg) in enumerate(results[:30], 1):
    child_sample = ",".join(list(info["child_asins"])[:2])
    cap = info["capacity"] or "未知"
    print(f"{rank:<4} {cnt:>6} {avg:>5.1f} {cap:>8}  "
          f"{info['brand'][:10]:<12} {parent:<14} {info['title'][:40]}")
    if child_sample:
        print(f"     child示例: {child_sample}")
    print()

# ── Step 5: 额外验证我们已有的3个 SKU ────────────────────────────
print(f"\n{'='*80}")
print("=== 已确认 SKU 在 metadata 中的信息 ===")
OUR_PARENTS = {
    "B0BNL7R3L1": "ecoflow-delta2",
    "B0C7W65JP8": "jackery-explorer-300",
    "B0BP2DT79S": "anker-solix-f2000",
}
for parent, sku in OUR_PARENTS.items():
    cnt = review_counts[parent]["count"]
    info = power_asins.get(parent, {})
    print(f"  {sku}: {cnt} 条 | {info.get('title','未在metadata中')}")