import unittest
from training.crawl_web import clean_url, public_url

class CrawlerSafetyTests(unittest.TestCase):
    def test_rejects_local_and_non_global_targets(self):
        for url in ("http://localhost/","http://127.0.0.1/","http://10.0.0.2/","http://169.254.169.254/","http://service.internal/","https://user:pass@example.org/","https://example.org:8443/"):
            self.assertFalse(public_url(url),url)
        self.assertTrue(public_url("https://docs.python.org/3/"))

    def test_clean_url_removes_tracking_query_and_fragments(self):
        self.assertEqual(clean_url("https://example.org/docs/?utm_source=test#section"),"https://example.org/docs")

if __name__ == "__main__": unittest.main()
