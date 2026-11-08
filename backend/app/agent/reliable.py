"""Bounded business queries and evidence-based presentation for the chat UI."""

from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta

from backend.app.agent.evidence_integrity import sentiment_label_conflict
from backend.app.agent.request_scope import resolve_scope
from backend.app.agent.router import FunctionCallingRouter
from backend.app.agent.schemas import (
    AgentExecutionMetadata,
    AgentRunResult,
    AgentStatus,
    AnalyticsToolArguments,
    RagToolArguments,
    ToolCallTrace,
    ToolCompletedEvent,
    ToolError,
    ToolExecutionMetadata,
    ToolName,
    ToolStartedEvent,
    ToolStatus,
    WeekRange,
)
from backend.app.agent.tool_rag import build_answer_citations

NAMES = {
    "ecoflow-delta2": "EcoFlow Delta 2",
    "jackery-explorer-1000": "Jackery Explorer 1000",
    "jackery-explorer-300": "Jackery Explorer 300",
    "jackery-explorer-240": "Jackery Explorer 240",
    "anker-solix-f2000": "Anker Solix F2000",
}
ASPECTS = {
    "battery_capacity": "电池与续航",
    "charging_speed": "充电速度",
    "solar_charging": "太阳能充电",
    "ac_output_power": "交流输出",
    "output_ports": "输出接口",
    "build_quality": "做工质量",
    "noise_level": "噪声",
    "weight_portability": "重量与便携性",
    "thermal_management": "散热",
    "display_interface": "显示与操作",
    "app_connectivity": "应用连接",
    "setup_complexity": "设置",
    "price_value": "性价比",
    "customer_service": "售后",
    "camping_outdoor_use": "露营使用",
    "home_backup_use": "家庭备用电源",
    "van_rv_use": "房车使用",
}
SENTIMENTS = {"positive": "正面", "negative": "负面", "neutral": "中性"}


def period(message):
    """Resolve explicit ISO weeks. Ambiguous time requests require clarification."""
    match = re.search(r"(\d{4})\s*年?\s*(?:第|W|年第)?\s*(\d{1,2})\s*周", message, re.I)
    if match:
        year, week = map(int, match.groups())
        date.fromisocalendar(year, week, 1)
        return WeekRange(start_week_id=year * 100 + week, end_week_id=year * 100 + week)
    match = re.search(r"\b(20\d{2})(\d{2})\b", message)
    if match:
        year, week = map(int, match.groups())
        date.fromisocalendar(year, week, 1)
        return WeekRange(start_week_id=year * 100 + week, end_week_id=year * 100 + week)
    return None


def render_analytics(payload):
    """Keep all numbers, denominators and ISO week dates out of free generation."""
    if payload is None:
        return ""
    data = payload.model_dump(mode="json")
    operation = data.get("operation")
    if operation == "review_count":
        rows = [
            f"{NAMES.get(r['sku_code'], r['sku_code'])}：{r['review_count']} 条评论，{r['mention_count']} 次方面提及。"
            for r in data["by_sku"]
        ]
        return (
            "本系统按现有产品归档、符合质量条件的去重评论（不是平台总评论量）：\n"
            + "\n".join(rows)
        )
    if operation == "sentiment_distribution":
        return f"共 {data['mention_count']} 次方面提及，按提及数计算：\n" + "\n".join(
            f"{SENTIMENTS.get(r['sentiment'], r['sentiment'])}：{r['mention_count']} 次，{r['proportion']:.1%}。"
            for r in data["distribution"]
        )
    if operation == "aspect_distribution":
        return (
            "各方面的反馈分布（按现有归档情绪标签与提及计数，不代表独立评论数）：\n"
            + "\n".join(
                f"{ASPECTS.get(r['aspect_label'], r['aspect_label'])}：{r['mention_count']} 次，正面 {r['positive_count']}、负面 {r['negative_count']}、中性 {r['neutral_count']}。"
                for r in data["distribution"]
            )
        )
    if operation in {"trend", "aspect_trend"}:
        rows = []
        for r in data["points"]:
            year, week = divmod(r["week_id"], 100)
            start = date.fromisocalendar(year, week, 1)
            rows.append(
                f"{year} 年第 {week} 周（{start.isoformat()} 至 {(start + timedelta(days=6)).isoformat()}）：{r['review_count']} 条评论、{r['mention_count']} 次提及，其中负面 {r['negative_count']} 次，负面提及率 {r['negative_rate']:.2%}。"
            )
        return "按 ISO 周统计；比例的分母为方面提及数：\n" + "\n".join(rows)
    if "skus" in data:
        return "同容量档位比较，负面率按方面提及数计算：\n" + "\n".join(
            f"{NAMES.get(r['sku_code'], r['sku_code'])}：{r['review_count']} 条评论、{r['mention_count']} 次提及，负面 {r['negative_count']} 次（{r['negative_rate']:.2%}）。"
            for r in data["skus"]
        )
    return ""


