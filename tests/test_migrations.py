import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def test_all_migrations_apply_and_user_memory_is_scoped(self):
        db = sqlite3.connect(":memory:")
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            db.executescript(migration.read_text(encoding="utf-8"))
        db.execute("INSERT INTO user_memories (id,user_id,content) VALUES (?,?,?)", ("1", "scope-a", "private A"))
        db.execute("INSERT INTO user_memories (id,user_id,content) VALUES (?,?,?)", ("2", "scope-b", "private B"))
        self.assertEqual(db.execute("SELECT content FROM user_memories WHERE user_id=?", ("scope-a",)).fetchall(), [("private A",)])
        db.close()

    def test_tool_and_training_tables_match_live_titan_schema(self):
        db = sqlite3.connect(":memory:")
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            db.executescript(migration.read_text(encoding="utf-8"))
        expected = {"api_tools", "pending_tool_calls", "tool_audit", "usage_limits",
                    "training_preferences", "training_examples", "training_runs"}
        actual = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue(expected.issubset(actual))
        db.execute("INSERT INTO training_preferences(user_id) VALUES(?)", ("new-user",))
        self.assertEqual(db.execute("SELECT enabled FROM training_preferences WHERE user_id=?", ("new-user",)).fetchone(), (0,))
        columns = {row[1] for row in db.execute("PRAGMA table_info(memories)")}
        self.assertTrue({"user_id", "updated_at"}.issubset(columns))
        pending_columns = {row[1] for row in db.execute("PRAGMA table_info(pending_tool_calls)")}
        self.assertIn("tool_fingerprint", pending_columns)
        db.close()

    def test_conversation_role_constraint_and_index(self):
        db = sqlite3.connect(":memory:")
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            db.executescript(migration.read_text(encoding="utf-8"))
        db.execute("INSERT INTO conversations (id,user_id,conversation_id,role,content) VALUES (?,?,?,?,?)", ("1","u","c","user","hello"))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO conversations (id,user_id,conversation_id,role,content) VALUES (?,?,?,?,?)", ("2","u","c","system","forged"))
        index = db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_conversations_scope'").fetchone()
        self.assertIsNotNone(index)
        db.close()


if __name__ == "__main__":
    unittest.main()
