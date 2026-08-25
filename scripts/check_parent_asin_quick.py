# scripts/check_parent_asin_quick.py
# 专门查 B0833FBN8B 和 B08MZJW943 的真实 parent_asin

import re
import time

import requests

CHECK_LIST = {
    "jackery-explorer-1000": "B0833FBN8B",
    "bluetti-ac200p": "B08MZJW943",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_parent_asin(asin: str) -> dict:
    url = f"https://www.amazon.com/dp/{asin}"
    resp = requests.get(url, headers=HEADERS, timeout=12)
    text = resp.text

    result = {"child_asin": asin, "parent_asin": None, "category": None}

    # 提取 parent_asin（多种模式兜底）
    for pattern in [
        r'"parent_asin"\s*:\s*"([A-Z0-9]{10})"',
        r"parent_asin['\"]?\s*:\s*['\"]([A-Z0-9]{10})['\"]",
        r'data-csa-c-item-id="([A-Z0-9]{10})"',
    ]:
        m = re.search(pattern, text)
        if m:
            result["parent_asin"] = m.group(1)
            break

    # 提取品类
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, "html.parser")
    bc = soup.select("#wayfinding-breadcrumbs_feature_div a")
    if bc:
        result["category"] = " > ".join(a.get_text(strip=True) for a in bc)

    return result


for sku, asin in CHECK_LIST.items():
    info = extract_parent_asin(asin)
    print(f"\n{sku} ({asin})")
    print(f"  parent_asin : {info['parent_asin']}")
    print(f"  category    : {info['category']}")
    if info["parent_asin"] and info["parent_asin"] != asin:
        print(f"  ⚠️  数据集应搜索 parent_asin: {info['parent_asin']}")
    time.sleep(2)
