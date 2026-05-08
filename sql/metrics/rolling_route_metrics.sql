MERGE `{project}.{dataset}.rolling_route_metrics` AS target
USING (
  WITH source_rows AS (
    SELECT
      chain,
      token_symbol AS stablecoin,
      route_id,
      settlement_node_id,
      settlement_node_name,
      settlement_node_type,
      protocol_type,
      label_confidence,
      fee_model,
      amount_usd,
      total_observed_fee_usd,
      observed_onchain_settled,
      block_date
    FROM `{project}.{dataset}.normalized_x402_payments`
    WHERE block_date BETWEEN @window_start_date AND @window_end_date
      AND block_timestamp >= @window_start
      AND block_timestamp < @window_end
      AND chain = @chain
      AND token_symbol = @stablecoin
  ),
  validation AS (
    SELECT
      chain,
      stablecoin,
      MAX(source_count) AS source_count,
      MAX(CASE WHEN validation_type = 'row_sample' THEN match_rate END) AS row_sample_match_rate,
      MAX(run_timestamp) AS last_validated_at,
      MAX(validation_type) AS validation_type
    FROM `{project}.{dataset}.x402_validation_log`
    WHERE run_timestamp >= @validation_window_start
      AND run_timestamp <= @run_timestamp
      AND chain = @chain
      AND stablecoin = @stablecoin
      AND validation_status = 'passed'
    GROUP BY chain, stablecoin
  ),
  totals AS (
    SELECT
      SUM(amount_usd) AS total_observed_volume_usd
    FROM source_rows
    WHERE amount_usd IS NOT NULL
  ),
  grouped AS (
    SELECT
      @run_timestamp AS cache_generation_timestamp,
      @run_timestamp AS metrics_timestamp,
      @window_label AS window_label,
      @window_start AS window_start,
      @window_end AS window_end,
      source_rows.chain,
      source_rows.stablecoin,
      source_rows.route_id,
      ANY_VALUE(source_rows.settlement_node_id) AS settlement_node_id,
      ANY_VALUE(source_rows.settlement_node_name) AS settlement_node_name,
      ANY_VALUE(source_rows.settlement_node_type) AS settlement_node_type,
      ANY_VALUE(source_rows.protocol_type) AS protocol_type,
      ANY_VALUE(source_rows.label_confidence) AS label_confidence,
      ANY_VALUE(source_rows.fee_model) AS fee_model,
      SAFE_DIVIDE(
        SUM(IF(source_rows.amount_usd IS NULL, 0, source_rows.total_observed_fee_usd)),
        SUM(source_rows.amount_usd)
      ) AS observed_cost_pct,
      SUM(IF(source_rows.amount_usd IS NULL, 0, source_rows.amount_usd)) AS route_volume_usd,
      totals.total_observed_volume_usd,
      SAFE_DIVIDE(
        SUM(IF(source_rows.amount_usd IS NULL, 0, source_rows.amount_usd)),
        totals.total_observed_volume_usd
      ) AS route_share_pct,
      COUNT(*) AS tx_count,
      COUNTIF(source_rows.amount_usd IS NULL) AS data_quality_issue_count,
      IFNULL(validation.source_count, 0) AS source_count,
      validation.row_sample_match_rate,
      validation.last_validated_at,
      CASE
        WHEN validation.last_validated_at IS NULL THEN 'partially_validated'
        WHEN validation.last_validated_at < @stale_validation_cutoff THEN 'stale'
        WHEN validation.source_count >= 3
          AND validation.row_sample_match_rate >= @reconciliation_match_rate_min
          AND COUNTIF(source_rows.amount_usd IS NULL) = 0 THEN 'validated'
        ELSE 'partially_validated'
      END AS data_quality_status
    FROM source_rows
    CROSS JOIN totals
    LEFT JOIN validation
      ON validation.chain = source_rows.chain
      AND validation.stablecoin = source_rows.stablecoin
    GROUP BY
      source_rows.chain,
      source_rows.stablecoin,
      source_rows.route_id,
      totals.total_observed_volume_usd,
      validation.source_count,
      validation.row_sample_match_rate,
      validation.last_validated_at
  )
  SELECT
    TO_HEX(SHA256(CONCAT(
      chain, '|',
      stablecoin, '|',
      route_id, '|',
      window_label, '|',
      CAST(window_start AS STRING)
    ))) AS metric_id,
    *
  FROM grouped
) AS source
ON target.chain = source.chain
  AND target.stablecoin = source.stablecoin
  AND target.route_id = source.route_id
  AND target.window_label = source.window_label
  AND target.window_start = source.window_start
WHEN NOT MATCHED THEN
  INSERT (
    metric_id,
    cache_generation_timestamp,
    metrics_timestamp,
    window_label,
    window_start,
    window_end,
    chain,
    stablecoin,
    route_id,
    settlement_node_id,
    settlement_node_name,
    settlement_node_type,
    protocol_type,
    label_confidence,
    fee_model,
    observed_cost_pct,
    route_volume_usd,
    total_observed_volume_usd,
    route_share_pct,
    tx_count,
    source_count,
    row_sample_match_rate,
    data_quality_status,
    last_validated_at
  )
  VALUES (
    source.metric_id,
    source.cache_generation_timestamp,
    source.metrics_timestamp,
    source.window_label,
    source.window_start,
    source.window_end,
    source.chain,
    source.stablecoin,
    source.route_id,
    source.settlement_node_id,
    source.settlement_node_name,
    source.settlement_node_type,
    source.protocol_type,
    source.label_confidence,
    source.fee_model,
    source.observed_cost_pct,
    source.route_volume_usd,
    source.total_observed_volume_usd,
    source.route_share_pct,
    source.tx_count,
    source.source_count,
    source.row_sample_match_rate,
    source.data_quality_status,
    source.last_validated_at
  );
