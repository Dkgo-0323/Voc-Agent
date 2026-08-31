from types import SimpleNamespace

import pytest

from backend.app.agent.llm import OpenAIChatCompletionsModel


class FakeCompletions:
    def __init__(self, message) -> None:
        self.message = message
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.message)])


def fake_client(message):
    completions = FakeCompletions(message)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


@pytest.mark.asyncio
async def test_openai_adapter_parses_function_call_arguments() -> None:
    message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(
                    name="tool_sql",
                    arguments='{"operation":"review_count"}',
                ),
            )
        ],
    )
    client, completions = fake_client(message)
    model = OpenAIChatCompletionsModel(
        client, model="test-model", max_tokens=512, extra_body={"temperature": 0}
    )

    response = await model.complete(
        messages=[{"role": "user", "content": "count"}],
        tools=[{"type": "function", "function": {"name": "tool_sql"}}],
    )

    assert response.tool_calls[0].arguments == {"operation": "review_count"}
    assert completions.requests[0]["tool_choice"] == "auto"
    assert completions.requests[0]["extra_body"] == {"temperature": 0}


@pytest.mark.asyncio
async def test_openai_adapter_parses_structured_final_answer_and_citations() -> None:
    message = SimpleNamespace(
        content=(
            '{"answer":"Supported answer",'
            '"cited_evidence_ids":["520232f6-e99f-4bee-9f28-1a02751bb1ae"]}'
        ),
        tool_calls=None,
    )
    client, completions = fake_client(message)
    model = OpenAIChatCompletionsModel(client, model="test-model", max_tokens=512)

    response = await model.complete(
        messages=[{"role": "user", "content": "answer"}], tools=[]
    )

    assert response.content == "Supported answer"
    assert response.cited_evidence_ids == ["520232f6-e99f-4bee-9f28-1a02751bb1ae"]
    assert "tools" not in completions.requests[0]
    assert "tool_choice" not in completions.requests[0]
