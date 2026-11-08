"""Prompts and label contracts for aspect extraction."""

import json
import re

MAX_MENTION_LENGTH = 120

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

BASE_PROMPT = f"""You are an evidence-grounded analyst of portable power station reviews.

Extract only product aspects that are explicitly supported by the review text. If the
evidence is vague, generic, indirect, or insufficient, return no aspect for that
statement. Precision is more important than recall.

Choose aspect_label only from this exact list:
{chr(10).join(f"- {label}: {description}" for label, description in ASPECT_LABELS.items())}

STRICT EVIDENCE RULES:
1. mention_text must be an exact contiguous substring copied character-for-character
   from the review, no more than {MAX_MENTION_LENGTH} characters. Never correct spelling, paraphrase,
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
   power, or backup context. Power failure, power went out, or power came back on
   can establish a household outage when supported by actual appliance use or
   utility/weather context. A device's own power failure is not a household outage.
   Ordinary phone or computer charging is insufficient.
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
11. Set context_window to null. The application reconstructs surrounding context
    from the exact review excerpt; do not repeat review paragraphs in the response.
12. sentiment is exactly positive, negative, or neutral; confidence is 0.0 to 1.0.
13. Exclude delivery, packaging, and other non-product-only statements.

ASPECT-LEVEL SENTIMENT RULES:
- Assign sentiment to this specific aspect using the excerpt and its surrounding
  review context. Do not copy the overall review sentiment, star rating, or an
  opinion about a different aspect onto it.
- A factual duration, capacity, port count, or specification is neutral unless the
  reviewer evaluates that aspect or describes a clear benefit/problem. For example,
  "takes 7 to 8 hours to charge" alone is neutral; "charges too slowly" is negative.
- Buying something for a trip, planning to use it, or not having tried it yet does
  not establish satisfaction with that use. "I plan to use it for camping" alone
  is neutral. Praise for a home heating experience cannot make an untried camping
  scenario positive.
- Actual outcomes or explicit evaluation of the same aspect in surrounding text
  can support sentiment even when the excerpt itself states the intended use.
  For example, a camping purchase followed by "kept our phones charged throughout
  the trip" supports positive camping sentiment. A favorable assessment of port
  availability can be positive without claiming that every port was tested.
- The existence of a sale does not by itself prove good value. Tie price_value
  sentiment to an explicit assessment of price, affordability, or value. Do not
  silently resolve conflicting price opinions to positive.
- Preserve negation and conditions. Poor solar charging on cloudy days does not
  establish that the stated charging duration itself is too slow.
"""

COVERAGE_PROMPT = """
MULTI-ASPECT COVERAGE AND EVIDENCE SELECTION:
- Scan the ENTIRE review before selecting aspects. Do not stop after finding the
  first valid aspect or treat one aspect as a sufficient summary of the review.
- Independently check performance (runtime/capacity, charging, solar, supported
  loads), physical/interaction properties (noise, portability, heat, ports,
  construction, controls, app, setup), service/value/reliability, and actual use
  scenarios. Only select categories explicitly supported by this review.
- Return up to THREE DISTINCT aspect labels with separate evidence. When two or
  three independently supported aspects exist, include them instead of returning
  just one. Do not duplicate a label to describe several ports or repeat a scene.
  Never invent aspects to fill three slots. For more than three, prioritize
  concrete measured outcomes and explicit benefits/problems over purchase intent.
- A measured runtime, charging duration, or retained battery level is useful
  evidence even without praise or complaint. Preserve such facts with neutral
  sentiment unless the same aspect is explicitly evaluated in context.
- Select an excerpt that states what the product DID or how it performed, not
  merely a noun such as "power outage" or an earlier purchase intention when an
  actual outcome is available later in the review. Each excerpt should support
  its aspect and sentiment with as little inference as possible.
- Copy characters directly, including repeated spaces and punctuation. If a
  candidate is too long, choose a shorter CONTIGUOUS original clause; do not
  rewrite, stitch clauses together, or normalize whitespace.
- Before returning, check for an omitted independent fact, unsupported sentiment,
  duplicate label, or altered quote. An empty aspects list is appropriate only
  after checking all relevant categories and finding no useful supported aspect.
"""

