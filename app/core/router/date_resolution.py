from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from app.agent.messages import INVALID_DATES_MESSAGE
from app.core.dates import question_contains_temporal_signal, resolve_date_range
from app.core.router.decision import RouterDecision


def apply_date_normalizer(question: str, decision: RouterDecision) -> RouterDecision:
    """Post-process the LLM router decision with deterministic date resolution.

    The LLM is told not to infer dates, so it leaves start_date/end_date null for
    relative expressions like "ultimo mes". This function fills them in using the
    deterministic date normalizer and clears missing_dates if resolution succeeds.
    """
    if not question_contains_temporal_signal(question):
        return decision

    date_range, invalid_tokens = resolve_date_range(question)
    if invalid_tokens:
        return RouterDecision(
            intent=decision.intent,
            traffic_source=decision.traffic_source,
            start_date=None,
            end_date=None,
            needs_clarification=True,
            clarification_reason="invalid_dates",
            refusal_reason=decision.refusal_reason,
            response_message=INVALID_DATES_MESSAGE,
        )
    if date_range is None:
        if decision.start_date is not None or decision.end_date is not None:
            return decision
        return decision

    resolved_start, resolved_end = date_range
    needs_clarification = decision.needs_clarification
    clarification_reason = decision.clarification_reason
    response_message = decision.response_message

    if needs_clarification and clarification_reason == "missing_dates":
        needs_clarification = False
        clarification_reason = None
        response_message = None

    return RouterDecision(
        intent=decision.intent,
        traffic_source=decision.traffic_source,
        start_date=decision.start_date if decision.start_date is not None else resolved_start,
        end_date=decision.end_date if decision.end_date is not None else resolved_end,
        needs_clarification=needs_clarification,
        clarification_reason=clarification_reason,
        refusal_reason=decision.refusal_reason,
        response_message=response_message,
    )


def inherit_dates_from_thread(
    thread_context: list[BaseMessage],
    decision: RouterDecision,
    *,
    previous_router_decision: RouterDecision | None = None,
    previous_tools_used: list[str] | None = None,
) -> RouterDecision:
    """Inherit temporal context from the most recent human message that had a date.

    Handles two cases:
    - Turn N had dates + metric clarification → turn N+1 resolves metric without repeating date.
    - Turn N had dates + tool executed → turn N+1 asks about same scope without repeating date.
    """
    if (
        previous_router_decision is not None
        and not (previous_tools_used or [])
        and not any(isinstance(msg, ToolMessage) for msg in thread_context)
        and previous_router_decision.start_date is not None
        and previous_router_decision.end_date is not None
    ):
        return RouterDecision(
            intent=decision.intent,
            traffic_source=decision.traffic_source,
            start_date=previous_router_decision.start_date,
            end_date=previous_router_decision.end_date,
            needs_clarification=False,
            clarification_reason=None,
            refusal_reason=decision.refusal_reason,
            response_message=None,
        )

    if previous_tools_used or any(isinstance(msg, ToolMessage) for msg in thread_context):
        return decision

    for msg in reversed(thread_context):
        if not isinstance(msg, HumanMessage):
            continue
        text = msg.content if isinstance(msg.content, str) else ""
        if not question_contains_temporal_signal(text):
            continue
        date_range, invalid_tokens = resolve_date_range(text)
        if date_range is None or invalid_tokens:
            continue
        resolved_start, resolved_end = date_range
        return RouterDecision(
            intent=decision.intent,
            traffic_source=decision.traffic_source,
            start_date=resolved_start,
            end_date=resolved_end,
            needs_clarification=False,
            clarification_reason=None,
            refusal_reason=decision.refusal_reason,
            response_message=None,
        )
    return decision
