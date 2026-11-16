# Titan OSINT expansion

## Purpose

The scheduled research pipeline now combines the general public-reference crawler with a curated OSINT feed collector. It gathers public, non-authenticated feeds automatically and enables additional API-backed sources when the operator configures their own provider credentials.

## Registered automatic sources

The initial registry in `training/osint_sources.json` includes:

- CISA Known Exploited Vulnerabilities and cybersecurity advisories
- NIST National Vulnerability Database (NVD)
- GitHub Global Security Advisories
- CERT-EU and CERT/CC vulnerability advisories
- Google Project Zero, BleepingComputer, The Hacker News, Krebs on Security and Schneier on Security
- GDELT global news and events
- arXiv computer-science research
- OpenPhish community feed and abuse.ch URLhaus recent indicators

The sitemap crawler additionally discovers permitted public pages from MITRE ATT&CK, CISA, FIRST, Shadowserver, Spamhaus, abuse.ch, Shodan, Censys, urlscan.io, GreyNoise, VirusTotal, OpenStreetMap, Natural Earth, GeoNames, USGS, NASA, SEC EDGAR, Companies House, OpenCorporates, public government data portals and other seeds in `training/crawl_sources.txt`.

## Optional API-backed sources

The registry contains opt-in connectors for:
- AlienVault OTX subscribed pulses: repository secret `OTX_API_KEY`
- Shodan host search: repository secret `SHODAN_API_KEY`

If a secret is absent, that connector is skipped without failing the rest of the crawl. Obtain credentials directly from the provider and add them under GitHub **Settings → Secrets and variables → Actions → Repository secrets**. Never commit keys or put them in source URLs. Provider rate limits, terms and quotas still apply.

Additional high-value providers such as Censys, VirusTotal, GreyNoise, urlscan.io, SecurityTrails and AbuseIPDB can be added as dedicated connectors when their API credentials and permitted query scopes are configured. Some of these services are not general-purpose bulk export APIs; the collector must not assume that an account grants unlimited access.

## Execution and safety

- The scheduled workflow runs at **10:00 PM IST and 12:00 AM IST** (16:30 and 18:30 UTC).
- Each run first crawls public pages using Titan's DNS-pinned transport, then fetches registered feeds, then sends the combined cycle to the authenticated Titan RAG ingestion endpoint.
- Default page target is 600 per run; manual dispatch can select 1–10,000. The workflow timeout, per-host delay, 4 MB response ceiling and Worker ingestion body limit remain enforced.
- Feed parsing supports RSS/Atom XML, JSON APIs and plain-text indicator feeds. Records retain source identity, category, published timestamp and source URL.
- Robots.txt is checked before fetching each feed. Redirects are revalidated, DNS answers must be globally routable, the TCP destination is pinned, and TLS hostname verification remains enabled.
- Feed results are bounded per source and deduplicated within each cycle. Titan's ingestion layer handles persistent content deduplication.
- Private data, credentialed targets, authentication bypass, private social profiles and unrestricted scanning are out of scope. Internet-exposure providers are used only through their official APIs and the account's permitted access.

## Current limits

This is a broad, extensible source network, not an exhaustive crawl of every OSINT source or the whole internet. Some sources require API credentials, paid plans, a narrower query or manual approval. Some sites block automated collection or publish no machine-readable feed and will be skipped. The current Cloudflare RAG store is not an unlimited archive; larger scale will require durable object storage, queues, rate-limit-aware workers and a production search index.

The collected material is retrieval evidence, not model-weight training. Titan should surface provenance and dates and distinguish verified records from unconfirmed claims.
