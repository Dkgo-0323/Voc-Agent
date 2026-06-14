# scripts/check_amazon_category.py
# 不需要任何API，直接解析亚马逊公开页面的面包屑

import requests
from bs4 import BeautifulSoup
import time

ASINS = {
    "ecoflow-delta2": "B0B9XB57XM",
    "jackery-explorer-300": "B082TMBYR6",
    "jackery-explorer-1000": "B0833FBN8B",
    "anker-solix-f2000": "B09XM7WDZ2",
    "bluetti-ac200p": "B08MZJW943",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def get_amazon_category(asin: str) -> str:
    url = f"https://www.amazon.com/dp/{asin}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 方法1：面包屑导航
        breadcrumb = soup.select("#wayfinding-breadcrumbs_feature_div a")
        if breadcrumb:
            return " > ".join(a.get_text(strip=True) for a in breadcrumb)
        
        # 方法2：Best Sellers Rank 区域
        bsr = soup.find("tr", {"class": "po-product_site_launch_date"})  
        rank_section = soup.find(id="SalesRank")
        if rank_section:
            return rank_section.get_text(strip=True)[:200]
            
        return "未找到品类信息"
    except Exception as e:
        return f"请求失败: {e}"

for sku, asin in ASINS.items():
    category = get_amazon_category(asin)
    print(f"\n{sku} ({asin}):")
    print(f"  品类: {category}")
    time.sleep(2)  # 避免触发反爬