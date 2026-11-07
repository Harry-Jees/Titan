import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/index.ts").read_text(encoding="utf-8")

class ConversationPersistenceContractTests(unittest.TestCase):
    def test_chat_ignores_client_supplied_history(self):
        self.assertNotIn("body.history", SOURCE)
        self.assertIn("historyRows", SOURCE)

    def test_history_query_is_scoped_by_user_and_conversation(self):
        normalized = re.sub(r"\s+", " ", SOURCE).lower()
        self.assertIn("where user_id=? and conversation_id=? and role in ('user','assistant')", normalized)

    def test_chat_persists_user_and_assistant_turns(self):
        self.assertIn("INSERT INTO conversations", SOURCE)
        self.assertIn("answer.text.slice(0,12000)", SOURCE)

    def test_conversation_list_and_delete_are_user_scoped(self):
        normalized = re.sub(r"\s+", " ", SOURCE).lower()
        self.assertIn("where user_id=? group by conversation_id", normalized)
        self.assertIn("delete from conversations where user_id=? and conversation_id=?", normalized)

    def test_chat_retention_is_bounded(self):
        self.assertIn("ORDER BY rowid DESC LIMIT 40", SOURCE)
        self.assertIn("ORDER BY rowid DESC LIMIT 10000", SOURCE)

    def test_message_limit_is_enforced(self):
        self.assertRegex(SOURCE, re.compile(r'body\.message\.length\s*>\s*12000'))

if __name__ == "__main__":
    unittest.main()
