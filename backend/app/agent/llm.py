"""Small OpenAI-compatible function-calling adapter for the handwritten router."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] | str


@dataclass(frozen=True)
class ModelResponse:
    content: str | None = None
    tool_calls: list[ModelToolCall] = field(default_factory=list)
    cited_evidence_ids: list[str] = field(default_factory=list)


class ChatModelProtocol(Protocol):
    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse: ...


class OpenAIChatCompletionsModel:
    """Translate OpenAI-compatible chat completions into router-owned contracts."""

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        max_tokens: int,
        extra_body: dict[str, Any] | None = None,
        final_response_format: dict[str, str] | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._extra_body = extra_body or {}
        self._final_response_format = final_response_format

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        elif self._final_response_format:
            request["response_format"] = deepcopy(self._final_response_format)
        if self._extra_body:
            request["extra_body"] = self._extra_body
        response = await self._client.chat.completions.create(**request)
        message = response.choices[0].message
        tool_calls = [self._parse_tool_call(item) for item in message.tool_calls or []]
        if tool_calls:
            return ModelResponse(content=message.content, tool_calls=tool_calls)
        return self._parse_final_content(message.content)

    @staticmethod
    def _parse_tool_call(item: Any) -> ModelToolCall:
        raw_arguments = item.function.arguments or "{}"
        try:
            arguments = json.loads(raw_arguments)
        except (json.JSONDecodeError, TypeError):
            arguments = raw_arguments
        if not isinstance(arguments, dict):
            arguments = raw_arguments
        return ModelToolCall(
            call_id=item.id,
            name=item.function.name,
            arguments=arguments,
        )

    @staticmethod
    def _parse_final_content(content: str | None) -> ModelResponse:
        if not content:
            return ModelResponse()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return ModelResponse(content=content)
        if (
            not isinstance(parsed, dict)
            or set(parsed) != {"answer", "cited_evidence_ids"}
            or not isinstance(parsed.get("answer"), str)
            or not isinstance(parsed.get("cited_evidence_ids"), list)
            or not all(isinstance(item, str) for item in parsed["cited_evidence_ids"])
        ):
            return ModelResponse(content=content)
        return ModelResponse(
            content=parsed["answer"], cited_evidence_ids=parsed["cited_evidence_ids"]
        )
