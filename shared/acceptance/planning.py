"""Offline, credential-free inventory for a proposed bounded acceptance run."""

from __future__ import annotations

from math import ceil
from typing import Any


def build_plan(
    *,
    documents: int = 30,
    chat_model: str | None = None,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    if not 1 <= documents <= 30:
        raise ValueError("Choose 1–30 public review documents")
    # A future runner must enforce these limits; this planner executes nothing.
    # Citation correction increments the router's same eight-round counter.
    vector_batches = ceil(documents * 3 / 64)
    inventory = [
        {
            "operation": "enrich_reviews",
            "chat": documents,
            "embedding": 0,
            "assumption": "at most one enrichment request/document; at most 3 mentions",
        },
        {
            "operation": "seed_and_repeat_seed",
            "chat": 0,
            "embedding": vector_batches * 2,
            "assumption": "two seeds; at most 64 texts/batch; at most 3 mentions/document",
        },
        {
            "operation": "api_startup_probe",
            "chat": 0,
            "embedding": 1,
            "assumption": "one API start; no worker; restarts require replanning",
        },
        {
            "operation": "five_ask_turns",
            "chat": 5 * 8,
            "embedding": 5 * 3,
            "assumption": "five turns; at most 8 model rounds and 3 RAG calls/turn",
        },
        {
            "operation": "report_generate_and_regenerate",
            "chat": 2,
            "embedding": 4,
            "assumption": "two generations; each uses one chat and two RAG embeddings",
        },
    ]
    chat = sum(item["chat"] for item in inventory)
    embedding = sum(item["embedding"] for item in inventory)
    return {
        "schema_version": 1,
        "mode": "offline-plan-only",
        "live_authorized": False,
        "documents": documents,
        "models": {
            "chat": chat_model,
            "embedding": embedding_model,
            "effective_configuration_checked": False,
        },
        "proposed_sdk_retries": 0,
        "proposed_enrichment_retries": 0,
        "inventory": inventory,
        "proposed_request_upper_bound": {
            "chat": chat,
            "embedding": embedding,
            "total": chat + embedding,
        },
        "enforced_by_runtime": False,
        "cost_cny": None,
        "reference_prices": {
            "accessed": "2026-10-22",
            "source": "https://docs.bigmodel.cn/cn/guide/start/pricing",
            "currency": "CNY",
            "per_million_tokens": {
                "glm-4-flashx-250414": {"input": "0.1", "output": "0.1"},
                "embedding-3": {"input": "0.5"},
            },
            "applies_to_effective_configuration": False,
        },
        "blockers": [
            "public source and local-use scope need confirmation; no reviews imported",
            "effective model/provider and current matching prices need confirmation",
            "token limits, request accounting and failure stops must be wired before live use",
            "existing enrichment retries/fallback and SDK retries do not satisfy this proposed bound",
            "real calls require separate explicit approval; an offline plan grants none",
        ],
        "excluded": [
            "live LLM judge",
            "scheduled jobs",
            "new scraping",
            "public hosting",
        ],
    }
