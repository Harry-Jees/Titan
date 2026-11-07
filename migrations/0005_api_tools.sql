CREATE TABLE IF NOT EXISTS api_tools (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  base_url TEXT NOT NULL,
  path TEXT NOT NULL,
  method TEXT NOT NULL CHECK(method IN ('GET','POST')),
  allowed_query TEXT NOT NULL DEFAULT '[]',
  allowed_body_keys TEXT NOT NULL DEFAULT '[]',
  credential_ciphertext TEXT,
  credential_iv TEXT,
  credential_header TEXT NOT NULL DEFAULT 'authorization',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id,name)
);
CREATE INDEX IF NOT EXISTS idx_api_tools_user_name ON api_tools(user_id,name);

CREATE TABLE IF NOT EXISTS pending_tool_calls (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  input_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pending_tools_user_created ON pending_tool_calls(user_id,created_at);

CREATE TABLE IF NOT EXISTS tool_audit (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  status INTEGER,
  success INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tool_audit_user_created ON tool_audit(user_id,created_at DESC);

CREATE TABLE IF NOT EXISTS usage_limits (
  user_id TEXT NOT NULL,
  day TEXT NOT NULL,
  requests INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(user_id,day)
);
