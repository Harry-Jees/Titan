import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def apply_repository_migrations(db):
    for migration in sorted((ROOT / "migrations").glob("*.sql")):
        db.executescript(migration.read_text(encoding="utf-8"))


def create_live_schema_shape(db):
    """Reproduce the read-only Cloudflare D1 table shapes without production data."""
    db.executescript("""
        CREATE TABLE d1_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO d1_migrations(name) VALUES ('0001_init.sql'), ('0002_cloud_agent.sql');

        CREATE TABLE memories (
            id TEXT PRIMARY KEY, content TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            user_id TEXT NOT NULL DEFAULT 'legacy_unassigned', updated_at TEXT
        );
        CREATE TABLE evaluation_runs (
            id TEXT PRIMARY KEY, model TEXT NOT NULL, prompt TEXT NOT NULL, output TEXT NOT NULL,
            expected TEXT, passed INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_chunks (
            id TEXT PRIMARY KEY, source_url TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, user_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant','system')), content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE api_tools (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL,
            base_url TEXT NOT NULL, path TEXT NOT NULL, method TEXT NOT NULL CHECK(method IN ('GET','POST')),
            allowed_query TEXT NOT NULL DEFAULT '[]', allowed_body_keys TEXT NOT NULL DEFAULT '[]',
            credential_ciphertext TEXT, credential_iv TEXT,
            credential_header TEXT NOT NULL DEFAULT 'authorization',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id,name)
        );
        CREATE TABLE pending_tool_calls (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, tool_name TEXT NOT NULL,
            input_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE tool_audit (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, tool_name TEXT NOT NULL,
            status INTEGER, success INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE usage_limits (
            user_id TEXT NOT NULL, day TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,day)
        );
        CREATE TABLE training_preferences (
            user_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE training_examples (
            id TEXT PRIMARY KEY, source_user_message_id TEXT NOT NULL UNIQUE,
            source_assistant_message_id TEXT NOT NULL, user_id TEXT NOT NULL, prompt TEXT NOT NULL,
            response TEXT NOT NULL, quality_score INTEGER NOT NULL, labels_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'candidate', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT
        );
        CREATE TABLE training_runs (
            id TEXT PRIMARY KEY, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT,
            status TEXT NOT NULL, scanned_pairs INTEGER NOT NULL DEFAULT 0, accepted INTEGER NOT NULL DEFAULT 0,
            rejected INTEGER NOT NULL DEFAULT 0, evaluated INTEGER NOT NULL DEFAULT 0, summary TEXT, error TEXT
        );
    """)


