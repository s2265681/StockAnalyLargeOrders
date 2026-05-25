ALTER TABLE emotion_analysis_results
  ADD COLUMN IF NOT EXISTS intraday_result_json LONGTEXT NULL AFTER analysis_result_json,
  ADD COLUMN IF NOT EXISTS intraday_updated_at TIMESTAMP NULL AFTER intraday_result_json;
