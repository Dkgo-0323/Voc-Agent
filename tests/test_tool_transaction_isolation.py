from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.agent.router import ToolBinding
from backend.app.agent.schemas import AnalyticsToolArguments, ToolName, ToolStatus
from backend.app.api.ask import isolated_tool


class Savepoint:
    def __init__(self):
        self.rollback = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["returned_error", "raised_exception", "success"])
async def test_tool_savepoint_rollback_keeps_chat_transaction_usable(failure):
    savepoint = Savepoint()
    db = SimpleNamespace(begin_nested=lambda: savepoint)

    async def execute(args):
        if failure == "raised_exception":
            raise RuntimeError("query failed")
        return SimpleNamespace(
            status=ToolStatus.ERROR
            if failure == "returned_error"
            else ToolStatus.SUCCESS
        )

    tool = isolated_tool(
        ToolBinding(ToolName.SQL, "counts", AnalyticsToolArguments, execute), db
    )
    args = AnalyticsToolArguments(operation="review_count")
    if failure == "raised_exception":
        with pytest.raises(RuntimeError):
            await tool.executor(args)
    else:
        await tool.executor(args)
    assert savepoint.rollback.await_count == (0 if failure == "success" else 1)
