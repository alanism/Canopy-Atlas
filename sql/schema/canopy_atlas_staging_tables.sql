CREATE TABLE IF NOT EXISTS `{project}.{dataset}.raw_x402_events` (
  raw_event_id          STRING    NOT NULL,
  ingestion_id          STRING    NOT NULL,
  ingested_at           TIMESTAMP NOT NULL,
  run_id                STRING    NOT NULL,
  chain                 STRING    NOT NULL,
  source_path           STRING    NOT NULL,
  decode_version        STRING    NOT NULL,
  raw_payload           JSON      NOT NULL,
  block_date            DATE      NOT NULL,
  is_inner              BOOL      NOT NULL,
  x402_signal_detected  BOOL      NOT NULL DEFAULT FALSE
)
PARTITION BY block_date
CLUSTER BY chain, source_path
OPTIONS (description = 'Append-only raw payment event observations. MERGE on raw_event_id.');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.normalized_x402_payments` (
  chain                              STRING    NOT NULL,
  transaction_hash                   STRING,
  signature                          STRING,
  log_index                          INT64,
  instruction_index                  INT64,
  is_inner                           BOOL      NOT NULL,
  inner_instruction_index            INT64,
  block_timestamp                    TIMESTAMP NOT NULL,
  block_date                         DATE      NOT NULL,
  block_number                       INT64     NOT NULL,
  from_address                       STRING    NOT NULL,
  to_address                         STRING    NOT NULL,
  amount_tokens                      NUMERIC   NOT NULL,
  amount_usd                         FLOAT64   NOT NULL,
  token_symbol                       STRING    NOT NULL,
  route_id                           STRING    NOT NULL,
  protocol_type                      STRING    NOT NULL,
  payment_scheme                     STRING    NOT NULL,
  payment_structure                  STRING    NOT NULL,
  settlement_node_id                 STRING    NOT NULL,
  settlement_node_name               STRING    NOT NULL,
  settlement_node_type               STRING    NOT NULL,
  payment_role                       STRING    NOT NULL,
  label_confidence                   STRING    NOT NULL,
  session_or_batch_id                STRING,
  network_fee_usd                    FLOAT64   NOT NULL,
  priority_fee_usd                   FLOAT64,
  facilitator_fee_usd                FLOAT64,
  network_fee_observation_status     STRING    NOT NULL,
  priority_fee_observation_status    STRING    NOT NULL,
  facilitator_fee_observation_status STRING    NOT NULL,
  total_observed_fee_usd             FLOAT64   NOT NULL,
  fee_source                         STRING    NOT NULL,
  fee_model                          STRING    NOT NULL,
  observed_onchain_settled           BOOL      NOT NULL,
  settlement_latency_ms              INT64,
  self_transfer_flag                 BOOL      NOT NULL,
  normalized_payment_id              STRING    NOT NULL,
  source_path                        STRING    NOT NULL,
  decode_version                     STRING    NOT NULL,
  run_id                             STRING    NOT NULL,
  validation_status                  STRING    NOT NULL,
  last_validated_at                  TIMESTAMP NOT NULL
)
PARTITION BY block_date
CLUSTER BY chain, token_symbol, route_id
OPTIONS (description = 'Canonical route-level normalized payment records.');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.route_labels` (
  route_label_id        STRING    NOT NULL,
  settlement_node_id    STRING    NOT NULL,
  settlement_node_name  STRING    NOT NULL,
  wallet_address        STRING    NOT NULL,
  chain                 STRING    NOT NULL,
  confidence_level      STRING    NOT NULL,
  source                STRING    NOT NULL,
  valid_from            TIMESTAMP NOT NULL,
  valid_to              TIMESTAMP,
  last_reviewed_at      TIMESTAMP NOT NULL,
  label_status          STRING    NOT NULL,
  notes                 STRING
)
PARTITION BY DATE(valid_from)
OPTIONS (description = 'Time-bounded route entity labels.');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.route_label_corrections` (
  correction_id         STRING    NOT NULL,
  submitted_at          TIMESTAMP NOT NULL,
  submitted_by_email    STRING,
  route_id              STRING,
  chain                 STRING    NOT NULL,
  tx_hash_or_sig        STRING,
  claimed_correction    STRING    NOT NULL,
  evidence_type         STRING    NOT NULL,
  evidence_url          STRING,
  reviewer              STRING,
  reviewed_at           TIMESTAMP,
  outcome               STRING,
  resulting_label_id    STRING,
  notes                 STRING
)
PARTITION BY DATE(submitted_at)
OPTIONS (description = 'Audit log for external route label corrections.');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.advertised_fee_schedule` (
  schedule_id           STRING    NOT NULL,
  settlement_node_id    STRING    NOT NULL,
  chain                 STRING    NOT NULL,
  stablecoin            STRING    NOT NULL,
  fee_model             STRING    NOT NULL,
  advertised_fee_value  FLOAT64,
  fee_includes          STRING,
  source_url            STRING,
  last_checked_at       TIMESTAMP NOT NULL,
  notes                 STRING
)
OPTIONS (description = 'Manual advertised fee schedules. No external API calls.');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.anti_gaming_flags` (
  flag_id                   STRING    NOT NULL,
  flagged_at                TIMESTAMP NOT NULL,
  route_id                  STRING    NOT NULL,
  chain                     STRING    NOT NULL,
  flag_type                 STRING    NOT NULL,
  window_start              TIMESTAMP NOT NULL,
  window_end                TIMESTAMP NOT NULL,
  payer_concentration_pct   FLOAT64,
  top_payer_address         STRING,
  tx_count                  INT64     NOT NULL,
  flag_status               STRING    NOT NULL,
  reviewed_at               TIMESTAMP,
  notes                     STRING
)
PARTITION BY DATE(flagged_at)
OPTIONS (description = 'Anti-gaming flags per route per window.');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.x402_validation_log` (
  validation_id         STRING    NOT NULL,
  run_timestamp         TIMESTAMP NOT NULL,
  run_id                STRING    NOT NULL,
  chain                 STRING    NOT NULL,
  stablecoin            STRING    NOT NULL,
  validation_type       STRING    NOT NULL,
  source_a              STRING    NOT NULL,
  source_b              STRING    NOT NULL,
  window_start          TIMESTAMP NOT NULL,
  window_end            TIMESTAMP NOT NULL,
  bq_row_count          INT64     NOT NULL,
  rpc_row_count         INT64,
  node_row_count        INT64,
  sample_size           INT64     NOT NULL,
  matched_count         INT64     NOT NULL,
  match_rate            FLOAT64   NOT NULL,
  row_sample_match_rate FLOAT64,
  discrepancy_count     INT64     NOT NULL,
  source_count          INT64     NOT NULL,
  gate_passed           BOOL      NOT NULL,
  validation_status     STRING    NOT NULL,
  notes                 STRING
)
PARTITION BY DATE(run_timestamp)
OPTIONS (description = 'Three-source reconciliation audit log. validation_type required in every row.');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.rolling_route_metrics` (
  metric_id                    STRING    NOT NULL,
  cache_generation_timestamp   TIMESTAMP NOT NULL,
  metrics_timestamp            TIMESTAMP NOT NULL,
  window_label                 STRING    NOT NULL,
  window_start                 TIMESTAMP NOT NULL,
  window_end                   TIMESTAMP NOT NULL,
  chain                        STRING    NOT NULL,
  stablecoin                   STRING    NOT NULL,
  route_id                     STRING    NOT NULL,
  settlement_node_id           STRING    NOT NULL,
  settlement_node_name         STRING    NOT NULL,
  settlement_node_type         STRING    NOT NULL,
  protocol_type                STRING    NOT NULL,
  label_confidence             STRING    NOT NULL,
  fee_model                    STRING    NOT NULL,
  observed_cost_pct            FLOAT64,
  observed_cost_per_tx         FLOAT64,
  network_cost_pct             FLOAT64,
  facilitator_cost_pct         FLOAT64,
  total_observed_fee_usd       FLOAT64,
  advertised_fee_value         FLOAT64,
  advertised_fee_model         STRING,
  fee_delta                    FLOAT64,
  route_volume_usd             FLOAT64,
  total_observed_volume_usd    FLOAT64,
  route_share_pct              FLOAT64,
  tx_count                     INT64,
  observed_settlement_rate     FLOAT64,
  stale_rate                   FLOAT64,
  settlement_health_score      FLOAT64,
  p50_settlement_ms            INT64,
  p95_settlement_ms            INT64,
  labeled_volume_pct           FLOAT64,
  long_tail_volume_pct         FLOAT64,
  source_count                 INT64     NOT NULL,
  row_sample_match_rate        FLOAT64,
  data_quality_status          STRING    NOT NULL,
  last_validated_at            TIMESTAMP NOT NULL,
  under_review_flag            BOOL      NOT NULL DEFAULT FALSE
)
PARTITION BY DATE(cache_generation_timestamp)
CLUSTER BY chain, stablecoin, window_label, route_id
OPTIONS (description = 'Precomputed 5-min rolling route metrics. Dashboard reads only from here.');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.pipeline_runs` (
  run_id              STRING    NOT NULL,
  started_at          TIMESTAMP NOT NULL,
  completed_at        TIMESTAMP,
  status              STRING    NOT NULL,
  trigger_source      STRING    NOT NULL,
  chain               STRING    NOT NULL,
  stablecoin          STRING    NOT NULL,
  window_start        TIMESTAMP,
  window_end          TIMESTAMP,
  rows_ingested       INT64,
  rows_normalized     INT64,
  rows_validated      INT64,
  bytes_processed     INT64,
  cache_promoted      BOOL,
  phases_run          STRING,
  error_message       STRING,
  last_error          STRING
)
PARTITION BY DATE(started_at)
OPTIONS (description = 'Pipeline run log with full operational fields. Overlap prevention via run_id status check.');
