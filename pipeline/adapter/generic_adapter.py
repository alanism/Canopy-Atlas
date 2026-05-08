"""Generic upstream evidence adapter for public Canopy Atlas builds."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pipeline.ingest.solana_event_id import compute_raw_event_id


INGESTION_MODE_PATH = Path("config/ingestion_mode.json")
CHAINS_CONFIG_PATH = Path("config/chains.yaml")
DEFAULT_FIXTURE_PATH = Path("sample_data/solana_evidence_rows.json")


class EvidenceSource(Protocol):
    def fetch_rows(self, *, chain: str, token_symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        ...


class GenericAdapterError(RuntimeError):
    """Raised when public evidence ingestion would be ambiguous or unsafe."""


@dataclass(frozen=True)
class RawEvidenceEventStage:
    raw_event_id: str
    ingestion_id: str
    ingested_at: str
    run_id: str
    chain: str
    source_path: str
    decode_version: str
    raw_payload: dict[str, Any]
    block_date: str
    is_inner: bool
    x402_signal_detected: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class FixtureEvidenceSource:
    """Local JSON fixture source used by default for public demos and tests."""

    def __init__(self, fixture_path: Path = DEFAULT_FIXTURE_PATH) -> None:
        self.fixture_path = fixture_path

    def fetch_rows(self, *, chain: str, token_symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        if not self.fixture_path.exists():
            raise GenericAdapterError(f"missing evidence fixture: {self.fixture_path}")
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        rows = payload.get("rows", payload if isinstance(payload, list) else [])
        if not isinstance(rows, list):
            raise GenericAdapterError("evidence fixture must be a list or an object with a rows list")
        filtered = [
            row
            for row in rows
            if isinstance(row, dict)
            and str(row.get("chain")) == chain
            and str(row.get("token_symbol")) == token_symbol
        ]
        return filtered[:limit]


class GenericEvidenceAdapter:
    def __init__(self, source: EvidenceSource | None = None) -> None:
        self.source = source or FixtureEvidenceSource()

    def build_staging_rows(
        self,
        *,
        chain: str,
        token_symbol: str,
        run_id: str,
        ingestion_id: str,
        decode_version: str,
        limit: int = 100,
        mode_path: Path = INGESTION_MODE_PATH,
        chains_path: Path = CHAINS_CONFIG_PATH,
    ) -> list[RawEvidenceEventStage]:
        mode_config = load_ingestion_mode(mode_path)
        require_adapter_mode(mode_config)
        validate_token_pair(chain, token_symbol, chains_path)
        rows = self.source.fetch_rows(chain=chain, token_symbol=token_symbol, limit=limit)
        return [
            map_upstream_row_to_raw_event(
                row,
                run_id=run_id,
                ingestion_id=ingestion_id,
                default_decode_version=decode_version,
            )
            for row in rows
        ]


def load_ingestion_mode(path: Path = INGESTION_MODE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_adapter_mode(mode_config: dict[str, Any]) -> None:
    mode = mode_config.get("ingestion_mode")
    if mode == "adapter":
        return
    if mode == "pivot":
        raise GenericAdapterError("ingestion blocked because ingestion_mode is pivot")
    if mode == "adapter_plus_signal_fetch":
        raise GenericAdapterError("adapter_plus_signal_fetch requires an explicit upstream signal contract")
    if mode == "raw":
        raise GenericAdapterError("raw mode requires explicit bounded raw extraction implementation")
    raise GenericAdapterError(f"unknown ingestion_mode: {mode}")


def validate_token_pair(chain: str, token_symbol: str, config_path: Path = CHAINS_CONFIG_PATH) -> None:
    content = config_path.read_text(encoding="utf-8")
    allowed_pairs = parse_chain_token_pairs(content)
    if (chain, token_symbol) not in allowed_pairs:
        raise GenericAdapterError(f"unsupported token pair: {chain}/{token_symbol}")


def parse_chain_token_pairs(content: str) -> set[tuple[str, str]]:
    current: dict[str, str] = {}
    allowed_pairs: set[tuple[str, str]] = set()
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if {"chain", "token_symbol"} <= current.keys():
                allowed_pairs.add((current["chain"], current["token_symbol"]))
            current = {}
            stripped = stripped[2:].strip()
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        if key not in {"chain", "token_symbol"}:
            continue
        current[key] = _clean_yaml_scalar(raw_value)
        if {"chain", "token_symbol"} <= current.keys():
            allowed_pairs.add((current["chain"], current["token_symbol"]))
    if {"chain", "token_symbol"} <= current.keys():
        allowed_pairs.add((current["chain"], current["token_symbol"]))
    return allowed_pairs


def _clean_yaml_scalar(raw_value: str) -> str:
    value = raw_value.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def map_upstream_row_to_raw_event(
    row: dict[str, Any],
    *,
    run_id: str,
    ingestion_id: str,
    default_decode_version: str,
    ingested_at: str | None = None,
) -> RawEvidenceEventStage:
    chain = str(row["chain"])
    payload = dict(row)
    payload.setdefault("protocol_type", "unknown")
    payload.setdefault("x402_signal_status", "unavailable")

    raw_event_id = compute_raw_event_id(chain, _identity_event_for_chain(chain, payload))
    source_path = str(row.get("source_path") or "fixture:sample_data/solana_evidence_rows.json")
    decode_version = str(row.get("decode_version") or default_decode_version)
    event_ingested_at = ingested_at or datetime.now(timezone.utc).isoformat()

    return RawEvidenceEventStage(
        raw_event_id=raw_event_id,
        ingestion_id=ingestion_id,
        ingested_at=event_ingested_at,
        run_id=run_id,
        chain=chain,
        source_path=source_path,
        decode_version=decode_version,
        raw_payload=payload,
        block_date=str(row["block_date"]),
        is_inner=bool(row.get("is_inner", False)),
        x402_signal_detected=bool(row.get("x402_signal_detected", False)),
    )


def build_adapter_staging_rows(
    source: EvidenceSource,
    *,
    chain: str,
    token_symbol: str,
    run_id: str,
    ingestion_id: str,
    decode_version: str,
    limit: int = 100,
    mode_path: Path = INGESTION_MODE_PATH,
    chains_path: Path = CHAINS_CONFIG_PATH,
) -> list[RawEvidenceEventStage]:
    return GenericEvidenceAdapter(source).build_staging_rows(
        chain=chain,
        token_symbol=token_symbol,
        run_id=run_id,
        ingestion_id=ingestion_id,
        decode_version=decode_version,
        limit=limit,
        mode_path=mode_path,
        chains_path=chains_path,
    )


def validate_raw_mode_bounds(start_slot: int | None = None, end_slot: int | None = None) -> None:
    if start_slot is None or end_slot is None:
        raise GenericAdapterError("raw mode requires explicit start_slot and end_slot")
    if end_slot <= start_slot:
        raise GenericAdapterError("raw mode end_slot must be greater than start_slot")


def get_signal_fetch_candidates(rows: list[RawEvidenceEventStage]) -> list[dict[str, Any]]:
    return [
        {
            "chain": row.chain,
            "signature": row.raw_payload.get("signature"),
            "transaction_hash": row.raw_payload.get("transaction_hash"),
            "raw_event_id": row.raw_event_id,
        }
        for row in rows
    ]


def _identity_event_for_chain(chain: str, payload: dict[str, Any]) -> dict[str, Any]:
    if chain == "solana":
        return {
            "signature": payload.get("signature"),
            "instruction_index": payload.get("instruction_index"),
            "is_inner": payload.get("is_inner"),
            "inner_instruction_index": payload.get("inner_instruction_index"),
        }
    return {
        "transaction_hash": payload.get("transaction_hash"),
        "log_index": payload.get("log_index"),
    }
