# scripts/find_parent_asin_from_metadata.py
# 从 HF 数据集的 metadata 文件查 parent_asin，不依赖 Amazon 页面

import json

from huggingface_hub import hf_hub_download, list_repo_files

TARGET_ASINS = {
    "B0B9XB57XM": "ecoflow-delta2",
    "B082TMBYR6": "jackery-explorer-300",
    "B0833FBN8B": "jackery-explorer-1000",
    "B09XM7WDZ2": "anker-solix-f2000",
    "B08MZJW943": "bluetti-ac200p",
}

REPO_ID = "McAuley-Lab/Amazon-Reviews-2023"
LOCAL_DIR = "data/raw"

# ── Step 1: 找 metadata 文件名 ────────────────────────────────────
print("=== 列出仓库中 Patio metadata 文件 ===")
all_files = list(list_repo_files(REPO_ID, repo_type="dataset"))

# metadata 文件通常命名为 meta_Patio_Lawn_and_Garden.jsonl
meta_files = [f for f in all_files if "Patio" in f and "meta" in f.lower()]
print("找到 metadata 文件：")
for f in meta_files:
    print(f"  {f}")

if not meta_files:
    print("未找到 Patio metadata 文件，列出所有文件供参考：")
    for f in sorted(all_files):
        print(f"  {f}")

# ── Step 2: 下载 metadata 文件 ────────────────────────────────────
meta_local = None
for filename in meta_files:
    try:
        print(f"\n下载: {filename}")
        meta_local = hf_hub_download(
            repo_id=REPO_ID,
            filename=filename,
            repo_type="dataset",
            local_dir=LOCAL_DIR,
            local_dir_use_symlinks=False,
        )
        print(f"✅ 下载成功: {meta_local}")
        break
    except Exception as e:
        print(f"❌ 失败: {str(e)[:100]}")

if not meta_local:
    print("metadata 文件下载失败，退出")
    exit(1)

# ── Step 3: 扫描 metadata，建立 child_asin → parent_asin 映射 ────
print("\n=== 扫描 metadata 文件 ===")

# 收集两个方向的映射
child_to_parent = {}  # child_asin  → parent_asin
parent_to_info = {}  # parent_asin → {title, brand, child_asins}

target_set = set(TARGET_ASINS.keys())
lines_scanned = 0

with open(meta_local, encoding="utf-8", errors="ignore") as f:
    for line in f:
        lines_scanned += 1
        if lines_scanned % 500_000 == 0:
            print(f"  进度: {lines_scanned:,} 行")
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        parent = item.get("parent_asin", "")
        asin = item.get("asin", parent)  # 有些 metadata 没有单独的 asin 字段

        # 记录映射
        if asin:
            child_to_parent[asin] = parent
        if parent:
            child_to_parent[parent] = parent  # parent 映射到自身

        # 如果命中目标
        for check in [asin, parent]:
            if check in target_set:
                parent_to_info[parent] = {
                    "title": item.get("title", ""),
                    "brand": item.get("brand", ""),
                    "child_asin": asin,
                    "matched_via": check,
                }

print(f"\n扫描完成，共 {lines_scanned:,} 行")

# ── Step 4: 输出结果 ──────────────────────────────────────────────
print(f"\n{'=' * 60}")
print("=== ASIN 映射结果 ===")

found_parents = {}
for target_asin, sku in TARGET_ASINS.items():
    parent = child_to_parent.get(target_asin)
    in_meta = target_asin in parent_to_info or (parent and parent in parent_to_info)

    print(f"\n{sku} ({target_asin})")
    print(f"  parent_asin  : {parent or '未找到'}")
    print(f"  在metadata中 : {'✅' if in_meta else '❌'}")

    if parent and parent in parent_to_info:
        info = parent_to_info[parent]
        print(f"  品牌         : {info['brand']}")
        print(f"  标题         : {info['title'][:80]}")

    if parent and parent != target_asin:
        print(f"  ⚠️  应使用 parent_asin [{parent}] 重新扫描 review 文件")
        found_parents[sku] = parent
    elif parent == target_asin:
        print("  ✅ 已是 parent_asin，review 文件中应能直接找到")

# 输出需要用 parent_asin 重新搜索的列表
if found_parents:
    print(f"\n{'=' * 60}")
    print("需要用以下 parent_asin 重新扫描 review 文件：")
    for sku, p_asin in found_parents.items():
        print(f"  {sku}: {p_asin}")
