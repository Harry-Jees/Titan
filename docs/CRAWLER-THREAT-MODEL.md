# Titan crawler threat model and configuration contract

Status: Python crawler transport is implemented; Worker-side arbitrary outbound
fetch is disabled. The shared `training.crawler_policy` module validates URLs,
DNS answers, redirects and bounded configuration. `training.pinned_http`
applies the policy at the connection boundary; both `training/crawl_web.py`
and `titan_explorer` use this adapter for HTTP and HTTPS requests. The
Cloudflare Worker research fetch path and cron triggers are disabled because
Workers `fetch()` cannot provide the required arbitrary-host DNS pinning and
TLS identity guarantee. `POST /research/run` fails closed with HTTP 503.

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
6. The Python transport resolves each hostname immediately before pool
   selection and pins the selected globally routable address to the socket.
   TLS SNI/certificate validation and the HTTP Host header continue to use
   the original hostname. A new request repeats resolution; a changed DNS
   answer selects a new pinned pool.

The policy rejects private, loopback, link-local, multicast, reserved and
otherwise non-global destinations. Redirects are followed manually, with
relative URL resolution and full DNS policy checks at every hop. The current
Python policy intentionally rejects cross-host redirects and HTTPS downgrade.
The adapter disables ambient proxies and refuses TLS verification opt-out.

## 3. Robots, pacing and content limits

- Fetch robots.txt for each origin and user agent; fail closed if unavailable
  or malformed. A confirmed 404 may be treated as no published rules.
- Apply a minimum one-second delay per host; requests to a host are sequential.
- Apply the configured request timeout and stream each response up to the
  per-response byte cap. Content-Length is an early rejection hint, not the
  only size check.
- Sitemap parsing has additional hard limits: 8 MB expanded bytes, a 20:1
  gzip expansion ratio, 100,000 XML elements, nesting depth 32, 5,000
  discovered locations per sitemap and at most 500 sitemap documents per seed.
  Gzip data is read through a bounded stream before XML parsing.
- HTML extraction is limited to the response byte cap and truncates stored
  text to 250,000 characters.
- The workflow caps successful page fetches with TITAN_PAGE_TARGET and has
  a 55-minute job timeout. The Python crawler additionally enforces aggregate
  response bytes, a process wall-clock deadline, a distinct-hostname cap and
  a bounded frontier queue. Robots, sitemap and page response bodies all count
  toward the aggregate byte budget. Per-host requests remain sequential and
  paced; there is no parallel crawler fan-out.
- The aggregate byte counter includes the final in-flight response chunk that
  crosses the cap; the stream is then closed immediately. The maximum read
  chunk is 64 KiB, so accounting cannot silently omit bytes already received.
- The checkpoint resumes pending URLs and refreshes previously fetched pages
  after a configurable age. fetched_pages measures successful page fetches;
  new_pages measures only content hashes not previously indexed. These are
  intentionally separate so an unchanged page still counts as researched.
- Store canonical URL, original URL, fetch time, content hash and source
  provenance with every accepted document. Robots decisions are enforced
  before page fetches but are not yet persisted as a per-document field.

## 4. Configuration contract

Configuration is read at process start, validated once and recorded in each
run manifest. Invalid values fail startup with a clear message; they are not
silently converted to zero or unbounded values.

| Setting | Default | Contract |
| --- | --- | --- |
| `TITAN_PAGE_TARGET` | 10,000 | Positive integer, maximum 10,000 |
| `TITAN_FETCH_TIMEOUT` | 20 seconds | 1–30 seconds |
| `TITAN_PER_HOST_DELAY` | 1 second | 1–60 seconds |
| `TITAN_MAX_PAGE_BYTES` | 4,000,000 | 100,000–4,000,000 bytes |
| TITAN_MAX_TOTAL_BYTES | 100,000,000 | 1 MB–1 GB response bytes per run |
| TITAN_MAX_RUN_SECONDS | 3,000 seconds | 60–3,300 seconds |
| TITAN_MAX_HOSTS_PER_RUN | 50 | 1–500 distinct hostnames |
| TITAN_RECRAWL_INTERVAL_SECONDS | 86,400 seconds | 1 hour–30 days |
| TITAN_MAX_QUEUE_SIZE | 20,000 | 100–50,000 queued URLs |
| `TITAN_ALLOWED_DOMAINS` | empty | Optional comma-separated hostname allowlist |
| `TITAN_DENIED_DOMAINS` | empty | Comma-separated denylist; deny wins over allow |
| `TITAN_CRAWLER_UA` | TitanKnowledgeBot | Descriptive, stable user agent |
| `TITAN_CRAWLER_CONTACT` | unset | Optional public contact URL/email; never a secret |
| `TITAN_CRAWL_SEEDS` | training/crawl_sources.txt | Operator-managed seed file |
| `TITAN_CRAWL_OUT` | training/crawled_pages.jsonl | Append-only corpus output |
| `TITAN_CRAWL_STATE` | training/crawl_state.json | Checkpoint state |

