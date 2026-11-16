-- Bind each one-time approval to the exact tool definition seen by the user.
-- Empty fingerprints invalidate any legacy pending approvals safely.
ALTER TABLE pending_tool_calls ADD COLUMN tool_fingerprint TEXT NOT NULL DEFAULT '';