def evidence_quote(item, runtime=False):
    """Use complete source sentences, preserving units and conditions."""
    text = re.sub(r"<br\s*/?>", "\n", item.source.review_text or "", flags=re.I)
    if runtime:
        for paragraph in text.splitlines():
            if (
                re.search(r"\b(hours?|all day|overnight)\b", paragraph, re.I)
                and re.search(
                    r"\b(ran|run|powering|using|used|allows)\b", paragraph, re.I
                )
                and len(paragraph) <= 1600
            ):  # complete source paragraph
                sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
                for index, sentence in enumerate(sentences):
                    if re.search(
                        r"\b(hours?|all day|overnight)\b", sentence, re.I
                    ) and re.search(
                        r"\b(ran|run|powering|using|used|allows)\b", sentence, re.I
                    ):
                        following = [
                            s
                            for s in sentences[index + 1 : index + 3]
                            if re.search(r"charge|battery|\d|wifi", s, re.I)
                        ]
                        return " ".join([sentence, *following])
                return paragraph.strip()
        return None
    # The hydrated mention is verified against the complete original review.
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    for sentence in sentences:
        if item.mention_text in sentence and len(sentence) <= 1000:
            return sentence.strip()
    return item.mention_text


class ReliableVocRouter:
    def __init__(self, model, bindings, *, system_policy):
        self._model = model
        self._bindings = {b.name.value: b for b in bindings}
        self._legacy = FunctionCallingRouter(
            model, bindings, system_policy=system_policy
        )

    async def run(self, *, recent_messages, current_user_message, event_sink=None):
        message = current_user_message.strip()
        scope = resolve_scope(message, recent_messages)
        traces, warnings, parts, selected = [], [], [], []
        failed = False

        def finish(text=None, status=None):
            answer = text or "\n\n".join(parts)
            return AgentRunResult(
                status=status
                or (AgentStatus.PARTIAL if failed else AgentStatus.SUCCESS),
                final_answer=answer,
                citations=build_answer_citations(
                    selected, [e.mention_id for e in selected]
                ),
                warnings=warnings,
                tool_trace=traces,
                execution=AgentExecutionMetadata(
                    model_round_count=0,
                    attempted_tool_call_count=len(traces),
                    executed_tool_call_count=len(traces),
                    maximum_tool_calls=3,
                ),
            )

        async def call(name, args):
            nonlocal failed
            if len(traces) >= 3 or name not in self._bindings:
                failed = True
                return None
            call_id = f"voc-{len(traces) + 1}"
            if event_sink:
                await event_sink(
                    ToolStartedEvent(call_id=call_id, tool_name=ToolName(name))
                )
            try:
                async with asyncio.timeout(35):
                    result = await self._bindings[name].executor(args)
                trace = ToolCallTrace(
                    call_id=call_id,
                    tool_name=name,
                    arguments=args.model_dump(mode="json"),
                    normalized_arguments=result.normalized_args.model_dump(mode="json"),
                    executed=True,
                    status=result.status,
                    warnings=result.warnings,
                    error=result.error,
                    duration_ms=result.execution.duration_ms,
                    result_count=result.execution.result_count,
                )
                warnings.extend(result.warnings)
            except Exception:
                failed = True
                trace = ToolCallTrace(
                    call_id=call_id,
                    tool_name=name,
                    arguments=args.model_dump(mode="json"),
                    normalized_arguments=args.model_dump(mode="json"),
                    executed=True,
                    status=ToolStatus.ERROR,
                    error=ToolError(
                        code="query_unavailable",
                        message="本次查询暂时未完成，请稍后重试。",
                        retryable=True,
                    ),
                )
                result = None
            traces.append(trace)
            if event_sink:
                await event_sink(
                    ToolCompletedEvent(
                        call_id=call_id,
                        tool_name=ToolName(name),
                        status=trace.status,
                        execution=ToolExecutionMetadata(
                            result_count=trace.result_count,
                            duration_ms=trace.duration_ms,
                        ),
                        warnings=trace.warnings,
                    )
                )
            if trace.status == ToolStatus.ERROR:
                failed = True
            return result

        if re.search(r"编造|假(?:的|造).*原文|fake.*review", message, re.I):
            return finish(
                "我不能编造评论数量或用户原文。你可以直接问产品的真实反馈，我会查询现有数据并给出依据。",
                AgentStatus.ABSTAINED,
            )
        if message in {"你好", "您好", "hello", "hi"}:
            return finish(
                "你好！你可以告诉我关心的产品和问题，例如“EcoFlow Delta 2 的续航反馈怎么样？”"
            )
        if re.search(r"评论数.*提及数|提及数.*评论数", message) and not scope.skus:
            return finish(
                "评论数是本系统符合分析条件的独立评论数量，按评论去重。提及数是从这些评论中抽取并通过质量筛选的方面反馈数量；一条评论可以包含多个方面提及，因此两者通常不同。正负面提及率按提及数计算，不能当成正负面评论比例。"
            )
        if (
            re.search(r"你.*做什么|你能做什么|怎么使用|怎么用|如何使用", message)
            and not scope.data_request
        ):
            return finish(
                "我帮助你分析便携式电源的客户反馈，包括评论数量、优缺点、趋势和产品比较。\n直接输入例如“EcoFlow Delta 2 有多少条评论，续航反馈怎么样？”即可，也可以继续追问“它的噪声呢？”。结论以本系统已收集的数据为限。"
            )
        if re.search(r"哪个最好|哪款最好", message) and not scope.skus:
            return finish(
                "你希望比较哪些产品，更关注负面反馈率、续航还是其他方面？明确范围后，我会结合样本量比较。"
            )

        catalog = bool(
            re.search(r"哪些产品|几款产品|产品目录|能分析哪些|能看哪些", message)
        )
        unknown_data = not scope.skus and bool(
            re.search(r"多少.*评论|评论.*多少|用户反馈|产品评价", message)
        )
        if catalog or unknown_data:
            result = await call(
                "tool_sql",
                AnalyticsToolArguments(operation="review_count", sku_codes=[]),
            )
            if result and result.payload:
                if unknown_data and not catalog:
                    parts.append(
                        "已核对当前产品目录，未能把你提到的名称匹配到已启用产品。请确认名称或从下列产品中选择："
                    )
                parts.append(render_analytics(result.payload))
                return finish(
                    status=AgentStatus.ABSTAINED
                    if unknown_data and not catalog
                    else None
                )
            return finish("当前未能取得产品目录，请稍后重试。", AgentStatus.ABSTAINED)

        if not scope.data_request or re.search(r"周报|report", message, re.I):
            try:
                async with asyncio.timeout(60):
                    result = await self._legacy.run(
                        recent_messages=recent_messages,
                        current_user_message=message,
                        event_sink=event_sink,
                    )
            except Exception:
                return finish(
                    "本次请求暂时未完成。你可以重试，或明确产品、关注方面及时间范围后继续。",
                    AgentStatus.ABSTAINED,
                )
            if result.status == AgentStatus.ERROR:
                return result.model_copy(
                    update={
                        "status": AgentStatus.ABSTAINED,
                        "error": None,
                        "final_answer": "这次没有完成查询。你可以补充产品名称、关注方面或时间范围后继续；也可以重试刚才的问题。",
                    }
                )
            return result

        try:
            week_range = period(message)
        except ValueError:
            return finish(
                "这个周次不是有效的 ISO 周。请提供有效的年份和周次，例如“2023 年第 5 周”。",
                AgentStatus.ABSTAINED,
            )
        if (
            scope.time_requested
            and week_range is None
            and not re.search(r"全部时间|所有时间|不限制时间", message)
        ):
            return finish(
                "请明确查询时间，例如“2023 年第 5 周”或“全部时间”，以免把不确定的时间范围用于统计。",
                AgentStatus.ABSTAINED,
            )

        runtime = bool(
            re.search(r"续航|耐不耐用|电量|运行.*小时|runtime", message, re.I)
        )
        sentiment = (
            "negative"
            if re.search(r"差评|投诉|负面|抱怨", message)
            else "positive"
            if re.search(r"好评|喜欢|正面|赞扬", message)
            else None
        )
        aspect = next(
            (
                label
                for pattern, label in [
                    (r"噪声|噪音|风扇", "noise_level"),
                    (r"充电", "charging_speed"),
                    (r"便携|重量", "weight_portability"),
                    (r"应用|APP", "app_connectivity"),
                ]
                if re.search(pattern, message, re.I)
            ),
            None,
        )
        operation = None
        if len(scope.skus) > 1:
            operation = "compare_skus"
        elif re.search(r"趋势|变化|按周", message):
            operation = "trend"
        elif re.search(r"正面.*负面|负面.*正面|情绪分布", message):
            operation = "sentiment_distribution"
        elif re.search(r"主要.*方面|最喜欢", message):
            operation = "aspect_distribution"
        elif scope.review_count_requested:
            operation = "review_count"
        elif re.search(r"主要.*方面|最喜欢|优缺点|怎么样|怎么评价", message) and not (
            runtime or aspect
        ):
            operation = "aspect_distribution"
        if operation:
            args = AnalyticsToolArguments(
                operation=operation,
                sku_codes=list(scope.skus),
                week_range=week_range,
                aspect_label=aspect,
                sentiment=sentiment
                if operation in {"review_count", "aspect_distribution"}
                else None,
                comparison_metric="negative_rate"
                if operation == "compare_skus"
                else None,
            )
            result = await call("tool_sql", args)
            if result and result.payload:
                parts.append(render_analytics(result.payload))
                counts = [
                    int(w.details.get("sample_size", 20))
                    for w in result.warnings
                    if w.code == "small_sample"
                ]
                if counts:
                    parts.append(
                        "部分产品样本少于本系统提示阈值 20 条，结论的代表性有限。"
                    )
            elif (
                result
                and result.error
                and result.error.code
                in {"capacity_tier_mismatch", "capacity_tier_unavailable"}
            ):
                return finish(
                    "这些产品的容量档位不同或缺少档位信息，无法直接按同档口径比较。请选择相同容量档位的产品。",
                    AgentStatus.ABSTAINED,
                )
            elif result and result.status in {ToolStatus.EMPTY, ToolStatus.NOT_FOUND}:
                parts.append("所选范围内没有足够的可分析统计数据。")
            else:
                parts.append("统计查询暂时未完成，当前无法提供可靠数字。")

        if (
            operation == "review_count"
            and runtime
            and re.search(r"怎么样|整体|口碑|评价", message)
        ):
            overall = await call(
                "tool_sql",
                AnalyticsToolArguments(
                    operation="aspect_distribution",
                    sku_codes=list(scope.skus),
                    week_range=week_range,
                ),
            )
            if overall and overall.payload:
                parts.append(render_analytics(overall.payload))

        qualitative = (
            runtime
            or aspect
            or bool(
                re.search(
                    r"怎么样|怎么评价|口碑|原文|原话|例子|证据|最喜欢|主要.*方面|查一下.*反馈",
                    message,
                )
            )
        )
        if operation is None or qualitative:
            result = await call(
                "tool_rag",
                RagToolArguments(
                    query=message,
                    sku_codes=list(scope.skus),
                    week_range=week_range,
                    aspect_label=aspect,
                    sentiment=sentiment,
                    top_k=8,
                ),
            )
            evidence = result.payload.evidence if result and result.payload else []
            if result and any(
                w.code == "source_sentiment_conflict" for w in result.warnings
            ):
                parts.append(
                    "部分原文与系统情绪标签不一致，已标记待复核；统计按现有归档标签计算，不应以该标签替代原文含义。"
                )
            if result and any(
                w.code == "source_model_conflict" for w in result.warnings
            ):
                parts.append(
                    "部分评论原文的产品型号归属存在疑问，已从体验引用中排除；评论统计仍按系统现有归档计算，不能视为已逐条核验的市场样本。"
                )
            quotes = []
            docs = set()
            for item in evidence:
                quote = evidence_quote(item, runtime)
                if quote and item.document_id not in docs:
                    docs.add(item.document_id)
                    selected.append(item)
                    label = (
                        "续航使用案例"
                        if runtime
                        else f"{ASPECTS.get(item.aspect_label, '用户体验')}（{SENTIMENTS.get(item.sentiment.value, item.sentiment.value)}）"
                    )
                    fact = ""
                    if not runtime and sentiment_label_conflict(
                        item.sentiment.value, item.mention_text
                    ):
                        label = f"{ASPECTS.get(item.aspect_label, '用户体验')}（情绪标签待复核）"
                    if runtime:
                        hours = re.search(
                            r"\b(?:ran|used)\b[^.!?]*?(\d+(?:\.\d+)?)\s*hours?\b",
                            quote,
                            re.I,
                        )
                        remaining = re.search(
                            r"\bdropped\b[^.!?]*?to\s*(\d+(?:\.\d+)?)\s*%", quote, re.I
                        )
                        if hours and remaining:
                            loads = [
                                name
                                for term, name in [
                                    ("desktop", "台式电脑"),
                                    ("monitor", "显示器"),
                                    ("phones", "手机"),
                                ]
                                if term in quote.lower()
                            ]
                            fact = f"该评论记录：为{'、'.join(loads) or '原文所述设备'}供电/充电，使用约 {hours[1]} 小时后剩余电量约 {remaining[1]}%。\n"
                    quotes.append(
                        f"{label}，{NAMES.get(item.sku_code, item.sku_code)}：\n{fact}> {quote}"
                    )
                if len(quotes) == (
                    2
                    if re.search(r"(?:引用|给出|提供)\s*(?:两|二|2)\s*条", message)
                    else 3
                ):
                    break
            if quotes:
                parts.append(
                    "以下是可追溯的用户原文，保留其具体使用条件；个别案例不代表总体表现：\n\n"
                    + "\n\n".join(quotes)
                )
            else:
                parts.append(
                    "当前没有找到能可靠回答这一方面的用户证据，无法据此下结论。你可以换一个方面或扩大时间范围。"
                )
                failed = True
            if runtime:
                parts.append(
                    "续航取决于负载功率、设备工作方式与初始电量。以上案例不能换算成任意冰箱或其他设备的固定运行小时数；充电速度和重量也不能证明续航长短。"
                )
        if not parts:
            return finish(
                "当前没有足够的依据完成这个问题，请补充产品、方面或时间范围。",
                AgentStatus.ABSTAINED,
            )
        return finish(
            status=AgentStatus.ABSTAINED if not selected and operation is None else None
        )