EVIDENCE_CHECK_PROMPT = """
Before returning each aspect, verify that mention_text occurs exactly in the original
review, the label is directly supported, and the evidence is useful without guessing.
"""

SYSTEM_PROMPT = BASE_PROMPT + EVIDENCE_CHECK_PROMPT + """
Return strict JSON only, using this FLAT shape:
{"document_ids":["UUID"],"aspects":[{"document_id":"UUID","aspect_label":"noise_level","sentiment":"negative","confidence":0.92,"mention_text":"fan is extremely loud","context_window":null}]}
document_ids must list EVERY input document ID exactly once, including documents
with no supported aspects. Each aspect is one flat object with its document_id.
Do not nest aspects arrays inside document objects. Return at most three aspect
objects per document. For no supported evidence, include the ID but no aspect.
"""

SPAN_SYSTEM_PROMPT = BASE_PROMPT + COVERAGE_PROMPT + EVIDENCE_CHECK_PROMPT + """
EVIDENCE-ID MODE:
The input includes the original review and numbered contiguous original spans.
Inspect each numbered span independently for distinct useful aspects before
selecting up to three. Do not return only the first salient span.
Select only spans about THIS product, not the older batteries it replaced.
Prefer measured outcomes and direct evaluations over vague brand praise or a
purchase plan. A plain measurement is NEUTRAL, not an implicit compliment.
If more than three aspects qualify, prefer concrete performance measurements and
explicit benefits/problems, then other physical, service or scenario evidence.
Return evidence_id instead of writing mention_text or context_window. The code
copies the original text. Never invent or modify an evidence_id.
Return strict JSON:
{"document_ids":["UUID"],"aspects":[{"document_id":"UUID","evidence_id":"e0","aspect_label":"noise_level","sentiment":"negative","confidence":0.92}]}
List all input document IDs exactly once. Empty aspects is allowed only when none
of the numbered spans supplies specific product evidence. Do not force three items.
"""


def build_evidence_spans(body: str) -> list[dict[str, str | int]]:
    """Number literal clauses; preserve offsets and never normalize the source."""
    boundaries = list(re.finditer(
        r"<br\s*/?>|[.!?](?=\s|$)|[,;:]|\s+(?:and|but|while|although|because)\s+",
        body, re.I,
    ))
    ranges = []
    start = 0
    for boundary in boundaries:
        # Keep sentence punctuation; exclude HTML and conjunction separators.
        end = boundary.end() if boundary.group() in '.!?' else boundary.start()
        ranges.append((start, end))
        start = boundary.end()
    ranges.append((start, len(body)))
    spans = []
    for left, right in ranges:
        while left < right and body[left].isspace():
            left += 1
        while right > left and body[right - 1].isspace():
            right -= 1
        while left < right:
            end = min(right, left + MAX_MENTION_LENGTH)
            if end < right:
                space = body.rfind(' ', left, end)
                if space > left:
                    end = space
            if end > left:
                spans.append({'evidence_id': f'e{len(spans)}', 'start': left, 'end': end, 'text': body[left:end]})
            left = end
            while left < right and body[left].isspace():
                left += 1
    if len(spans) > 256:
        raise ValueError('Review has too many evidence spans')
    return spans


def build_user_prompt(documents: list[dict[str, str]]) -> str:
    """Format a batch without giving the model opportunities to change its contract."""
    items = "\n\n".join(
        f"Document ID: {document['document_id']}\nReview:\n{document['body']}"
        for document in documents
    )
    skeleton = json.dumps(
        {"document_ids": [item["document_id"] for item in documents], "aspects": []},
        separators=(",", ":"),
    )
    return (
        f"Extract aspects for the following reviews:\n\n{items}\n\n"
        "Fill the flat aspects array in this JSON skeleton. Preserve document_ids "
        "exactly, include document_id in each aspect, and return only valid JSON:\n"
        f"{skeleton}"
    )
