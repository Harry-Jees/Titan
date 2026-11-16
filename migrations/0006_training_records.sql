CREATE TABLE IF NOT EXISTS training_preferences (
  user_id TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS training_examples (
  id TEXT PRIMARY KEY,
  source_user_message_id TEXT NOT NULL UNIQUE,
  source_assistant_message_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  prompt TEXT NOT NULL,
  response TEXT NOT NULL,
  quality_score INTEGER NOT NULL,
  labels_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_training_examples_user_status ON training_examples(user_id,status,created_at DESC);

CREATE TABLE IF NOT EXISTS training_runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  status TEXT NOT NULL,
  scanned_pairs INTEGER NOT NULL DEFAULT 0,
  accepted INTEGER NOT NULL DEFAULT 0,
  rejected INTEGER NOT NULL DEFAULT 0,
  evaluated INTEGER NOT NULL DEFAULT 0,
  summary TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_training_runs_started ON training_runs(started_at DESC);