class MigrationTests(unittest.TestCase):
    def test_all_migrations_apply_and_user_memory_is_scoped(self):
        db = sqlite3.connect(":memory:")
        apply_repository_migrations(db)
        db.execute("INSERT INTO user_memories (id,user_id,content) VALUES (?,?,?)", ("1", "scope-a", "private A"))
        db.execute("INSERT INTO user_memories (id,user_id,content) VALUES (?,?,?)", ("2", "scope-b", "private B"))
        self.assertEqual(
            db.execute("SELECT content FROM user_memories WHERE user_id=?", ("scope-a",)).fetchall(),
            [("private A",)],
        )
        db.close()

    def test_tool_and_training_tables_match_live_titan_schema(self):
        db = sqlite3.connect(":memory:")
        apply_repository_migrations(db)
        expected = {
            "api_tools", "pending_tool_calls", "tool_audit", "usage_limits",
            "training_preferences", "training_examples", "training_runs",
            "agent_experience_episodes", "agent_experience_events",
        }
        actual = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue(expected.issubset(actual))
        db.execute("INSERT INTO training_preferences(user_id) VALUES(?)", ("new-user",))
        self.assertEqual(
            db.execute("SELECT enabled FROM training_preferences WHERE user_id=?", ("new-user",)).fetchone(),
            (0,),
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(memories)")}
        self.assertTrue({"user_id", "updated_at"}.issubset(columns))
        pending_columns = {row[1] for row in db.execute("PRAGMA table_info(pending_tool_calls)")}
        self.assertIn("tool_fingerprint", pending_columns)
        db.close()

    def test_conversation_role_constraint_and_index(self):
        db = sqlite3.connect(":memory:")
        apply_repository_migrations(db)
        db.execute(
            "INSERT INTO conversations (id,user_id,conversation_id,role,content) VALUES (?,?,?,?,?)",
            ("1", "u", "c", "user", "hello"),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO conversations (id,user_id,conversation_id,role,content) VALUES (?,?,?,?,?)",
                ("2", "u", "c", "system", "forged"),
            )
        index = db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_conversations_scope'"
        ).fetchone()
        self.assertIsNotNone(index)
        db.close()

    def test_repository_migrations_extend_observed_live_schema_without_rewriting_rows(self):
        db = sqlite3.connect(":memory:")
        create_live_schema_shape(db)
        db.execute("INSERT INTO memories(id,content,source,user_id,updated_at) VALUES(?,?,?,?,?)",
                   ("legacy-memory", "preserve this memory", "user", "scope-a", "2026-11-01"))
        db.execute("INSERT INTO conversations(id,conversation_id,user_id,role,content) VALUES(?,?,?,?,?)",
                   ("legacy-system", "legacy-conversation", "scope-a", "system", "existing system row"))
        db.execute("INSERT INTO pending_tool_calls(id,user_id,tool_name,input_json) VALUES(?,?,?,?)",
                   ("legacy-approval", "scope-a", "write_item", '{"item":"old"}'))

        apply_repository_migrations(db)

        self.assertEqual(
            db.execute("SELECT content,user_id FROM memories WHERE id='legacy-memory'").fetchone(),
            ("preserve this memory", "scope-a"),
        )
        self.assertEqual(
            db.execute("SELECT role,content FROM conversations WHERE id='legacy-system'").fetchone(),
            ("system", "existing system row"),
        )
        self.assertEqual(
            db.execute("SELECT tool_fingerprint FROM pending_tool_calls WHERE id='legacy-approval'").fetchone(),
            ("",),
        )
        self.assertEqual(
            db.execute("SELECT name FROM d1_migrations ORDER BY id").fetchall(),
            [("0001_init.sql",), ("0002_cloud_agent.sql",)],
        )
        db.close()


    def test_experience_events_are_scoped_versioned_and_append_only(self):
        db = sqlite3.connect(":memory:")
        apply_repository_migrations(db)
        db.execute(
            "INSERT INTO agent_experience_episodes "
            "(id,user_id,environment_id,goal,mode,started_at) VALUES (?,?,?,?,?,?)",
            ("episode_0001", "scope-a", "toy-balance", "Keep balance", "simulation", "2026-11-11T00:00:00Z"),
        )
        db.execute(
            "INSERT INTO agent_experience_events "
            "(id,user_id,episode_id,sequence,event_type,schema_version,occurred_at,payload_json) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("event_0001", "scope-a", "episode_0001", 1, "observation", 1,
             "2026-11-11T00:00:01Z", '{"state":{"angle":0.1},"source":"toy"}'),
        )
        self.assertEqual(
            db.execute(
                "SELECT sequence,event_type FROM agent_experience_events "
                "WHERE user_id=? AND episode_id=?",
                ("scope-a", "episode_0001"),
            ).fetchall(),
            [(1, "observation")],
        )
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute(
                "UPDATE agent_experience_events SET payload_json='{}' WHERE id='event_0001'"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("DELETE FROM agent_experience_events WHERE id='event_0001'")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO agent_experience_episodes "
                "(id,user_id,environment_id,goal,mode,started_at) VALUES (?,?,?,?,?,?)",
                ("episode_0002", "scope-a", "robot", "Move", "physical", "2026-11-11T00:00:00Z"),
            )
        db.close()


    def test_semantic_learning_schema_and_full_text_index(self):
        db = sqlite3.connect(":memory:")
        apply_repository_migrations(db)
        columns = {row[1] for row in db.execute("PRAGMA table_info(knowledge_chunks)")}
        self.assertTrue({"summary", "topics_json", "kind", "embedding_json", "source_hash", "quality_score"}.issubset(columns))
        for table in ("knowledge_facts", "knowledge_evidence", "research_pages", "research_runs",
                      "research_frontier", "research_robots", "ai_daily_usage"):
            self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())
        db.execute(
            "INSERT INTO knowledge_chunks(id,source_url,title,content,content_hash,summary) VALUES(?,?,?,?,?,?)",
            ("semantic-1", "https://example.org/ai", "Semantic retrieval", "Vector embeddings improve semantic search across related concepts.", "hash-1", "Semantic retrieval overview"),
        )
        matches = db.execute(
            "SELECT k.id FROM knowledge_chunks_fts f JOIN knowledge_chunks k ON k.rowid=f.rowid WHERE knowledge_chunks_fts MATCH ?",
            ("embeddings",),
        ).fetchall()
        self.assertEqual(matches, [("semantic-1",)])
        db.close()


if __name__ == "__main__":
    unittest.main()
