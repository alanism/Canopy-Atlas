"""Deterministic Phase 9 pipeline orchestration helpers."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from pipeline.metrics.rolling_metrics import windows_for_cadence


RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"
STALE = "stale"
SKIPPED_OVERLAP = "skipped_overlap"
PIPELINE_STATUSES = {RUNNING, SUCCESS, FAILED, STALE, SKIPPED_OVERLAP}
DEFAULT_LOCK_MINUTES = 10
DEFAULT_CHAIN = "solana"
DEFAULT_STABLECOIN = "PYUSD"


class PipelineRunStore(Protocol):
    def find_running(self, *, chain: str, stablecoin: str) -> "PipelineRun | None":
        ...

    def insert_run(self, run: "PipelineRun") -> None:
        ...

    def update_run_status(
        self,
        *,
        run_id: str,
        status: str,
        completed_at: datetime | None = None,
        phases_run: str | None = None,
        cache_promoted: bool | None = None,
        error_message: str | None = None,
        last_error: str | None = None,
    ) -> None:
        ...


class AlertSink(Protocol):
    def send(self, *, alert_type: str, message: str, payload: dict[str, Any]) -> None:
        ...


class PipelineStage(Protocol):
    name: str

    def run(self, context: "OrchestratorContext") -> dict[str, Any] | None:
        ...


@dataclass
class PipelineRun:
    run_id: str
    started_at: datetime
    status: str
    trigger_source: str
    chain: str
    stablecoin: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    rows_ingested: int | None = None
    rows_normalized: int | None = None
    rows_validated: int | None = None
    bytes_processed: int | None = None
    cache_promoted: bool | None = None
    phases_run: str | None = None
    error_message: str | None = None
    last_error: str | None = None
    completed_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrchestratorContext:
    run_id: str
    cadence: str
    windows: tuple[str, ...]
    chain: str
    stablecoin: str
    trigger_source: str
    requested_at: datetime


@dataclass(frozen=True)
class OrchestratorResult:
    status: str
    run_id: str
    cadence: str
    windows: tuple[str, ...]
    phases_run: tuple[str, ...]
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrchestratorConfig:
    overlap_lock_minutes: int = DEFAULT_LOCK_MINUTES


class MemoryPipelineRunStore:
    """Small in-memory store used by tests and local harnesses."""

    def __init__(self) -> None:
        self.runs: list[PipelineRun] = []
        self.update_calls: list[dict[str, Any]] = []

    def find_running(self, *, chain: str, stablecoin: str) -> PipelineRun | None:
        running = [
            run
            for run in self.runs
            if run.chain == chain and run.stablecoin == stablecoin and run.status == RUNNING
        ]
        if not running:
            return None
        return max(running, key=lambda run: run.started_at)

    def insert_run(self, run: PipelineRun) -> None:
        _validate_status(run.status)
        self.runs.append(run)

    def update_run_status(
        self,
        *,
        run_id: str,
        status: str,
        completed_at: datetime | None = None,
        phases_run: str | None = None,
        cache_promoted: bool | None = None,
        error_message: str | None = None,
        last_error: str | None = None,
    ) -> None:
        _validate_status(status)
        self.update_calls.append({"operation": "UPDATE", "run_id": run_id, "status": status})
        for run in self.runs:
            if run.run_id == run_id:
                run.status = status
                run.completed_at = completed_at
                run.phases_run = phases_run
                run.cache_promoted = cache_promoted
                run.error_message = error_message
                run.last_error = last_error
                return
        raise ValueError(f"unknown run_id: {run_id}")


class MemoryAlertSink:
    def __init__(self) -> None:
        self.alerts: list[dict[str, Any]] = []

    def send(self, *, alert_type: str, message: str, payload: dict[str, Any]) -> None:
        self.alerts.append({"alert_type": alert_type, "message": message, "payload": payload})


class NamedStage:
    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, context: OrchestratorContext) -> dict[str, Any] | None:
        return {"run_id": context.run_id, "phase": self.name}


def default_stage_plan(windows: tuple[str, ...]) -> list[PipelineStage]:
    stages: list[PipelineStage] = [
        NamedStage("ingest"),
        NamedStage("normalize"),
        NamedStage("validate"),
    ]
    stages.extend(NamedStage(f"metrics:{window}") for window in windows)
    stages.extend([NamedStage("validate_cache_payload"), NamedStage("promote_cache")])
    return stages


def run_orchestrator(
    *,
    payload: dict[str, Any],
    store: PipelineRunStore,
    alert_sink: AlertSink,
    stages: list[PipelineStage] | None = None,
    config: OrchestratorConfig | None = None,
    now: datetime | None = None,
) -> OrchestratorResult:
    requested_at = now or datetime.now(timezone.utc)
    cadence = str(payload.get("cadence", ""))
    windows = windows_for_cadence(cadence)
    chain = str(payload.get("chain") or DEFAULT_CHAIN)
    stablecoin = str(payload.get("stablecoin") or DEFAULT_STABLECOIN)
    trigger_source = str(payload.get("trigger_source") or "scheduler")
    run_id = str(payload.get("run_id") or uuid.uuid4())
    settings = config or OrchestratorConfig()

    active_run = store.find_running(chain=chain, stablecoin=stablecoin)
    if active_run is not None:
        active_age = requested_at - active_run.started_at
        if active_age <= timedelta(minutes=settings.overlap_lock_minutes):
            return _insert_skipped_overlap(
                store=store,
                run_id=run_id,
                requested_at=requested_at,
                trigger_source=trigger_source,
                chain=chain,
                stablecoin=stablecoin,
                cadence=cadence,
                windows=windows,
                reason="recent_running_lock",
            )

        store.update_run_status(
            run_id=active_run.run_id,
            status=STALE,
            completed_at=requested_at,
            error_message="stale running lock detected",
            last_error="failed_stale_lock",
        )
        alert_sink.send(
            alert_type="stale_running_lock",
            message="Stale pipeline run lock detected",
            payload={
                "stale_run_id": active_run.run_id,
                "oldest_running_minutes": int(active_age.total_seconds() // 60),
                "chain": chain,
                "stablecoin": stablecoin,
            },
        )
        return _insert_skipped_overlap(
            store=store,
            run_id=run_id,
            requested_at=requested_at,
            trigger_source=trigger_source,
            chain=chain,
            stablecoin=stablecoin,
            cadence=cadence,
            windows=windows,
            reason="stale_running_lock",
        )

    store.insert_run(
        PipelineRun(
            run_id=run_id,
            started_at=requested_at,
            status=RUNNING,
            trigger_source=trigger_source,
            chain=chain,
            stablecoin=stablecoin,
        )
    )

    context = OrchestratorContext(
        run_id=run_id,
        cadence=cadence,
        windows=windows,
        chain=chain,
        stablecoin=stablecoin,
        trigger_source=trigger_source,
        requested_at=requested_at,
    )
    phases_run: list[str] = []
    try:
        for stage in stages or default_stage_plan(windows):
            stage.run(context)
            phases_run.append(stage.name)
        store.update_run_status(
            run_id=run_id,
            status=SUCCESS,
            completed_at=requested_at,
            phases_run=",".join(phases_run),
            cache_promoted=True,
        )
        return OrchestratorResult(SUCCESS, run_id, cadence, windows, tuple(phases_run))
    except Exception as exc:
        store.update_run_status(
            run_id=run_id,
            status=FAILED,
            completed_at=requested_at,
            phases_run=",".join(phases_run),
            cache_promoted=False,
            error_message=str(exc),
            last_error=type(exc).__name__,
        )
        return OrchestratorResult(FAILED, run_id, cadence, windows, tuple(phases_run), reason=str(exc))


def _insert_skipped_overlap(
    *,
    store: PipelineRunStore,
    run_id: str,
    requested_at: datetime,
    trigger_source: str,
    chain: str,
    stablecoin: str,
    cadence: str,
    windows: tuple[str, ...],
    reason: str,
) -> OrchestratorResult:
    store.insert_run(
        PipelineRun(
            run_id=run_id,
            started_at=requested_at,
            status=SKIPPED_OVERLAP,
            trigger_source=trigger_source,
            chain=chain,
            stablecoin=stablecoin,
            error_message=reason,
            last_error=reason,
            completed_at=requested_at,
        )
    )
    return OrchestratorResult(SKIPPED_OVERLAP, run_id, cadence, windows, (), reason=reason)


def _validate_status(status: str) -> None:
    if status not in PIPELINE_STATUSES:
        raise ValueError(f"unsupported pipeline run status: {status}")
