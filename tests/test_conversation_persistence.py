import re
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConversationPersistenceContractTests(unittest.TestCase):
    def test_chat_does_not_accept_client_supplied_history(self):
        source = (ROOT / "src/index.ts").read_text(encoding="utf-8")
        chat = source.split('if (request.method === "POST" && url.pathname === "/chat")', 1)[1].split('if (url.pathname === "/conversations")', 1)[0]
        self.assertNotIn("body.history", chat)
        self.assertIn("client-supplied history is never trusted", chat.lower())

    def test_history_query_is_scoped_by_user_and_conversation(self):
        source = (ROOT / "src/index.ts").read_text(encoding="utf-8")
        self.assertIn("WHERE user_id = ? AND conversation_id = ? AND role IN ('user', 'assistant')", source)

    def test_chat_persists_user_and_assistant_turns(self):
        source = (ROOT / "src/index.ts").read_text(encoding="utf-8")
        self.assertIn("INSERT INTO conversations", source)
        self.assertIn("result.text.slice(0, 12000)", source)

    def test_conversation_list_and_delete_are_user_scoped(self):
        source = (ROOT / "src/index.ts").read_text(encoding="utf-8")
        route = source.split('if (url.pathname === "/conversations")', 1)[1].split('if (url.pathname === "/knowledge"', 1)[0]
        self.assertIn("memoryScope(request, env)", route)
        self.assertIn("WHERE user_id = ? GROUP BY conversation_id", route)
        self.assertIn("DELETE FROM conversations WHERE user_id = ? AND conversation_id = ?", route)

    def test_chat_retention_is_bounded(self):
        source = (ROOT / "src/index.ts").read_text(encoding="utf-8")
        self.assertIn("ORDER BY rowid DESC LIMIT 40", source)
        self.assertIn("ORDER BY rowid DESC LIMIT 10000", source)

    def test_message_limit_is_enforced(self):
        source = (ROOT / "src/index.ts").read_text(encoding="utf-8")
        self.assertRegex(source, re.compile(r'body\.message\.length > 12000'))


if __name__ == "__main__":
    unittest.main()
