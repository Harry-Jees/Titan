import unittest
from unittest.mock import patch

import training.crawl_web as crawler
from training.crawl_web import build_frontier, clean_url, public_url

class CrawlerSafetyTests(unittest.TestCase):
    def test_rejects_local_and_non_global_targets(self):
        for url in ("http://localhost/","http://127.0.0.1/","http://10.0.0.2/","http://169.254.169.254/","http://service.internal/","https://user:pass@example.org/","https://example.org:8443/"):
            self.assertFalse(public_url(url),url)
        self.assertTrue(public_url("https://docs.python.org/3/"))

    def test_clean_url_removes_tracking_query_and_fragments(self):
        self.assertEqual(clean_url("https://example.org/docs/?utm_source=test#section"),"https://example.org/docs")




    def test_frontier_resumes_pending_then_discovers_new_and_refreshes_stale(self):
        now = 200_000.0
        state = {
            "seen_urls": [
                "https://example.org/old",
                "https://example.org/recent",
            ],
            "last_crawled_at": {
                "https://example.org/old": now - 172_800,
                "https://example.org/recent": now - 60,
            },
            "remaining_queue": ["https://example.org/pending"],
        }
        queue = build_frontier(
            ["https://example.org/new", "https://example.org/old"],
            state,
            now=now,
            refresh_interval_seconds=86_400,
            max_queue_size=10,
        )
        self.assertEqual(
            list(queue),
            [
                "https://example.org/pending",
                "https://example.org/new",
                "https://example.org/old",
            ],
        )

    def test_legacy_checkpoint_without_timestamps_refreshes_seen_urls(self):
        queue = build_frontier(
            [],
            {"seen_urls": ["https://example.org/a", "https://example.org/b"]},
            now=200_000.0,
            refresh_interval_seconds=86_400,
            max_queue_size=10,
        )
        self.assertEqual(
            list(queue),
            ["https://example.org/a", "https://example.org/b"],
        )

    def test_frontier_is_capped_and_deduplicated(self):
        queue = build_frontier(
            [
                "https://example.org/a#one",
                "https://example.org/a#two",
                "https://example.org/b",
                "https://example.org/c",
            ],
            {},
            now=200_000.0,
            max_queue_size=2,
        )
        self.assertEqual(list(queue), ["https://example.org/a", "https://example.org/b"])

    def test_request_stops_before_network_when_run_deadline_is_exhausted(self):
        with patch.object(crawler, "safe_get") as safe_get:
            with patch.object(crawler.time, "monotonic", return_value=61.0):
                with patch.object(crawler, "STARTED_AT", 0.0), \
                     patch.object(crawler, "MAX_RUN_SECONDS", 60), \
                     patch.object(crawler, "BUDGET_EXHAUSTED", False):
                    result = crawler.request_once("https://docs.python.org/")
            self.assertEqual(result, (None, None, "budget-exhausted"))
            safe_get.assert_not_called()

    def test_request_stops_at_aggregate_byte_limit(self):
        class Response:
            status_code = 200
            headers = {"content-type": "text/html", "content-length": "6"}
            url = "https://docs.python.org/page"
            def __init__(self):
                self.closed = False
            def iter_content(self, chunk_size):
                yield b"abc"
                yield b"def"
            def close(self):
                self.closed = True

        response = Response()
        with patch.object(crawler, "safe_get", return_value=response):
            with patch.object(crawler.time, "monotonic", return_value=100.0), \
                 patch.object(crawler, "STARTED_AT", 0.0), \
                 patch.object(crawler, "MAX_RUN_SECONDS", 300), \
                 patch.object(crawler, "MAX_TOTAL_BYTES", 4), \
                 patch.object(crawler, "TOTAL_BYTES", 0), \
                 patch.object(crawler, "MAX_BYTES", 100), \
                 patch.object(crawler, "PER_HOST_DELAY", 0), \
                 patch.object(crawler, "LAST_HIT", {}), \
                 patch.object(crawler, "REQUESTED_HOSTS", set()), \
                 patch.object(crawler, "MAX_HOSTS", 5), \
                 patch.object(crawler, "BUDGET_EXHAUSTED", False):
                result = crawler.request_once("https://docs.python.org/page")
                self.assertEqual(result, (None, None, "budget-exhausted"))
                self.assertEqual(crawler.TOTAL_BYTES, 3)
                self.assertTrue(crawler.BUDGET_EXHAUSTED)
        self.assertTrue(response.closed)

    def test_request_stops_before_a_new_host_exceeds_host_budget(self):
        with patch.object(crawler, "safe_get") as safe_get:
            with patch.object(crawler.time, "monotonic", return_value=100.0), \
                 patch.object(crawler, "STARTED_AT", 0.0), \
                 patch.object(crawler, "MAX_RUN_SECONDS", 300), \
                 patch.object(crawler, "TOTAL_BYTES", 0), \
                 patch.object(crawler, "MAX_TOTAL_BYTES", 100), \
                 patch.object(crawler, "MAX_HOSTS", 1), \
                 patch.object(crawler, "REQUESTED_HOSTS", {"already.example"}), \
                 patch.object(crawler, "BUDGET_EXHAUSTED", False):
                result = crawler.request_once("https://docs.python.org/page")
            self.assertEqual(result, (None, None, "budget-exhausted"))
            safe_get.assert_not_called()


if __name__ == "__main__": unittest.main()
