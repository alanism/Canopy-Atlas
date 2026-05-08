"""Cache payload construction for public dashboard data."""

from __future__ import annotations

from typing import Any

from api.public_api import ensure_public_envelope


PREVIEW_TIMESTAMP = "2026-05-07T00:00:00Z"
PREVIEW_RUNTIME_WARNING = (
    "Public sample bootstrap rows. Scheduled cache refresh not observed yet; "
    "values are illustrative and not production evidence."
)


def build_dashboard_summary_payload(
    *,
    meta: dict[str, Any],
    leaderboard: list[dict[str, Any]],
    route_share: list[dict[str, Any]],
    settlement_health: list[dict[str, Any]],
    under_review: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return ensure_public_envelope(
        {
            "meta": meta,
            "data": {
                "panels": {
                    "observed_effective_cost_leaderboard": leaderboard,
                    "volume_weighted_route_share": route_share,
                    "observed_settlement_health_x_cost": settlement_health,
                    "under_review_routes": under_review or [],
                }
            },
        }
    )


def build_investor_preview_dashboard_payload() -> dict[str, Any]:
    """Build deterministic non-production rows for public sample mode."""

    rows = [
        {
            "route_id": "preview_solana_usdc_direct",
            "route_share_pct": 0.42,
            "observed_cost_pct": 0.0018,
            "observed_settlement_rate": 0.992,
            "data_quality_status": "preview_bootstrap",
        },
        {
            "route_id": "preview_base_usdc_x402",
            "route_share_pct": 0.31,
            "observed_cost_pct": 0.0024,
            "observed_settlement_rate": 0.986,
            "data_quality_status": "preview_bootstrap",
        },
        {
            "route_id": "preview_solana_usdc_agentcash",
            "route_share_pct": 0.19,
            "observed_cost_pct": 0.0031,
            "observed_settlement_rate": 0.976,
            "data_quality_status": "preview_bootstrap",
        },
    ]
    under_review = [
        {
            "route_id": "preview_unlabeled_long_tail",
            "route_share_pct": 0.08,
            "observed_cost_pct": 0.0047,
            "observed_settlement_rate": 0.941,
            "data_quality_status": "under_review",
        }
    ]
    return build_dashboard_summary_payload(
        meta={
            "cache_generation_timestamp": PREVIEW_TIMESTAMP,
            "metrics_timestamp": PREVIEW_TIMESTAMP,
            "data_window_start": "2026-05-06T00:00:00Z",
            "data_window_end": PREVIEW_TIMESTAMP,
            "last_validated_at": PREVIEW_TIMESTAMP,
            "data_quality_status": "preview_bootstrap",
            "labeled_volume_pct": 0.92,
            "long_tail_volume_pct": 0.08,
            "x402_signal_status": "unavailable",
            "x402_signal_detected": False,
            "runtime_warning": PREVIEW_RUNTIME_WARNING,
        },
        leaderboard=rows,
        route_share=rows,
        settlement_health=rows + under_review,
        under_review=under_review,
    )
