import pathlib
import unittest

from pipeline.bq_client import BigQueryWrapper, BigQueryWrapperError
from pipeline.schema_apply import render_schema_sql


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_SQL = ROOT / "sql" / "schema" / "canopy_atlas_staging_tables.sql"


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def query(self, sql, job_config=None):
        self.calls.append((sql, job_config))
        return {"sql": sql, "job_config": job_config}


class TestPhase1BigQuerySchema(unittest.TestCase):
    def test_bq_client_enforces_max_bytes(self) -> None:
        fake = FakeClient()
        wrapper = BigQueryWrapper(fake, incremental_max_bytes=123)
        wrapper.query("SELECT 1")
        self.assertEqual(fake.calls[0][1].maximum_bytes_billed, 123)

    def test_incremental_uses_small_byte_cap(self) -> None:
        fake = FakeClient()
        wrapper = BigQueryWrapper(fake, incremental_max_bytes=10_000_000_000)
        wrapper.query("SELECT 1", mode="incremental")
        self.assertEqual(fake.calls[0][1].maximum_bytes_billed, 10_000_000_000)

    def test_backfill_requires_explicit_mode_and_dry_run(self) -> None:
        wrapper = BigQueryWrapper(FakeClient(), backfill_max_bytes=999)
        with self.assertRaises(BigQueryWrapperError):
            wrapper.query("SELECT 1", mode="backfill")

        result = wrapper.query("SELECT 1", mode="backfill", dry_run=True)
        self.assertTrue(result["job_config"].dry_run)
        self.assertEqual(result["job_config"].maximum_bytes_billed, 999)

    def test_schema_matches_reference_guide_table_inventory(self) -> None:
        sql = SCHEMA_SQL.read_text(encoding="utf-8")
        expected_tables = [
            "raw_x402_events",
            "normalized_x402_payments",
            "route_labels",
            "route_label_corrections",
            "advertised_fee_schedule",
            "anti_gaming_flags",
            "x402_validation_log",
            "rolling_route_metrics",
            "pipeline_runs",
        ]
        for table_name in expected_tables:
            self.assertIn(f".{table_name}`", sql)

    def test_schema_is_idempotent(self) -> None:
        sql = SCHEMA_SQL.read_text(encoding="utf-8")
        self.assertEqual(sql.count("CREATE TABLE IF NOT EXISTS"), 9)

    def test_solana_relevant_schemas_use_non_null_is_inner(self) -> None:
        sql = SCHEMA_SQL.read_text(encoding="utf-8")
        self.assertIn("is_inner              BOOL      NOT NULL", sql)
        self.assertIn("is_inner                           BOOL      NOT NULL", sql)

    def test_pipeline_runs_status_enum_is_lowercase_documented(self) -> None:
        sql = SCHEMA_SQL.read_text(encoding="utf-8")
        self.assertIn("status              STRING    NOT NULL", sql)
        self.assertNotIn("'RUNNING'", sql)
        self.assertNotIn("'SUCCESS'", sql)

    def test_schema_has_no_forbidden_sql_patterns(self) -> None:
        sql = SCHEMA_SQL.read_text(encoding="utf-8").upper()
        self.assertNotIn("SELECT *", sql)
        self.assertNotIn("GENERATE_UUID(", sql)
        self.assertNotIn("CURRENT_TIMESTAMP(", sql)

    def test_render_schema_sql_replaces_project_and_dataset(self) -> None:
        sql = render_schema_sql(project="p", dataset="d", template_path=SCHEMA_SQL)
        self.assertIn("`p.d.raw_x402_events`", sql)
        self.assertNotIn("{project}", sql)
        self.assertNotIn("{dataset}", sql)

    def test_upstream_gates_uses_central_bq_wrapper_contract(self) -> None:
        gates_path = ROOT / "pipeline" / "adapter" / "upstream_gates.py"
        content = gates_path.read_text(encoding="utf-8")
        self.assertIn("QueryRunner", content)
        self.assertNotIn("bigquery.Client", content)


if __name__ == "__main__":
    unittest.main()
