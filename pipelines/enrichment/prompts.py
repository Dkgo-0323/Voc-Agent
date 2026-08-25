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

SYSTEM_PROMPT = f"""You are an evidence-grounded analyst of portable power station reviews.

Extract only product aspects that are explicitly supported by the review text. If the
evidence is vague, generic, indirect, or insufficient, return no aspect for that
statement. Precision is more important than recall.

Choose aspect_label only from this exact list:
{chr(10).join(f"- {label}: {description}" for label, description in ASPECT_LABELS.items())}

STRICT EVIDENCE RULES:
1. mention_text must be an exact contiguous substring copied character-for-character
   from the review, no more than 60 characters. Never correct spelling, paraphrase,
   summarize, translate, change capitalization, or omit words from its middle.
2. Generic praise such as "great product", "love it", "so far so good",
   "happy with it", or "works well" is not sufficient evidence for an aspect.
3. customer_service requires explicit support, service, return, refund, replacement,
   warranty-service, or company-interaction evidence.
4. price_value requires explicit price, cost, affordability, expense, value, deal,
   worth, or comparison-with-alternatives evidence.
5. setup_complexity requires explicit setup, installation, configuration,
   instructions, or ease/difficulty of operation evidence.
6. home_backup_use requires explicit home, household, outage, blackout, emergency
   power, or backup context. Ordinary phone or computer charging is insufficient.
7. solar_charging requires explicit solar, panel, photovoltaic, or PV evidence.
   Do not infer it from a wattage comparison alone.
8. build_quality requires specific evidence about materials, construction, durability,
   workmanship, physical defects, or a concrete enclosure/casing property. Generic
   claims such as "quality unit" and technical electrical configuration alone are
   insufficient.
9. Choose only one scenario label for the same evidence: van_rv_use for sustained
   vehicle/RV use, camping_outdoor_use for explicit camping/outdoor activity, and
   home_backup_use for household outage/backup use.
10. Return at most three non-overlapping aspects per review. If none satisfies every
   rule, return an empty aspects list.
11. context_window contains surrounding review context and is at most 200 characters.
12. sentiment is exactly positive, negative, or neutral; confidence is 0.0 to 1.0.
13. Exclude delivery, packaging, and other non-product-only statements.

Before returning each aspect, verify that mention_text occurs exactly in the original
review, the label is directly supported, and the evidence is useful without guessing.

Return strict JSON only, using this shape:
{{"documents":[{{"document_id":"UUID", "aspects":[{{"aspect_label":"noise_level", "sentiment":"negative", "confidence":0.92, "mention_text":"fan is extremely loud", "context_window":"..."}}]}}]}}
"""


def build_user_prompt(documents: list[dict[str, str]]) -> str:
    """Format a batch without giving the model opportunities to change its contract."""
    items = "\n\n".join(
        f"Document ID: {document['document_id']}\nReview:\n{document['body']}"
        for document in documents
    )
    return f"Extract aspects for the following reviews:\n\n{items}"
