# pipelines/config/targets.py

REVIEW_FILE_PATH = r"data/raw/raw/review_categories/Patio_Lawn_and_Garden.jsonl"

# amazon_asins: [child_asin, parent_asin]
# loader 同时匹配两个字段，确保不丢评论
TARGETS = {
    "ecoflow-delta2": {
        "amazon_asins": ["B0B9XB57XM", "B0BNL7R3L1"],
        "reddit_keywords": ["ecoflow delta 2", "delta2", "ecoflow delta2"],
        "reddit_subreddits": ["SolarDIY", "preppers", "vandwellers", "camping"],
    },
    "jackery-explorer-1000": {
        "amazon_asins": ["B0BMQ9FGFS"],  # parent_asin直接用
        "reddit_keywords": ["jackery 1000", "jackery explorer 1000"],
        "reddit_subreddits": ["SolarDIY", "camping", "vandwellers"],
    },
    "jackery-explorer-300": {
        "amazon_asins": ["B082TMBYR6", "B0C7W65JP8"],
        "reddit_keywords": ["jackery 300", "jackery explorer 300"],
        "reddit_subreddits": ["SolarDIY", "camping", "overlanding"],
    },
    "jackery-explorer-240": {
        "amazon_asins": ["B09YM1BXKP"],  # parent_asin直接用
        "reddit_keywords": ["jackery 240", "jackery explorer 240"],
        "reddit_subreddits": ["SolarDIY", "camping", "overlanding"],
    },
    "anker-solix-f2000": {
        "amazon_asins": ["B09XM7WDZ2", "B0BP2DT79S"],
        "reddit_keywords": ["anker solix f2000", "anker 767", "solix f2000"],
        "reddit_subreddits": ["SolarDIY", "preppers", "homeimprovement"],
    },
}

LOCKED_SKU_CODES = frozenset(TARGETS)
