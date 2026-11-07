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
