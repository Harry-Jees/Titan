"""Shared fail-closed URL and DNS policy for Titan's public-web crawlers.

This module performs policy preflight only. Network transports must additionally
pin/revalidate the resolved address at connection time to prevent DNS rebinding.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urljoin, urlsplit


_PRIVATE_SUFFIXES = (
    ".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid",
)


@dataclass(frozen=True)
class URLDecision:
    allowed: bool
    reason: str
    normalized_url: str = ""
    addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class CrawlerConfig:
    """Validated per-run budgets; invalid environment values fail closed."""
    page_target: int = 10_000
    fetch_timeout: int = 20
    per_host_delay: float = 1.0
    max_page_bytes: int = 4_000_000
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "CrawlerConfig":
        values = os.environ if env is None else env
        try:
            page_target = int(values.get("TITAN_PAGE_TARGET", "10000"))
            fetch_timeout = int(values.get("TITAN_FETCH_TIMEOUT", "20"))
            per_host_delay = float(values.get("TITAN_PER_HOST_DELAY", "1"))
            max_page_bytes = int(values.get("TITAN_MAX_PAGE_BYTES", "4000000"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Crawler budget settings must be valid numbers.") from exc
        if not 1 <= page_target <= 10_000:
            raise ValueError("TITAN_PAGE_TARGET must be between 1 and 10000.")
        if not 1 <= fetch_timeout <= 30:
            raise ValueError("TITAN_FETCH_TIMEOUT must be between 1 and 30.")
        if not 1.0 <= per_host_delay <= 60.0:
            raise ValueError("TITAN_PER_HOST_DELAY must be between 1 and 60.")
        if not 100_000 <= max_page_bytes <= 4_000_000:
            raise ValueError("TITAN_MAX_PAGE_BYTES must be between 100000 and 4000000.")

        def domains(key: str) -> tuple[str, ...]:
            raw = values.get(key, "")
            result = []
            for item in raw.split(","):
                host = item.strip().lower().rstrip(".")
                if not host:
                    continue
                if "/" in host or ":" in host or " " in host:
                    raise ValueError(f"{key} must contain hostnames only.")
                result.append(host)
            return tuple(dict.fromkeys(result))

        return cls(page_target, fetch_timeout, per_host_delay, max_page_bytes,
                   domains("TITAN_ALLOWED_DOMAINS"),
                   domains("TITAN_DENIED_DOMAINS"))

    def host_allowed(self, host: str) -> bool:
        candidate = host.lower().rstrip(".")
        matches = lambda domain: candidate == domain or candidate.endswith("." + domain)
        if any(matches(domain) for domain in self.denied_domains):
            return False
        return not self.allowed_domains or any(matches(domain) for domain in self.allowed_domains)


def resolve_public_url(value: str, resolver=socket.getaddrinfo) -> URLDecision:
    """Validate a public HTTP(S) URL and reject any non-global DNS answer."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return URLDecision(False, "invalid_or_oversized_url")
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return URLDecision(False, "malformed_url")
    if scheme not in {"http", "https"}:
        return URLDecision(False, "unsupported_scheme")
    if not host or parsed.username is not None or parsed.password is not None:
        return URLDecision(False, "missing_host_or_credentials")
    if port is not None and port not in {80, 443}:
        return URLDecision(False, "port_not_allowed")
    if host == "localhost" or host.endswith(_PRIVATE_SUFFIXES):
        return URLDecision(False, "local_hostname")
    if any(ch.isspace() for ch in host) or "%" in host:
        return URLDecision(False, "malformed_hostname")

    try:
        literal = ipaddress.ip_address(host)
        addresses = (str(literal),)
    except ValueError:
        if "." not in host or host.startswith("."):
            return URLDecision(False, "invalid_hostname")
        try:
            answers = resolver(host, port or (443 if scheme == "https" else 80),
                               type=socket.SOCK_STREAM)
            addresses = tuple(sorted({
                ipaddress.ip_address(answer[4][0].split("%", 1)[0]).compressed
                for answer in answers
            }))
        except (OSError, ValueError, IndexError, TypeError):
            return URLDecision(False, "dns_resolution_failed")
        if not addresses:
            return URLDecision(False, "dns_no_answers")

    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        return URLDecision(False, "non_public_dns_answer", addresses=addresses)

    default_port = 443 if scheme == "https" else 80
    authority = f"[{host}]" if ":" in host else host
    if port is not None and port != default_port:
        authority += f":{port}"
    normalized = parsed._replace(scheme=scheme, netloc=authority).geturl()
    return URLDecision(True, "public", normalized, addresses)


def validate_redirect(source_url: str, location: str, resolver=socket.getaddrinfo) -> URLDecision:
    """Resolve and fully revalidate a redirect target; never auto-follow it."""
    if not location or len(location) > 2048:
        return URLDecision(False, "invalid_redirect_location")
    try:
        source = urlsplit(source_url)
        target = urljoin(source_url, location)
        parsed_target = urlsplit(target)
    except ValueError:
        return URLDecision(False, "malformed_redirect")
    if source.scheme.lower() == "https" and parsed_target.scheme.lower() == "http":
        return URLDecision(False, "https_downgrade")
    return resolve_public_url(target, resolver=resolver)
