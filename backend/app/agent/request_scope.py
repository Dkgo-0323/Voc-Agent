"""Conservative request constraints independent of the model's answer label."""

import re
from dataclasses import dataclass

ALIASES = {
    "ecoflow-delta2": r"delta[\s_-]*2(?![a-z0-9])|德尔塔\s*2(?![a-z0-9])",
    "jackery-explorer-1000": r"(?:jackery|explorer)\s*(?:explorer\s*)?1000(?![a-z0-9])",
    "jackery-explorer-300": r"(?:jackery|explorer)\s*(?:explorer\s*)?300(?![a-z0-9])",
    "jackery-explorer-240": r"(?:jackery|explorer)\s*(?:explorer\s*)?240(?![a-z0-9])",
    "anker-solix-f2000": r"f2000(?![a-z0-9])|anker\s*767(?![a-z0-9])",
}


@dataclass(frozen=True)
class RequestScope:
    skus: tuple[str, ...]
    data_request: bool
    time_requested: bool
    tools: frozenset[str]
    sentiment_requested: bool = False
    review_count_requested: bool = False


def resolve_scope(message: str, history) -> RequestScope:
    def products(text):
        return tuple(
            k
            for k, pattern in ALIASES.items()
            if k in text.lower() or re.search(pattern, text, re.I)
        )

    skus = products(message)
    relevant = message
    if not skus and re.search(
        r"它|这款|那款|这些反馈|\b(it|its|that product)\b", message, re.I
    ):
        for row in reversed(history):
            if row.role == "user" and products(row.content):
                skus = products(row.content)
                relevant += " " + row.content
                break
    # System usage/examples are not dataset requests merely because they name a product.
    usage = bool(
        re.search(
            r"举.*(?:例|问题)|提问示例|怎么(?:使用|用).*系统|如何(?:使用|用).*系统|how to use.*system",
            message,
            re.I,
        )
    )
    data = (
        bool(skus)
        and not usage
        and bool(
            re.search(
                r"多少|几条|数量|总数|统计|分布|趋势|比较|对比|怎么样|如何|评价|评论|反馈|口碑|喜欢|原话|续航|运行|小时|噪|充电|原文|证据|例子|查询|读取|how many|count|trend|compar|runtime|feedback|review|report",
                message,
                re.I,
            )
        )
    )
    tools = set()
    if data:
        if re.search(
            r"多少|几条|数量|总数|统计|分布|趋势|比较|对比|how many|count|trend|compar",
            message,
            re.I,
        ):
            tools.add("tool_sql")
        if re.search(
            r"怎么样|如何|评价|反馈|口碑|续航|噪|充电|原文|证据|例子|runtime|feedback|reviews? say",
            message,
            re.I,
        ) and (
            "tool_sql" not in tools
            or re.search(
                r"怎么样|评价|口碑|续航|原文|证据|例子|runtime|examples?|quotes?",
                message,
                re.I,
            )
        ):
            tools.add("tool_rag")
    return RequestScope(
        skus,
        data,
        bool(
            re.search(
                r"(?:19|20|21)\d{2}|\d+\s*(?:周|月|天)|本周|上周|这周|最近|去年|今年|上个月|本月|week|month|year|recent|last",
                relevant,
                re.I,
            )
        ),
        frozenset(tools),
        bool(
            re.search(
                r"正面|负面|中性|好评|差评|投诉|喜欢|满意|抱怨|positive|negative|neutral|complaint|praise",
                message,
                re.I,
            )
        ),
        bool(
            re.search(r"评论|评价|reviews?", message, re.I)
            and re.search(r"多少|几条|数量|总数|统计|how many|count", message, re.I)
        ),
    )


def constrain_arguments(scope: RequestScope, tool: str, arguments: dict) -> dict:
    args = dict(arguments)
    if scope.data_request and scope.skus and tool in {"tool_sql", "tool_rag"}:
        args["sku_codes"] = list(scope.skus)
        if not scope.time_requested:
            args.pop("week_range", None)
        if not scope.sentiment_requested:
            args.pop("sentiment", None)
    return args
