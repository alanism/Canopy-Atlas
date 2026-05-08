MERGE `{project}.{dataset}.anti_gaming_flags` AS target
USING `{project}.{dataset}.anti_gaming_flags_stage` AS source
ON target.route_id = source.route_id
  AND target.chain = source.chain
  AND target.flag_type = source.flag_type
  AND target.window_start = source.window_start
WHEN NOT MATCHED THEN
  INSERT (
    flag_id,
    flagged_at,
    route_id,
    chain,
    flag_type,
    window_start,
    window_end,
    payer_concentration_pct,
    top_payer_address,
    tx_count,
    flag_status,
    reviewed_at,
    notes
  )
  VALUES (
    TO_HEX(SHA256(CONCAT(source.route_id, '|', source.chain, '|', source.flag_type, '|', CAST(source.window_start AS STRING)))),
    source.flagged_at,
    source.route_id,
    source.chain,
    source.flag_type,
    source.window_start,
    source.window_end,
    source.payer_concentration_pct,
    source.top_payer_address,
    source.tx_count,
    source.flag_status,
    source.reviewed_at,
    source.notes
  );
