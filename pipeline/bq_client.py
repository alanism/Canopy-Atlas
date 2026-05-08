"""Central BigQuery wrapper for pipeline-side jobs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol


DEFAULT_INCREMENTAL_BYTES = 10_000_000_000


class BigQueryClientProtocol(Protocol):
    def query(self, sql: str, job_config: Any = None) -> Any:
        ...


class BigQueryWrapperError(RuntimeError):
    """Raised when a BigQuery job violates the x402 harness."""


@dataclass(frozen=True)
class QueryJobConfig:
    maximum_bytes_billed: int
    dry_run: bool = False
    use_query_cache: bool = True
    query_parameters: tuple[Any, ...] = ()


class BigQueryWrapper:
    def __init__(
        self,
        client: BigQueryClientProtocol,
        *,
        incremental_max_bytes: int | None = None,
        backfill_max_bytes: int | None = None,
    ) -> None:
        self.client = client
        self.incremental_max_bytes = incremental_max_bytes or int(
            os.environ.get("BQ_MAX_BYTES_BILLED_INCREMENTAL", DEFAULT_INCREMENTAL_BYTES)
        )
        self.backfill_max_bytes = backfill_max_bytes

    def query(
        self,
        sql: str,
        *,
        mode: str = "incremental",
        dry_run: bool = False,
        query_parameters: tuple[Any, ...] = (),
    ) -> Any:
        maximum_bytes_billed = self._resolve_max_bytes(mode=mode, dry_run=dry_run)
        job_config = QueryJobConfig(
            maximum_bytes_billed=maximum_bytes_billed,
            dry_run=dry_run,
            query_parameters=query_parameters,
        )
        return self.client.query(sql, job_config=job_config)

    def _resolve_max_bytes(self, *, mode: str, dry_run: bool) -> int:
        if mode == "incremental":
            return self.incremental_max_bytes
        if mode == "backfill":
            if not dry_run:
                raise BigQueryWrapperError("backfill queries require explicit dry_run=True")
            if self.backfill_max_bytes is None:
                env_value = os.environ.get("BQ_MAX_BYTES_BILLED_BACKFILL")
                if not env_value:
                    raise BigQueryWrapperError("BQ_MAX_BYTES_BILLED_BACKFILL is required for backfill")
                return int(env_value)
            return self.backfill_max_bytes
        raise BigQueryWrapperError(f"unsupported BigQuery query mode: {mode}")


def create_google_bigquery_wrapper(**kwargs: Any) -> BigQueryWrapper:
    from google.cloud import bigquery

    return BigQueryWrapper(bigquery.Client(), **kwargs)
