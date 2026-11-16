"""Shared fail-closed URL and DNS policy for Titan's public-web crawlers.

This module performs policy preflight only. Network transports must additionally
pin/revalidate the resolved address at connection time to prevent DNS rebinding.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
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
