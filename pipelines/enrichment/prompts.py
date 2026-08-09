"""Prompts and label contracts for aspect extraction."""

ASPECT_LABELS: dict[str, str] = {
    "battery_capacity": "battery life, usable capacity, and runtime",
    "charging_speed": "AC, DC, or solar charging speed",
    "solar_charging": "solar charging compatibility and performance",
    "ac_output_power": "AC output wattage and device support",
    "output_ports": "port types, count, placement, and usability",
    "build_quality": "materials, durability, and physical workmanship",
    "noise_level": "fan noise and quiet operation",
    "weight_portability": "weight, carrying, and portability",
    "thermal_management": "heat, cooling, and overheat protection",
    "display_interface": "display, buttons, and device controls",
    "app_connectivity": "mobile app, Bluetooth, Wi-Fi, and connectivity",
    "setup_complexity": "setup and first-use difficulty",
    "price_value": "price, value, and value for money",
    "customer_service": "support, returns, and service experience",
    "warranty_reliability": "warranty and long-term reliability",
    "camping_outdoor_use": "camping and outdoor use cases",
    "home_backup_use": "home backup and outage use cases",
    "van_rv_use": "van, RV, and vehicle use cases",
}

SYSTEM_PROMPT = f"""You are an expert analyst of portable power station reviews.
Extract product-related aspect mentions from each supplied review.

Choose aspect_label only from this exact list:
{chr(10).join(f'- {label}: {description}' for label, description in ASPECT_LABELS.items())}

Rules:
1. Return at most three aspects for each review, choosing the most important ones.
2. mention_text must be a direct excerpt from the review, no more than 60 characters.
3. context_window must contain surrounding review context, no more than 200 characters.
4. sentiment is exactly positive, negative, or neutral; confidence is 0.0 to 1.0.
5. Exclude reviews that only discuss delivery, packaging, or other non-product matters.
6. Return strict JSON only, using this shape:
{{"documents":[{{"document_id":"UUID", "aspects":[{{"aspect_label":"noise_level", "sentiment":"negative", "confidence":0.92, "mention_text":"fan is extremely loud", "context_window":"..."}}]}}]}}
"""


def build_user_prompt(documents: list[dict[str, str]]) -> str:
    """Format a batch without giving the model opportunities to change its contract."""
    items = "\n\n".join(
        f"Document ID: {document['document_id']}\nReview:\n{document['body']}"
        for document in documents
    )
    return f"Extract aspects for the following reviews:\n\n{items}"
