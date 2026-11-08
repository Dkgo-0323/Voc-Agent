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
    assert "response_format" not in completions.requests[0]


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
    model = OpenAIChatCompletionsModel(
        client,
        model="test-model",
        max_tokens=512,
        final_response_format={"type": "json_object"},
    )

    response = await model.complete(
        messages=[{"role": "user", "content": "answer"}], tools=[]
    )

    assert response.content == "Supported answer"
    assert response.cited_evidence_ids == ["520232f6-e99f-4bee-9f28-1a02751bb1ae"]
    assert "tools" not in completions.requests[0]
    assert "tool_choice" not in completions.requests[0]
    assert completions.requests[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_json_mode_is_enabled_when_tools_are_available() -> None:
    message = SimpleNamespace(
        content='{"answer":"你好","cited_evidence_ids":[],"answer_kind":"general_guidance"}',
        tool_calls=None,
    )
    client, completions = fake_client(message)
    model = OpenAIChatCompletionsModel(
        client,
        model="test-model",
        max_tokens=512,
        final_response_format={"type": "json_object"},
    )
    response = await model.complete(
        messages=[{"role": "user", "content": "你好"}],
        tools=[{"type": "function", "function": {"name": "tool_sql"}}],
    )
    assert response.answer_kind == "general_guidance"
    assert completions.requests[0]["response_format"] == {"type": "json_object"}
    assert completions.requests[0]["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_openai_adapter_rejects_non_string_or_non_list_structured_citations() -> (
    None
):
    content = '{"answer":"Supported answer","cited_evidence_ids":[123]}'
    message = SimpleNamespace(content=content, tool_calls=None)
    client, _ = fake_client(message)
    model = OpenAIChatCompletionsModel(client, model="test-model", max_tokens=512)

    response = await model.complete(
        messages=[{"role": "user", "content": "answer"}], tools=[]
    )

    assert response.content == content
    assert response.cited_evidence_ids == []
    assert response.requires_formatting is True


def test_plain_provider_answer_requests_format_repair() -> None:
    response = OpenAIChatCompletionsModel._parse_final_content("你好")
    assert response.content == "你好"
    assert response.requires_formatting is True
    assert response.answer_kind == "data_answer"


@pytest.mark.parametrize("kind", ["general_guidance", "data_answer"])
def test_structured_answer_kind_is_preserved(kind) -> None:
    import json

    response = OpenAIChatCompletionsModel._parse_final_content(
        json.dumps(
            {
                "answer": "I can help you explore customer feedback.",
                "cited_evidence_ids": [],
                "answer_kind": kind,
            }
        )
    )
    assert response.answer_kind == kind
    assert response.content == "I can help you explore customer feedback."


@pytest.mark.parametrize("kind", ["unknown", None, True, []])
def test_invalid_answer_kind_cannot_enable_direct_guidance(kind) -> None:
    import json

    response = OpenAIChatCompletionsModel._parse_final_content(
        json.dumps(
            {
                "answer": "Unsupported claim",
                "cited_evidence_ids": [],
                "answer_kind": kind,
            }
        )
    )
    assert response.answer_kind == "data_answer"
