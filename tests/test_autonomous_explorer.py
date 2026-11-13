import unittest
from unittest.mock import patch
from titan_explorer.explorer import AutonomousExplorer, MAX_SESSION_SECONDS, _clean_url, _extract_keywords, _public_host, _summarize

class ExplorerTests(unittest.TestCase):
    def test_duration_cannot_exceed_thirty_minutes(self):
        with self.assertRaises(ValueError): AutonomousExplorer(duration_seconds=MAX_SESSION_SECONDS+1)
    def test_duration_must_be_positive(self):
        with self.assertRaises(ValueError): AutonomousExplorer(duration_seconds=0)
    def test_page_limit_is_bounded(self):
        with self.assertRaises(ValueError): AutonomousExplorer(max_pages=1501)
    def test_url_normalization_removes_fragment(self):
        self.assertEqual(_clean_url("https://Example.com/a#section"),"https://example.com/a")
    def test_rejects_non_http_and_credentials(self):
        self.assertIsNone(_clean_url("file:///etc/passwd")); self.assertIsNone(_clean_url("https://user:pass@example.com/"))
    def test_rejects_nonstandard_ports(self): self.assertIsNone(_clean_url("https://example.com:8443/"))
    def test_rejects_binary_suffix(self): self.assertIsNone(_clean_url("https://example.com/file.exe"))
    def test_sensitive_query_values_are_removed(self): self.assertEqual(_clean_url("https://example.com/?token=abc&q=hello"),"https://example.com/?q=hello")
    def test_keywords_are_deterministic(self): self.assertEqual(_extract_keywords("Python Python crawler crawler parser"),["crawler","python","parser"])
    def test_summary_is_extractive(self): self.assertIn("first sentence",_summarize("This is a sufficiently long first sentence describing the crawler. This is a sufficiently long second sentence describing source attribution."))
    @patch("titan_explorer.explorer.socket.getaddrinfo")
    def test_private_host_is_rejected(self,resolver):
        resolver.return_value=[(None,None,None,None,("127.0.0.1",0))]; self.assertFalse(_public_host("localhost.example"))
    @patch("titan_explorer.explorer.socket.getaddrinfo")
    def test_mixed_public_and_private_dns_is_rejected(self,resolver):
        resolver.return_value=[(None,None,None,None,("93.184.216.34",0)),(None,None,None,None,("10.0.0.1",0))]; self.assertFalse(_public_host("example.com"))

if __name__=="__main__": unittest.main()
