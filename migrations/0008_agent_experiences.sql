-- Durable episode metadata plus an append-only, versioned experience event log.
CREATE TABLE IF NOT EXISTS agent_experience_episodes (
  id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  goal TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('simulation', 'read_only')),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  started_at TEXT NOT NULL,
  ended_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, id)
);

CREATE INDEX IF NOT EXISTS idx_agent_experience_episodes_scope
  ON agent_experience_episodes(user_id, started_at DESC);

CREATE TABLE IF NOT EXISTS agent_experience_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  episode_id TEXT NOT NULL,
  sequence INTEGER NOT NULL CHECK (sequence > 0),
  event_type TEXT NOT NULL CHECK (event_type IN (
    'observation', 'prediction', 'action_proposed', 'action_validated',
    'outcome', 'diagnosis', 'belief_update', 'episode_ended'
  )),
  schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
  occurred_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (user_id, episode_id, sequence),
  FOREIGN KEY (user_id, episode_id)
    REFERENCES agent_experience_episodes(user_id, id)
);

CREATE INDEX IF NOT EXISTS idx_agent_experience_events_episode
  ON agent_experience_events(user_id, episode_id, sequence ASC);

CREATE TRIGGER IF NOT EXISTS agent_experience_events_no_update
BEFORE UPDATE ON agent_experience_events
BEGIN
  SELECT RAISE(ABORT, 'experience events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS agent_experience_events_no_delete
BEFORE DELETE ON agent_experience_events
BEGIN
  SELECT RAISE(ABORT, 'experience events are append-only');
END;
