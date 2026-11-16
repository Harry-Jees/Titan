-- Additive semantic knowledge schema. Deliberately avoids ALTER TABLE on legacy production tables.
CREATE TABLE IF NOT EXISTS knowledge_units (
 id TEXT PRIMARY KEY,
 source_url TEXT NOT NULL,
 title TEXT NOT NULL,
 content TEXT NOT NULL,
 content_hash TEXT NOT NULL UNIQUE,
 summary TEXT NOT NULL DEFAULT '',
 topics_json TEXT NOT NULL DEFAULT '[]',
 kind TEXT NOT NULL DEFAULT 'source',
 embedding_json TEXT,
 embedding_model TEXT,
 source_hash TEXT NOT NULL DEFAULT '',
 quality_score REAL NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_created ON knowledge_units(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_source ON knowledge_units(source_url);

-- Preserve already indexed knowledge while moving new writes to the richer schema.
INSERT OR IGNORE INTO knowledge_units(id,source_url,title,content,content_hash,kind)
SELECT id,source_url,title,content,content_hash,'legacy' FROM knowledge_chunks;

CREATE TABLE IF NOT EXISTS knowledge_facts (
 id TEXT PRIMARY KEY,
 fact_hash TEXT NOT NULL UNIQUE,
 subject TEXT NOT NULL,
 predicate TEXT NOT NULL,
 object TEXT NOT NULL,
 explanation TEXT NOT NULL DEFAULT '',
 confidence REAL NOT NULL DEFAULT 0.5 CHECK(confidence>=0 AND confidence<=1),
 status TEXT NOT NULL DEFAULT 'evidence-backed',
 conflict_group TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_knowledge_facts_subject ON knowledge_facts(subject);
CREATE TABLE IF NOT EXISTS knowledge_evidence (
 fact_id TEXT NOT NULL REFERENCES knowledge_facts(id) ON DELETE CASCADE,
 source_url TEXT NOT NULL,
 source_hash TEXT NOT NULL,
 quote TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(fact_id,source_url)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_source ON knowledge_evidence(source_url);
CREATE TABLE IF NOT EXISTS research_pages (
 source_url TEXT PRIMARY KEY,
 canonical_url TEXT NOT NULL,
 title TEXT NOT NULL DEFAULT '',
 content_hash TEXT NOT NULL,
 summary TEXT NOT NULL,
 topics_json TEXT NOT NULL DEFAULT '[]',
 quality_score REAL NOT NULL DEFAULT 0,
 novelty TEXT NOT NULL DEFAULT 'unknown',
 fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_research_pages_fetched ON research_pages(fetched_at DESC);
CREATE TABLE IF NOT EXISTS research_runs (
 run_id TEXT PRIMARY KEY,
 status TEXT NOT NULL DEFAULT 'queued',
 scheduled_at TEXT NOT NULL,
 started_at TEXT,
 completed_at TEXT,
 pages_crawled INTEGER NOT NULL DEFAULT 0,
 facts_added INTEGER NOT NULL DEFAULT 0,
 chunks_added INTEGER NOT NULL DEFAULT 0,
 error TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_runs_scheduled ON research_runs(scheduled_at DESC);
CREATE TABLE IF NOT EXISTS research_frontier (
 url TEXT PRIMARY KEY,
 depth INTEGER NOT NULL DEFAULT 0,
 priority INTEGER NOT NULL DEFAULT 0,
 discovered_from TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'queued',
 attempts INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_research_frontier_queue ON research_frontier(status,priority DESC,created_at ASC);
CREATE TABLE IF NOT EXISTS research_robots (origin TEXT PRIMARY KEY,body TEXT NOT NULL,expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_daily_usage (
 day_utc TEXT NOT NULL,
 bucket TEXT NOT NULL,
 reserved_neurons INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(day_utc,bucket)
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_units_fts
USING fts5(title,content,summary,content='knowledge_units',content_rowid='rowid',tokenize='porter unicode61');
INSERT INTO knowledge_units_fts(knowledge_units_fts) VALUES('rebuild');
CREATE TRIGGER IF NOT EXISTS knowledge_units_fts_insert AFTER INSERT ON knowledge_units BEGIN
 INSERT INTO knowledge_units_fts(rowid,title,content,summary) VALUES(new.rowid,new.title,new.content,new.summary);
END;
CREATE TRIGGER IF NOT EXISTS knowledge_units_fts_delete AFTER DELETE ON knowledge_units BEGIN
 INSERT INTO knowledge_units_fts(knowledge_units_fts,rowid,title,content,summary)
 VALUES('delete',old.rowid,old.title,old.content,old.summary);
END;
CREATE TRIGGER IF NOT EXISTS knowledge_units_fts_update AFTER UPDATE ON knowledge_units BEGIN
 INSERT INTO knowledge_units_fts(knowledge_units_fts,rowid,title,content,summary)
 VALUES('delete',old.rowid,old.title,old.content,old.summary);
 INSERT INTO knowledge_units_fts(rowid,title,content,summary) VALUES(new.rowid,new.title,new.content,new.summary);
END;

CREATE TABLE IF NOT EXISTS titan_semantic_migrations (
 name TEXT PRIMARY KEY,
 applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO titan_semantic_migrations(name) VALUES('0009_semantic_learning.sql');
