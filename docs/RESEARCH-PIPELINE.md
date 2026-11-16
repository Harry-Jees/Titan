# Titan scheduled research and callable knowledge

## What runs

Titan's public-web crawler runs from a GitHub Actions runner, not from the Cloudflare Worker. The runner uses the existing shared Python transport (training.pinned_http) which resolves each hostname, rejects non-global DNS answers, pins the validated address to the TCP socket, preserves TLS hostname verification, and revalidates every redirect. Worker-side arbitrary outbound fetching remains disabled.

- **Daily schedule:** 06:30 UTC / 12:00 PM India Standard Time.
- **On demand:** run Actions → Titan Secure Research Crawler → Run workflow.
- **Default budget:** 180 new pages and up to 300 knowledge chunks per run.
- **Persistence:** GitHub Actions cache retains the crawler's URL/hash checkpoint and public crawl corpus between runs.
- **Indexing:** new text is split into bounded chunks and sent in batches of at most 25 to the authenticated Titan POST /knowledge endpoint. Titan's existing BGE-M3 + lexical RAG path makes indexed material retrievable during normal chat.
- **No model training required:** new knowledge is indexed as evidence-backed retrieval context. It does not alter model weights.

## Expertise coverage

The operator-managed training/crawl_sources.txt covers AI/ML, software engineering, mathematics, physics, engineering, biology, public health, economics, public data, climate, environment, history, philosophy, culture, law, standards, governance and current affairs. Coverage is intentionally source-diverse rather than dependent on a single search provider.

This is a growing reference corpus, not a claim that Titan has exhaustively crawled the internet or has professional qualifications. Source quality, freshness, conflicting evidence and citations still matter. The crawler respects robots.txt, source terms, pacing and byte/page limits; unavailable or disallowing sources are skipped.

## One-time GitHub configuration

1. In **Settings → Secrets and variables → Actions → Secrets**, add **TITAN_ADMIN_TOKEN**. Its value must exactly match the TITAN_ADMIN_TOKEN secret configured on the Titan Worker that serves /knowledge.
2. Optionally add the repository variable **TITAN_API_BASE** if the deployed Worker origin differs from the default https://titan-ai-core.harryjees.workers.dev.
3. Run the workflow manually with a small page target (for example, 10) and verify the workflow summary and Titan's admin-only GET /knowledge count before increasing the budget.

The admin token is read only from GitHub Actions secrets and is sent over HTTPS. It is never written to crawler state, artifacts, logs, source files or cache. The crawler runner uses the token only for the knowledge-ingestion endpoint.

## Calling the knowledge

After indexing, ask Titan questions naturally in chat. Titan's existing chat route retrieves a small, relevant evidence pack from the RAG index and should cite source URLs when it uses that material. The corpus is not inserted wholesale into the prompt. For a fresh topic, trigger the workflow manually, wait for indexing to complete, then ask Titan.

The GitHub workflow is an operator-controlled on-demand research trigger. The public Worker POST /research/run endpoint remains disabled; do not expose a public crawl trigger or restore Worker fetch() for arbitrary URLs.

## Operational limits

- The default run is deliberately bounded; it does not try to crawl billions of pages in one job.
- The current D1 + FTS5 + vector implementation is a prototype, not a billion-page production index. See RAG-SCALING-ARCHITECTURE.md.
- Embedding/indexing is subject to the Worker's available AI quota. Batches are bounded and ingestion retries rate limits and transient server errors.
- GitHub Actions cache is a resumable convenience, not a durable archive. For larger corpora, move raw page storage and crawler checkpoints to dedicated object storage/queue infrastructure.
- Never place user conversations, private URLs, credentials, cookies or API keys in the public research corpus.
