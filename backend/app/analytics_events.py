"""Typed PostHog event functions.

Each function wraps capture_event with correct property names.
All calls are fire-and-forget — never raise.
"""

from __future__ import annotations

from app.analytics import capture_event


def analysis_completed(
    distinct_id: str,
    *,
    session_id: str,
    duration_s: float,
    model: str,
    elements_count: int,
    gpu: str,
) -> None:
    capture_event(
        "analysis_completed",
        distinct_id,
        {
            "session_id": session_id,
            "duration_s": round(duration_s, 2),
            "model": model,
            "elements_count": elements_count,
            "gpu": gpu,
        },
    )


def analysis_failed(
    distinct_id: str,
    *,
    session_id: str,
    error_type: str,
    retry_count: int,
) -> None:
    capture_event(
        "analysis_failed",
        distinct_id,
        {
            "session_id": session_id,
            "error_type": error_type,
            "retry_count": retry_count,
        },
    )


def vastai_dispatched(
    distinct_id: str,
    *,
    session_id: str,
    instance_type: str,
    estimated_cost_usd: float,
) -> None:
    capture_event(
        "vastai_dispatched",
        distinct_id,
        {
            "session_id": session_id,
            "instance_type": instance_type,
            "estimated_cost_usd": round(estimated_cost_usd, 4),
        },
    )


def email_sent(
    distinct_id: str,
    *,
    template: str,
    success: bool,
    bounce_reason: str | None = None,
) -> None:
    props: dict = {"template": template, "success": success}
    if bounce_reason:
        props["bounce_reason"] = bounce_reason
    capture_event("email_sent", distinct_id, props)


def subscription_renewed(
    distinct_id: str,
    *,
    variant: str,
    plan: str,
) -> None:
    capture_event(
        "subscription_renewed",
        distinct_id,
        {
            "variant": variant,
            "plan": plan,
            "$feature_flag": "renewal_offer_variant",
        },
    )
