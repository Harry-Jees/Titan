import socket
import unittest
from unittest.mock import patch

import requests

from training.crawler_policy import CrawlerConfig
from training.pinned_http import (
    PinnedHTTPAdapter,
    UnsafeCrawlerURL,
    _PinnedHTTPSConnection,
    safe_get,
)


def answer(ip):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (ip, 443 if family == socket.AF_INET6 else 443))


class PinnedTransportTests(unittest.TestCase):
    def resolver(self, *ips):
        return lambda host, port, type: [answer(ip) for ip in ips]

    def test_https_pool_pins_public_ip_but_keeps_original_tls_host(self):
        adapter = PinnedHTTPAdapter(resolver=self.resolver("93.184.216.34"))
        request = requests.Request("GET", "https://docs.example.org/guide").prepare()
        pool = adapter.get_connection_with_tls_context(request, verify=True)
        try:
            self.assertEqual(pool.conn_kw["pinned_ip"], "93.184.216.34")
            self.assertEqual(pool.host, "docs.example.org")
        finally:
            adapter.close()

    def test_transport_rejects_private_and_mixed_dns_before_connect(self):
        for answers in (("127.0.0.1",), ("93.184.216.34", "10.0.0.4")):
            adapter = PinnedHTTPAdapter(resolver=self.resolver(*answers))
            request = requests.Request("GET", "https://blocked.example.org/").prepare()
            with self.subTest(answers=answers), self.assertRaises(UnsafeCrawlerURL):
                adapter.get_connection_with_tls_context(request, verify=True)
            adapter.close()

    def test_transport_enforces_configured_domain_allow_and_deny(self):
        config = CrawlerConfig(allowed_domains=("example.org",),
                               denied_domains=("private.example.org",))
        adapter = PinnedHTTPAdapter(resolver=self.resolver("93.184.216.34"), config=config)
        good = requests.Request("GET", "https://docs.example.org/").prepare()
        pool = adapter.get_connection_with_tls_context(good, verify=True)
        self.assertEqual(pool.conn_kw["pinned_ip"], "93.184.216.34")
        bad = requests.Request("GET", "https://private.example.org/").prepare()
        with self.assertRaises(UnsafeCrawlerURL):
            adapter.get_connection_with_tls_context(bad, verify=True)
        adapter.close()

    def test_socket_connects_to_pinned_ip_not_dns_hostname(self):
        connection = _PinnedHTTPSConnection(
            host="docs.example.org", port=443, pinned_ip="93.184.216.34"
        )
        sentinel = object()
        with patch("training.pinned_http.create_connection", return_value=sentinel) as connect:
            self.assertIs(connection._new_conn(), sentinel)
        self.assertEqual(connect.call_args.args[0], ("93.184.216.34", 443))
        self.assertEqual(connection.host, "docs.example.org")

    def test_safe_get_revalidates_redirect_and_blocks_downgrade(self):
        adapter = PinnedHTTPAdapter(resolver=self.resolver("93.184.216.34"))
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        class Response:
            def __init__(self, status, headers=None):
                self.status_code = status
                self.headers = headers or {}
                self.closed = False
            def close(self):
                self.closed = True

        responses = iter([Response(302, {"Location": "http://docs.example.org/clear"}), Response(200)])
        with patch.object(session, "get", side_effect=lambda *a, **k: next(responses)):
            with self.assertRaises(UnsafeCrawlerURL):
                safe_get(session, "https://docs.example.org/start")
        adapter.close()

    def test_safe_get_rejects_cross_host_redirect(self):
        adapter = PinnedHTTPAdapter(resolver=self.resolver("93.184.216.34"))
        session = requests.Session()
        session.mount("https://", adapter)

        class Response:
            status_code = 302
            headers = {"Location": "https://other.example.net/"}
            def close(self): pass

        with patch.object(session, "get", return_value=Response()):
            with self.assertRaises(UnsafeCrawlerURL):
                safe_get(session, "https://docs.example.org/start")
        adapter.close()

    def test_proxy_use_is_rejected(self):
        adapter = PinnedHTTPAdapter(resolver=self.resolver("93.184.216.34"))
        with self.assertRaises(requests.exceptions.ProxyError):
            adapter.get_connection("https://docs.example.org/", proxies={"https": "http://proxy.invalid"})
        adapter.close()


if __name__ == "__main__":
    unittest.main()
