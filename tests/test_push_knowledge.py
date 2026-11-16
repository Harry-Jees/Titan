import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from training.push_knowledge import post_batch, read_chunks, split_text


class KnowledgePushTests(unittest.TestCase):
    def test_split_text_respects_chunk_boundaries(self):
        text = ("A" * 3000) + "\n\n" + ("B" * 3000)
        chunks = list(split_text(text, limit=4200))
        self.assertTrue(chunks)
        self.assertTrue(all(0 < len(chunk) <= 4200 for chunk in chunks))
        self.assertEqual("".join(chunks).replace("\n\n", ""), "A" * 3000 + "B" * 3000)

    def test_read_chunks_accepts_only_https_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cycle.jsonl"
            page = {"url": "https://docs.example.org/guide", "title": "Guide",
                    "text": "Useful paragraph. " * 40}
            path.write_text("\n".join(json.dumps(item) for item in (
                page, page, {**page, "url": "http://docs.example.org/insecure"}
            )), encoding="utf-8")
            chunks = read_chunks(path)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["source_url"], page["url"])
        self.assertLessEqual(len(chunks[0]["content"]), 5000)

    def test_post_batch_retries_rate_limit_then_succeeds(self):
        session = Mock()
        first = Mock(status_code=429, headers={"Retry-After": "1"})
        second = Mock(status_code=201, headers={})
        second.ok = True
        second.json.return_value = {"accepted": 1, "valid": 1, "inserted": 1}
        session.post.side_effect = [first, second]
        with patch("training.push_knowledge.time.sleep"):
            result = post_batch(session, "https://titan.example/knowledge", [{"content": "x"}])
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(session.post.call_count, 2)
        first.close.assert_called_once()
        second.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
