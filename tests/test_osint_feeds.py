import unittest

from training.fetch_osint_feeds import json_records, text_records, xml_records, value_at


class OSINTFeedTests(unittest.TestCase):
    def test_nested_json_paths(self):
        value = {"cve": {"id": "CVE-2026-1234", "descriptions": [{"value": "Example issue"}]}}
        self.assertEqual(value_at(value, "cve.id"), "CVE-2026-1234")
        self.assertEqual(value_at(value, "cve.descriptions.0.value"), "Example issue")

    def test_json_feed_record_preserves_category_and_source(self):
        source = {
            "id": "test-cve", "name": "Test CVE Feed", "category": "cyber",
            "url": "https://example.org/feed.json", "records_path": "items",
            "title_path": "name", "summary_paths": ["id", "description"],
            "url_path": "url", "date_path": "date"
        }
        rows = list(json_records(source, {"items": [{
            "name": "Example vulnerability", "id": "CVE-2026-1234",
            "description": "A test issue", "url": "https://example.org/CVE-2026-1234",
            "date": "2026-11-16"
        }]}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Example vulnerability")
        self.assertIn("CVE-2026-1234", rows[0]["text"])
        self.assertEqual(rows[0]["url"], "https://example.org/CVE-2026-1234")

    def test_atom_and_rss_entries(self):
        xml = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Research update</title><link href="https://example.org/post"/><updated>2026-11-16</updated><summary>Public research details</summary></entry></feed>"""
        rows = list(xml_records({"name": "Example", "category": "research", "url": "https://example.org/feed"}, xml))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Research update")
        self.assertEqual(rows[0]["url"], "https://example.org/post")
        self.assertIn("Public research details", rows[0]["text"])

    def test_text_indicator_feed(self):
        rows = list(text_records({"name": "Public IOC feed", "category": "ioc", "url": "https://example.org/feed"}, b"# comment\nhttps://malicious.example/path\n"))
        self.assertEqual(len(rows), 1)
        self.assertIn("https://malicious.example/path", rows[0]["text"])


if __name__ == "__main__":
    unittest.main()
