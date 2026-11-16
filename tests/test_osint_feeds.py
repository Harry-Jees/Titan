import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import requests

from training import fetch_osint_feeds as feeds
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

    def test_source_failures_are_isolated_and_successful_records_are_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "sources.json"
            output_path = root / "cycle.jsonl"
            registry_path.write_text(json.dumps({"sources": [
                {"id": "timeout-feed", "name": "Timeout feed", "category": "research", "kind": "xml", "url": "https://timeout.example/feed"},
                {"id": "blocked-feed", "name": "Blocked feed", "category": "research", "kind": "xml", "url": "https://blocked.example/feed"},
                {"id": "healthy-feed", "name": "Healthy feed", "category": "research", "kind": "xml", "url": "https://healthy.example/feed"},
            ]}), encoding="utf-8")
            xml = b"<rss><channel><item><title>Research update</title><link>https://healthy.example/post</link><description>This is a sufficiently detailed public research summary that should be kept for indexing.</description></item></channel></rss>"

            def fake_request(url, headers=None):
                if "timeout.example" in url:
                    raise requests.ReadTimeout("simulated timeout")
                if "blocked.example" in url:
                    raise feeds.UnsafeCrawlerURL("simulated unsafe redirect")
                return xml, 200

            stdout, stderr = StringIO(), StringIO()
            with (
                patch.object(feeds, "REGISTRY", registry_path),
                patch.object(feeds, "OUTPUT", output_path),
                patch.object(feeds, "robots_allowed", return_value=True),
                patch.object(feeds, "request", side_effect=fake_request),
                patch.object(feeds.SESSION, "close"),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                result = feeds.main()

            records = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
            self.assertEqual(result, 1)
            self.assertEqual([record["source_id"] for record in records], ["healthy-feed"])
            self.assertEqual(summary["sources"], 1)
            self.assertEqual(summary["records"], 1)
            self.assertEqual(summary["blocked"], 1)
            self.assertEqual(summary["errors"], 1)
            self.assertIn("Source blocked by crawler safety policy", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