Secrets, user API keys, cookies and authorization headers are never accepted
as crawler configuration. Domain matching includes the exact hostname and
its subdomains; deny rules take precedence over allow rules.

The sitemap parser also has fixed internal ceilings: expanded payload 8 MB,
gzip expansion ratio 20:1, 100,000 XML elements, nesting depth 32, 5,000
locations per sitemap and 500 sitemap documents per seed. These are code
constants, not user-overridable environment settings.

The scheduled workflow sets a 600-successful-fetch target per run and a
55-minute job timeout. It overrides the Python deadline to 40 minutes to leave
time for OSINT collection and indexing. Defaults include a 100 MB aggregate
response-byte budget, 50-hostname budget, 20,000-URL queue cap and one-day
refresh interval. An explicit manual run may request up to 10,000 successful
page fetches, but aggregate byte, time, host and queue budgets remain in force.
The Actions summary reports fetched pages separately from new/changed pages.

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
| Oversized/chunked page response | Stop streaming at per-response byte cap |
| Gzip sitemap expansion bomb or excessive ratio | Stop before XML parsing |
| Excessive sitemap XML depth or element count | Reject the sitemap |
| Prompt injection in page text | Remains untrusted retrieval content |
| Invalid/oversized configuration | Fail startup; no unbounded fallback |

## 6. Worker outbound-fetch boundary

The Cloudflare Worker must not use ordinary `fetch()` for arbitrary crawler
URLs. The Workers `fetch()` API does not expose a supported per-request
validated-IP pin while preserving the original origin TLS identity. The
Workers TCP socket API exposes a hostname override for TLS, but it is not a
reliable production-edge substitute for this guarantee. Therefore:

- `src/research.ts` retains deterministic URL and content-extraction helpers,
  but `fetchResearchPage` fails closed without making a network request.
- The Worker research Workflow binding and twice-daily cron triggers are
  removed from `wrangler.toml`.
- `POST /research/run` returns HTTP 503 with an explicit explanation.
- The admin research status endpoint remains read-only for existing records.
- The Python crawler remains the supported outbound research path and uses
  `training.pinned_http` to pin each validated destination IP.

Do not re-enable Worker crawling until a separately operated egress service
has an independently tested DNS-resolution-to-connection binding, correct TLS
hostname verification, redirect revalidation, byte/time limits and an
explicit service authentication boundary. A hostname allowlist alone is not
a substitute for connection pinning.

## 7. Day 3 implementation boundary

The Python crawler entry points now use the shared policy and pinned transport.
The deterministic transport tests verify that the socket destination is the
validated IP while the original hostname remains the TLS/HTTP identity; they
also cover private/mixed DNS rejection, domain allow/deny, proxy rejection and
redirect downgrade/cross-host rejection. Robots fetches use the same bounded
transport and fail closed on timeout, oversized content and non-404 errors.

The Worker-side outbound fetch path is now explicitly disabled, including its
scheduled handler and cron triggers. It must not be re-enabled until a separate
egoing service proves DNS-resolution-to-connection pinning and TLS identity
verification on the production edge. No live Worker deployment or D1 mutation
is part of this milestone.


## 8. Resumable daily refresh and target semantics

The checkpoint stores a bounded pending frontier and per-URL last successful
fetch timestamps. Each run resumes pending URLs first, then adds newly
discovered sitemap URLs, then refreshes stale known URLs in oldest-first order.
Older checkpoints without timestamps are treated as stale once, allowing the
crawler to recover its existing corpus without discarding it. The refresh
interval prevents every scheduled run from repeatedly downloading the same
pages after the backlog has been processed.

The 600-page workflow target counts successful page fetches, including
unchanged pages. The separate new/changed count controls what enters the
current ingestion delta. A run that fetches zero pages must report that fact;
OSINT feed records are not counted as web pages. A target warning is visible
in the Actions summary when source availability, robots rules or a resource
budget prevents the target from being reached.
