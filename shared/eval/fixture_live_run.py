"""Run all Golden fixture observations through the configured structured judge."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from openai import AsyncOpenAI

from backend.app.agent.llm import OpenAIChatCompletionsModel
from backend.app.core.settings import settings
from shared.eval.fixture_execution import fixture_executor
from shared.eval.rag_eval import (
    StructuredLlmJudge,
    render_summary,
    run_dataset,
    write_report,
)


def _api_key() -> str:
    if settings.llm_api_key:
        return settings.llm_api_key
    if settings.llm_base_url.rstrip("/") == settings.embedding_base_url.rstrip("/"):
        return settings.embedding_api_key
    return settings.openai_api_key


async def run(output: Path) -> int:
    client = AsyncOpenAI(
        api_key=_api_key(),
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    try:
        model = OpenAIChatCompletionsModel(
            client,
            model=settings.llm_model,
            max_tokens=400,
            extra_body=settings.llm_extra_body,
            final_response_format=(
                {"type": "json_object"}
                if "bigmodel.cn" in settings.llm_base_url.rstrip("/").lower()
                else None
            ),
        )
        report = await run_dataset(fixture_executor, judge=StructuredLlmJudge(model))
        write_report(report, output)
        print(render_summary(report))
        return 0 if report.overall_passed else 2
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all VOC fixture cases with live LLM judging")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(run(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
