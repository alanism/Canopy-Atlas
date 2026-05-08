"""Apply Canopy Atlas BigQuery schema SQL idempotently."""

from __future__ import annotations

from pathlib import Path

from pipeline.bq_client import BigQueryWrapper


SCHEMA_SQL_PATH = Path("sql/schema/canopy_atlas_staging_tables.sql")


def render_schema_sql(
    *,
    project: str,
    dataset: str,
    template_path: Path = SCHEMA_SQL_PATH,
) -> str:
    template = template_path.read_text(encoding="utf-8")
    return template.replace("{project}", project).replace("{dataset}", dataset)


def apply_schema(
    wrapper: BigQueryWrapper,
    *,
    project: str,
    dataset: str,
    dry_run: bool = False,
) -> object:
    sql = render_schema_sql(project=project, dataset=dataset)
    return wrapper.query(sql, mode="incremental", dry_run=dry_run)
