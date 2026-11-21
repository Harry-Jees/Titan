import socket
import unittest

from training.crawler_policy import CrawlerConfig, resolve_public_url, validate_redirect


def answer(ip):
    return (socket.AF_INET6 if ":" in ip else socket.AF_INET,
            socket.SOCK_STREAM, 6, "", (ip, 0))


class CrawlerPolicyTests(unittest.TestCase):
    def resolver(self, *ips):
        return lambda host, port, type: [answer(ip) for ip in ips]

    def test_accepts_public_literal_and_public_dns(self):
        self.assertTrue(resolve_public_url("https://1.1.1.1/").allowed)
        decision = resolve_public_url("https://docs.example.org/path",
                                      resolver=self.resolver("93.184.216.34"))
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.addresses, ("93.184.216.34",))

    def test_rejects_private_and_special_literals(self):
        for ip in ("127.0.0.1", "10.0.0.2", "169.254.169.254",
                   "192.168.1.1", "::1", "fc00::1", "fe80::1"):
            with self.subTest(ip=ip):
                self.assertFalse(resolve_public_url(f"http://{ip}/").allowed)

    def test_rejects_credentials_ports_schemes_and_local_names(self):
        candidates = (
            "file:///etc/passwd", "ftp://example.org/", "https://u:p@example.org/",
            "https://example.org:8443/", "http://localhost/",
            "http://printer.local/", "http://service.internal/",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertFalse(resolve_public_url(candidate).allowed)

    def test_rejects_mixed_public_and_private_dns_answers(self):
        decision = resolve_public_url("https://mixed.example.org/",
                                      resolver=self.resolver("93.184.216.34", "10.0.0.8"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "non_public_dns_answer")

    def test_dns_failure_and_empty_answers_fail_closed(self):
        def failed(*args, **kwargs):
            raise socket.gaierror("no answer")
        self.assertEqual(resolve_public_url("https://missing.example.org/",
                                            resolver=failed).reason,
                         "dns_resolution_failed")
        self.assertEqual(resolve_public_url("https://empty.example.org/",
                                            resolver=self.resolver()).reason,
                         "dns_no_answers")

    def test_rejects_oversized_and_malformed_urls(self):
        self.assertEqual(resolve_public_url("https://a.example/" + "x" * 2100).reason,
                         "invalid_or_oversized_url")
        self.assertFalse(resolve_public_url("https://example.org:bad/").allowed)
        for candidate in (
            "https://example.org/a b",
            "https://example.org/a\\b",
            "https://example.org/a\tb",
            "https://example.org/a\x7fb",
        ):
            with self.subTest(candidate=candidate):
                self.assertEqual(resolve_public_url(candidate).reason, "malformed_url")

    def test_relative_redirect_is_resolved_and_revalidated(self):
        decision = validate_redirect("https://docs.example.org/a", "/b",
                                     resolver=self.resolver("93.184.216.34"))
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.normalized_url, "https://docs.example.org/b")

    def test_redirect_to_private_host_is_rejected(self):
        decision = validate_redirect("https://public.example.org/",
                                     "http://127.0.0.1/admin")
        self.assertFalse(decision.allowed)

    def test_cross_host_redirect_rechecks_dns(self):
        decision = validate_redirect("https://public.example.org/",
                                     "https://mixed.example.org/",
                                     resolver=self.resolver("8.8.8.8", "192.168.1.10"))
        self.assertFalse(decision.allowed)

    def test_https_redirect_downgrade_is_rejected(self):
        decision = validate_redirect("https://secure.example.org/",
                                     "http://public.example.org/",
                                     resolver=self.resolver("93.184.216.34"))
        self.assertEqual(decision.reason, "https_downgrade")

    def test_config_defaults_and_host_allow_deny(self):
        config = CrawlerConfig.from_env({
            "TITAN_ALLOWED_DOMAINS": "example.org, docs.python.org",
            "TITAN_DENIED_DOMAINS": "private.example.org",
        })
        self.assertEqual(config.page_target, 10_000)
        self.assertEqual(config.max_total_bytes, 100_000_000)
        self.assertEqual(config.max_run_seconds, 3_000)
        self.assertEqual(config.max_hosts_per_run, 50)
        self.assertEqual(config.recrawl_interval_seconds, 86_400)
        self.assertEqual(config.max_queue_size, 20_000)
        self.assertTrue(config.host_allowed("api.example.org"))
        self.assertFalse(config.host_allowed("private.example.org"))
        self.assertFalse(config.host_allowed("elsewhere.net"))

    def test_domain_policy_uses_label_boundaries_and_deny_precedence(self):
        config = CrawlerConfig.from_env({
            "TITAN_ALLOWED_DOMAINS": "example.org",
            "TITAN_DENIED_DOMAINS": "private.example.org",
        })
        self.assertTrue(config.host_allowed("example.org"))
        self.assertTrue(config.host_allowed("api.example.org"))
        self.assertFalse(config.host_allowed("notexample.org"))
        self.assertFalse(config.host_allowed("private.example.org"))
        self.assertFalse(config.host_allowed("api.private.example.org"))

    def test_config_rejects_unbounded_or_invalid_values(self):
        for values in (
            {"TITAN_PAGE_TARGET": "0"},
            {"TITAN_PAGE_TARGET": "10001"},
            {"TITAN_FETCH_TIMEOUT": "999"},
            {"TITAN_PER_HOST_DELAY": "0"},
            {"TITAN_MAX_PAGE_BYTES": "99999999"},
            {"TITAN_MAX_TOTAL_BYTES": "0"},
            {"TITAN_MAX_RUN_SECONDS": "30"},
            {"TITAN_MAX_HOSTS_PER_RUN": "0"},
            {"TITAN_RECRAWL_INTERVAL_SECONDS": "59"},
            {"TITAN_MAX_QUEUE_SIZE": "99"},
            {"TITAN_ALLOWED_DOMAINS": "https://example.org/path"},
            {"TITAN_ALLOWED_DOMAINS": "*.example.org"},
            {"TITAN_MAX_TOTAL_BYTES": "1000000001"},
            {"TITAN_MAX_RUN_SECONDS": "3301"},
            {"TITAN_MAX_HOSTS_PER_RUN": "501"},
            {"TITAN_RECRAWL_INTERVAL_SECONDS": "2592001"},
            {"TITAN_MAX_QUEUE_SIZE": "50001"},
            {"TITAN_MAX_PAGE_BYTES": "4000001"},
            {"TITAN_PER_HOST_DELAY": "60.1"},
            {"TITAN_FETCH_TIMEOUT": "31"},
        ):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    CrawlerConfig.from_env(values)


    def test_rejects_scheme_mismatched_standard_ports(self):
        for candidate in ("https://example.org:80/", "http://example.org:443/"):
            with self.subTest(candidate=candidate):
                self.assertEqual(resolve_public_url(candidate).reason, "port_not_allowed")


if __name__ == "__main__":
    unittest.main()
