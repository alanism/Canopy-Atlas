#!/usr/bin/env python3
"""Aggregate append-only paid AgentCash proxy events into cached summaries."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.agent_proxy import METRICS_WINDOWS, PAID_EVENT_TYPE, metrics_cache_filename


WINDOW_DURATIONS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def aggregate_events(events: list[dict[str, Any]], *, now: datetime, settlement_note: str | None = None) -> dict[str, dict[str, Any]]:
    unique_events = dedupe_events(events)
    return {
        window: aggregate_window(unique_events, window=window, now=now, settlement_note=settlement_note)
        for window in sorted(METRICS_WINDOWS, key=lambda item: WINDOW_DURATIONS[item])
    }


def aggregate_window(
    events: list[dict[str, Any]],
    *,
    window: str,
    now: datetime,
    settlement_note: str | None,
) -> dict[str, Any]:
    cutoff = now - WINDOW_DURATIONS[window]
    scoped = [event for event in events if event_time(event) and event_time(event) >= cutoff and event_time(event) <= now]
    counts = Counter(event.get("outcome") for event in scoped)
    paid_events = [event for event in scoped if event.get("outcome") == "paid_success"]
    wallets = {event.get("wallet_id") for event in paid_events if event.get("wallet_id")}
    gross_usdc = sum((decimal_amount(event.get("charge_usdc")) for event in paid_events), Decimal("0.00"))
    latencies = sorted(float(event["latency_ms"]) for event in scoped if isinstance(event.get("latency_ms"), (int, float)))

    return {
        "meta": {
            "service": "canopy-agent-proxy",
            "window": window,
            "generated_at": now.isoformat(),
            "source": "append_only_paid_agent_events",
            "wallet_privacy": "hmac_anonymized",
            "data_quality_status": "ready" if scoped else "empty",
            "settlement_note": settlement_note
            or "Run npx agentcash@latest balance from an operator shell for current merchant wallet balance.",
        },
        "data": {
            "totals": {
                "paid_success_count": counts["paid_success"],
                "gross_usdc": money(gross_usdc),
                "payment_required_count": counts["payment_required"],
                "payment_rejected_count": counts["payment_rejected"],
                "rate_limited_count": counts["rate_limited"],
                "benchmark_unavailable_count": counts["benchmark_unavailable"],
                "unique_payer_wallets": len(wallets),
                "p95_latency_ms": percentile_95(latencies),
            },
            "breakdowns": {
                "by_network": network_breakdown(paid_events),
                "by_window_requested": requested_window_breakdown(scoped),
                "top_wallets": top_wallets(paid_events),
            },
            "latest_events": latest_events(scoped),
        },
    }


def dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != PAID_EVENT_TYPE:
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or event_id in seen:
            continue
        seen.add(event_id)
        unique.append(event)
    return unique


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def write_summaries(summaries: dict[str, dict[str, Any]], cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    for window, payload in summaries.items():
        path = cache_dir / metrics_cache_filename(window)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def event_time(event: dict[str, Any]) -> datetime | None:
    value = event.get("emitted_at")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def decimal_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def percentile_95(values: list[float]) -> float | None:
    if not values:
        return None
    index = max(0, int(round((len(values) - 1) * 0.95)))
    return round(values[index], 3)


def network_breakdown(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "gross_usdc": Decimal("0.00")})
    for event in events:
        network = event.get("payment_network") or "unknown"
        grouped[str(network)]["count"] += 1
        grouped[str(network)]["gross_usdc"] += decimal_amount(event.get("charge_usdc"))
    return [
        {"network": network, "count": values["count"], "gross_usdc": money(values["gross_usdc"])}
        for network, values in sorted(grouped.items())
    ]


def requested_window_breakdown(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "gross_usdc": Decimal("0.00")})
    for event in events:
        requested_window = event.get("window") or "unknown"
        grouped[str(requested_window)]["count"] += 1
        if event.get("outcome") == "paid_success":
            grouped[str(requested_window)]["gross_usdc"] += decimal_amount(event.get("charge_usdc"))
    return [
        {"window": requested_window, "count": values["count"], "gross_usdc": money(values["gross_usdc"])}
        for requested_window, values in sorted(grouped.items())
    ]


def top_wallets(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"paid_success_count": 0, "gross_usdc": Decimal("0.00")})
    for event in events:
        wallet_id = event.get("wallet_id")
        if not wallet_id:
            continue
        grouped[str(wallet_id)]["paid_success_count"] += 1
        grouped[str(wallet_id)]["gross_usdc"] += decimal_amount(event.get("charge_usdc"))
    rows = [
        {
            "wallet_id": wallet_id,
            "paid_success_count": values["paid_success_count"],
            "gross_usdc": money(values["gross_usdc"]),
        }
        for wallet_id, values in grouped.items()
    ]
    return sorted(rows, key=lambda row: (-row["paid_success_count"], row["wallet_id"]))[:10]


def latest_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(events, key=lambda event: event.get("emitted_at") or "", reverse=True)[:10]
    return [
        {
            "emitted_at": event.get("emitted_at"),
            "outcome": event.get("outcome"),
            "status_code": event.get("status_code"),
            "wallet_id": event.get("wallet_id"),
            "payment_network": event.get("payment_network"),
            "window": event.get("window"),
        }
        for event in rows
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JSONL file containing paid proxy structured events.")
    parser.add_argument("--cache-dir", required=True, type=Path, help="Directory for cached metrics summaries.")
    parser.add_argument("--now", help="ISO timestamp used for deterministic tests/backfills.")
    parser.add_argument("--settlement-note", help="Operator-visible merchant wallet settlement note.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    summaries = aggregate_events(read_events(args.input), now=now.astimezone(timezone.utc), settlement_note=args.settlement_note)
    write_summaries(summaries, args.cache_dir)


if __name__ == "__main__":
    main()
