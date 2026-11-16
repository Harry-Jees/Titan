"""Requests transport that pins each validated DNS answer to the socket.

The URL hostname remains the HTTP Host header and TLS SNI/certificate name;
only the TCP destination is replaced with the public address validated for
this request. Redirects are handled explicitly by safe_get().
"""
from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import InvalidURL, ProxyError, TooManyRedirects
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.util.connection import create_connection

try:
    from .crawler_policy import resolve_public_url, validate_redirect
except ImportError:  # Direct script execution from the training directory.
    from crawler_policy import resolve_public_url, validate_redirect


class UnsafeCrawlerURL(ValueError):
    """Raised when a URL or redirect violates the crawler network policy."""


class _PinnedHTTPConnection(HTTPConnection):
    def __init__(self, *args, pinned_ip: str | None = None, **kwargs):
        if not pinned_ip:
            raise ValueError("A validated pinned IP is required.")
        self.pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        try:
            return create_connection(
                (self.pinned_ip, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except OSError as exc:
            raise NewConnectionError(self, f"Failed to connect to pinned address {self.pinned_ip}: {exc}") from exc


class _PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, *args, pinned_ip: str | None = None, **kwargs):
        if not pinned_ip:
            raise ValueError("A validated pinned IP is required.")
        self.pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        try:
            return create_connection(
                (self.pinned_ip, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except OSError as exc:
            raise NewConnectionError(self, f"Failed to connect to pinned address {self.pinned_ip}: {exc}") from exc


class _PinnedHTTPPool(HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection

    def __init__(self, *args, pinned_ip: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.conn_kw["pinned_ip"] = pinned_ip


class _PinnedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection

    def __init__(self, *args, pinned_ip: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.conn_kw["pinned_ip"] = pinned_ip


class PinnedHTTPAdapter(HTTPAdapter):
    """Resolve and pin a public IP for every HTTP request; never use proxies."""

    def __init__(self, resolver=None, config=None, pool_cache_size: int = 64, **kwargs):
        super().__init__(**kwargs)
        self.resolver = resolver
        self.config = config
        self.pool_cache_size = max(1, min(128, int(pool_cache_size)))
        self._pools: OrderedDict[tuple[str, str, int, str], object] = OrderedDict()
        self._pool_lock = RLock()

    def _pool_for_url(self, url: str):
        try:
            parsed = urlsplit(url)
            scheme = parsed.scheme.lower()
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError as exc:
            raise InvalidURL("Malformed crawler URL.") from exc
        if scheme not in {"http", "https"} or not host:
            raise InvalidURL("Only absolute HTTP(S) crawler URLs are allowed.")
        if self.config is not None and not self.config.host_allowed(host):
            raise UnsafeCrawlerURL("Host is outside the configured crawler allowlist or is denied.")

        decision = resolve_public_url(url, resolver=self.resolver or __import__("socket").getaddrinfo)
        if not decision.allowed or not decision.addresses:
            raise UnsafeCrawlerURL(f"Crawler URL rejected: {decision.reason}")
        pinned_ip = decision.addresses[0]
        key = (scheme, host, port, pinned_ip)
        with self._pool_lock:
            pool = self._pools.get(key)
            if pool is not None:
                self._pools.move_to_end(key)
                return pool
            pool_type = _PinnedHTTPSPool if scheme == "https" else _PinnedHTTPPool
            pool = pool_type(host=host, port=port, pinned_ip=pinned_ip, maxsize=1, block=True)
            self._pools[key] = pool
            while len(self._pools) > self.pool_cache_size:
                _, expired = self._pools.popitem(last=False)
                expired.close()
            return pool

    def get_connection(self, url, proxies=None):
        if proxies and any(proxies.values()):
            raise ProxyError("Crawler proxy use is disabled; direct pinned connections are required.")
        return self._pool_for_url(url)

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        if proxies and any(proxies.values()):
            raise ProxyError("Crawler proxy use is disabled; direct pinned connections are required.")
        return self._pool_for_url(request.url)

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        if verify is False:
            raise requests.exceptions.SSLError("TLS certificate verification cannot be disabled for crawler requests.")
        return super().send(request, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies)

    def close(self):
        with self._pool_lock:
            for pool in self._pools.values():
                pool.close()
            self._pools.clear()
        super().close()


def mount_pinned_transport(session: requests.Session, config=None, resolver=None) -> PinnedHTTPAdapter:
    """Mount the pinned adapter for both schemes and disable ambient proxies."""
    session.trust_env = False
    adapter = PinnedHTTPAdapter(config=config, resolver=resolver)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return adapter


def safe_get(
    session: requests.Session,
    url: str,
    *,
    max_redirects: int = 5,
    same_host_redirects: bool = True,
    **kwargs,
):
    """Fetch with explicit, revalidated redirects; each hop is DNS-pinned."""
    adapter = session.get_adapter(url)
    if not isinstance(adapter, PinnedHTTPAdapter):
        raise UnsafeCrawlerURL("A PinnedHTTPAdapter is required for crawler requests.")
    current = url
    original_host = (urlsplit(url).hostname or "").lower().rstrip(".")
    for hop in range(max_redirects + 1):
        response = session.get(current, allow_redirects=False, **kwargs)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("Location", "")
        response.close()
        if hop >= max_redirects:
            raise TooManyRedirects(f"More than {max_redirects} crawler redirects.")
        decision = validate_redirect(current, location, resolver=adapter.resolver or __import__("socket").getaddrinfo)
        if not decision.allowed:
            raise UnsafeCrawlerURL(f"Crawler redirect rejected: {decision.reason}")
        target_host = (urlsplit(decision.normalized_url).hostname or "").lower().rstrip(".")
        if same_host_redirects and target_host != original_host:
            raise UnsafeCrawlerURL("Cross-host crawler redirects are disabled.")
        current = decision.normalized_url
    raise TooManyRedirects("Crawler redirect limit exceeded.")
