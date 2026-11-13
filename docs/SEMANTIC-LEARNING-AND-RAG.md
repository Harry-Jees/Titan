# Titan semantic learning, RAG, and autonomous schedule

## Runtime architecture

Titan's Cloudflare Worker is the application runtime. Native Cloudflare Cron Triggers start a durable Cloudflare Workflow twice daily; GitHub Actions do not start research. The Workflow has a 30-minute wall-clock budget and persists progress across Worker isolate restarts.

The configured times are **06:00 and 18:00 Asia/Kolkata** (00:30 and 12:30 UTC). Cloudflare Cron expressions use UTC.

## Knowledge acquisition

1. Seed the frontier with a cross-disciplinary set of public technical, scientific, educational, and reference sources.
2. Fetch public HTML pages only, obey robots.txt, do not automatically follow redirects, reject private/local/IP-literal URLs, cap response sizes, and pace requests.
3. Ask GPT-OSS-20B to identify concise summaries, concepts, and facts. Page content is untrusted data, never instructions.
4. Store a fact only when the model supplies a quote that exactly appears in the fetched page. Each fact retains its source URL, content hash, and evidence quote.
6. Store synthesized knowledge units and metadata, not a mirror of every page. Deduplicate by stable content/fact hashes; unchanged pages are not re-analyzed and sources are refreshed weekly.
7. Generate BGE-M3 embeddings and persist compact float32 vectors in D1. If embedding inference is unavailable, FTS retrieval remains available.

## RAG

At question time Titan embeds the query, combines semantic cosine similarity with D1 FTS5 keyword retrieval, selects a bounded evidence context, includes unresolved conflicting claims when relevant, and asks GPT-OSS-20B to answer with source URLs. The current D1 vector scan ranks the most recent 250 embedded units; FTS5 can retrieve older units. If the knowledge base grows substantially, move the vector scan to Cloudflare Vectorize without changing the knowledge-unit format.

## Model updates versus knowledge updates

RAG updates Titan's usable knowledge immediately without changing GPT-OSS weights. The existing LoRA pipeline remains a separate candidate-training path: it requires curated examples, a held-out evaluation gate, and human review. Research artifacts must not be automatically used to pre-train or promote a model. Continuous blind fine-tuning risks catastrophic forgetting, poisoned data, and regressions.

## Cost guard

Cloudflare Workers AI documents a free allocation of 10,000 neurons per day. Titan reserves at most 7,000 neurons per UTC day, with a 2,500-neuron cap for each research run and a 2,000-neuron chat bucket. It never falls back to a paid model. Requests fail closed when the protected budget is exhausted. This is an application-side guard; check the Cloudflare dashboard to verify actual account usage and plan status.

## Activation

The code and Wrangler configuration do not activate the live Worker until reviewed, merged, and deployed. Before production activation:

1. Back up the titan-memory D1 database, then apply the pending repository migrations with `npx wrangler d1 migrations apply titan-memory --remote`. The live migration ledger currently records only 0001–0002, while several later tables already exist; the migration test reproduces that observed shape and verifies the full sequence. Migration 0007 adds the missing approval fingerprint, 0008 creates experience tables, and 0009 adds the semantic knowledge store.
2. Deploy the Worker with the Workers AI binding and Workflow binding.
3. Verify the two Cron Triggers in the Cloudflare dashboard.
4. Trigger one admin-only test run and inspect the research status endpoint before relying on the recurring schedule.

No live Worker, D1 migration, schedule, or billing setting is modified by this repository change.
