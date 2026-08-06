-- kr-realestate D1 schema
-- Tables for scorer results, ML weights, monthly stats, external data,
-- daily eval logs, and a wiki FTS index.

-- Scorer results: one row per region
CREATE TABLE IF NOT EXISTS scorer_results (
  region       TEXT PRIMARY KEY,
  total_score  REAL,
  grade        TEXT,
  factors      TEXT,
  version      TEXT,
  scored_at    TEXT
);

-- ML weights: one row per factor
CREATE TABLE IF NOT EXISTS ml_weights (
  factor_name       TEXT PRIMARY KEY,
  default_weight    REAL,
  optimized_weight  REAL,
  updated_at        TEXT
);

-- Monthly stats: composite PK (region, year_month)
CREATE TABLE IF NOT EXISTS monthly_stats (
  region             TEXT,
  year_month         TEXT,
  avg_price          REAL,
  trade_count        INTEGER,
  avg_jeonse_deposit REAL,
  jeonse_rate        REAL,
  PRIMARY KEY (region, year_month)
);

-- External cheongyak (public housing lottery) data
CREATE TABLE IF NOT EXISTS external_cheongyak (
  id                INTEGER PRIMARY KEY,
  region            TEXT,
  pblanc_name       TEXT,
  total_supply      INTEGER,
  total_competition REAL,
  score_cutoff      REAL,
  supply_price      REAL,
  market_price      REAL,
  pblanc_start      TEXT,
  pblanc_end        TEXT
);

-- External development project data
CREATE TABLE IF NOT EXISTS external_development (
  id                 INTEGER PRIMARY KEY,
  region             TEXT,
  project_name       TEXT,
  project_type       TEXT,
  status             TEXT,
  expected_completion TEXT,
  impact_score       REAL
);

-- Daily evaluation log
CREATE TABLE IF NOT EXISTS daily_eval_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date     TEXT,
  task         TEXT,
  status       TEXT,
  result_json  TEXT,
  created_at   TEXT
);

-- Wiki content table (paired with FTS below)
CREATE TABLE IF NOT EXISTS wiki_search (
  title        TEXT,
  category     TEXT,
  date_token   TEXT,
  content      TEXT,
  indexed_at   TEXT
);

-- Wiki FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
  title,
  category,
  content,
  date_token,
  tokenize = 'porter unicode61'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_monthly_region ON monthly_stats(region);
CREATE INDEX IF NOT EXISTS idx_cheongyak_region ON external_cheongyak(region);
CREATE INDEX IF NOT EXISTS idx_devel_region ON external_development(region);

-- ── Manual overrides synced from Google Drive (cron, see src/lib/drive-sync.ts) ──
-- Populated exclusively by the scheduled Drive sync: every run replaces the
-- full table content with whatever CSV rows are currently in the Drive
-- overrides folder, so deleting a row in Drive removes the override here too
-- (the scorer-computed value then applies again, untouched).
CREATE TABLE IF NOT EXISTS manual_overrides (
  region     TEXT NOT NULL,
  field      TEXT NOT NULL,
  value      TEXT NOT NULL,
  note       TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (region, field)
);

-- Tracks the last-applied Drive modifiedTime for each per-table data dump
-- file (see src/lib/drive-sync.ts runTableDataSync), so unchanged files are
-- skipped instead of being re-applied every 15-minute cron run.
CREATE TABLE IF NOT EXISTS drive_sync_state (
  file_id       TEXT PRIMARY KEY,
  path          TEXT NOT NULL,
  modified_time TEXT NOT NULL,
  updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
