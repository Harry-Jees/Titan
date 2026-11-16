# Titan crawler threat model and configuration contract

Status: Day 2 security contract. This document defines the policy every
crawler entry point must share. It does not claim that the current scheduled
Worker or Python crawler already enforces every control. The standalone
`training.crawler_policy` module supplies a testable URL/DNS/redirect policy;
Day 3 wires the policy into active network transports and closes connection-
time DNS rebinding gaps.

## 1. Assets and trust boundaries

**Protect:** Titan's Worker and D1 services, credentials, user memory, API
tools, internal metadata endpoints, crawler runtime, knowledge index, and
source provenance.

**Untrusted inputs:** seed URLs, discovered links, HTTP redirects, DNS answers,
robots.txt, sitemap XML, page headers, HTML, extracted text, and model-produced
search suggestions.

**Trust boundary:** fetched page content is evidence only. It must never
become system/developer instructions, tool authorization, configuration,
credentials, or executable code. Prompt-injection text stays inside a
retrieval-data boundary and is quoted/cited as source content.

## 2. URL acceptance policy

A candidate URL is accepted only when all checks pass:

1. Scheme is HTTP or HTTPS; hostname exists; URL has no username/password.
2. Only ports 80 and 443 are allowed by default.
3. Reject localhost names, private/internal suffixes, IP literals that are
   not globally routable, malformed hosts, and URLs longer than 2,048 chars.
4. Resolve DNS before a request. Fail closed on resolution errors, empty
   answers, malformed answers, or if **any** A/AAAA answer is non-global.
5. Every redirect is a new untrusted URL: resolve relative locations, reject
   HTTPS-to-HTTP downgrade, and rerun the full URL and DNS policy before
   following it. Never rely on the original URL's DNS decision.
6. Connection-time address pinning/revalidation is required to defeat DNS
   rebinding. A preflight DNS lookup alone is not sufficient; the HTTP
   transport must connect only to a validated address while preserving TLS
   hostname verification and HTTP Host semantics.

The policy rejects private, loopback, link-local, multicast, reserved and
otherwise non-global destinations. It must not follow redirects automatically.

## 3. Robots, pacing and content limits

- Fetch robots.txt for each origin and user agent; fail closed if unavailable
  or malformed. A confirmed 404 may be treated as no published rules.
- Apply a minimum one-second delay per host by default; never parallelize
  requests to the same host without a stricter explicit policy.
- Use finite connect/read timeouts, bounded retries with exponential backoff
  and jitter, and a global wall-clock deadline.
- Accept HTML/XHTML for page extraction. Sitemap/XML is a separate parser
  path with byte, decompression-ratio, element-count and nesting limits.
- Stream response bodies and stop at the configured byte cap; never trust
  Content-Length alone.
- Bound pages per run, domains per run, total bytes, per-host requests,
  queue size, extracted characters and wall-clock duration.
- Store canonical URL, original URL, fetch time, status, content type, hash,
  robots decision and crawl-policy version with every accepted document.

## 4. Configuration contract

Configuration is read at process start, validated once and recorded in each
run manifest. Invalid values fail startup with a clear message; they are not
silently converted to zero or unbounded values.

| Setting | Default | Contract |
| --- | --- | --- |
| `TITAN_PAGE_TARGET` | 10,000 | Positive integer; hard-capped by deployment policy |
| `TITAN_FETCH_TIMEOUT` | 20 seconds | 1–30 seconds |
| `TITAN_PER_HOST_DELAY` | 1 second | At least 1 second |
| `TITAN_MAX_PAGE_BYTES` | 4,000,000 | 100,000–4,000,000 bytes |
| `TITAN_CRAWLER_UA` | TitanKnowledgeBot | Descriptive, stable user agent |
| `TITAN_CRAWLER_CONTACT` | unset | Optional public contact URL/email; never a secret |
| `TITAN_CRAWL_SEEDS` | training/crawl_sources.txt | Operator-managed seed file |
| `TITAN_CRAWL_OUT` | training/crawled_pages.jsonl | Append-only corpus output |
| `TITAN_CRAWL_STATE` | training/crawl_state.json | Checkpoint state |

Secrets, user API keys, cookies and authorization headers are never accepted
as crawler configuration. Domain allow/deny policy must be explicit and
deny rules take precedence. Production scheduling must expose pause/stop and
budget exhaustion states.

## 5. Abuse cases and required tests

| Threat | Required test / expected result |
| --- | --- |
| Private IPv4/IPv6, loopback, link-local, metadata IP | Reject before request |
| Public hostname resolves to mixed public/private IPs | Reject entire host |
| DNS fails or returns no answers | Fail closed |
| DNS rebinding between validation and connection | Transport pins/revalidates; never reaches private address |
| Redirect to localhost/private IP or a new mixed-answer host | Revalidate and reject |
| HTTPS redirect to HTTP | Reject downgrade |
| Credentials in URL or nonstandard port | Reject |
| robots.txt timeout/5xx/oversized body | Fail closed |
| Oversized/chunked response | Stop streaming at byte cap |
| Prompt injection in page text | Remains untrusted retrieval content |
| Invalid/oversized configuration | Fail startup; no unbounded fallback |

## 6. Day 2 implementation boundary

The pure policy helper and deterministic tests cover URL syntax, DNS answer
classification, fail-closed resolution and redirect destination policy.
They are not a substitute for connection-time pinning. Day 3 must integrate
this contract into `training/crawl_web.py` and `titan_explorer`, including
safe redirect handling, DNS rebinding resistance, robots transport, and
bounded request behavior. No live Worker deployment or D1 mutation is part
of this milestone.
