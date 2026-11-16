# Titan RAG: scale-out architecture and performance contract

## Goal

Allow Titan's knowledge corpus to grow from thousands to millions and ultimately billions of crawled pages without making normal chat requests scan, load or reason over the entire corpus.

**Important current-state boundary:** the current implementation uses Cloudflare D1, FTS5 and application-side cosine similarity. It is a useful bounded prototype, not a billion-page vector-search service. This document specifies the evolution path; it does not claim that the current Worker or Free plan already provides billion-scale capacity.

## Core invariants

1. Corpus size must not determine prompt size. Only a small, evidence-ranked context pack reaches the reasoning model.
2. Corpus size must not cause a full scan on the request path. Retrieval uses prebuilt indexes, metadata filters, partition routing and bounded candidate counts.
3. Ingestion and serving are isolated. Crawling, parsing, embedding, compaction and index rebuilds cannot starve interactive queries.
4. Every extracted fact retains provenance, timestamps, content hashes, confidence and contradiction state.
5. Updates are incremental and idempotent. Re-crawling an unchanged page must not re-embed or re-index it.
6. Every expensive stage has a budget, timeout, quota and graceful fallback. Never silently switch to a paid provider.
7. Storage, indexing and compute are independently scalable. No single database or Worker is expected to hold the whole web corpus.

## Logical data planes

### 1. Immutable source archive
Store canonicalized page snapshots and extracted text in object storage, keyed by content hash and source identity. Keep metadata (canonical URL, domain, language, crawl time, license/robots decision, content type, hash, parser version and freshness) separately. Deduplicate identical content and near-duplicate boilerplate before chunking. Keep raw snapshots out of the hot query path.

### 2. Metadata and knowledge catalogue
Keep compact records for documents, chunks, entities, facts, provenance, freshness, access policy and index locations. Partition by stable document/domain identifiers and time. Use a database suited to metadata transactions and pagination; D1 remains suitable for the current small deployment, not an assumed global billion-row catalogue.

### 3. Lexical retrieval
Build an inverted full-text index (BM25 or equivalent) for exact terms, names, identifiers, quoted phrases and rare vocabulary. This is a strong low-cost candidate generator and a reliable fallback when embeddings are unavailable. Do not issue an unbounded SQL LIKE/FTS scan over the entire corpus.

### 4. Dense semantic retrieval
Generate embeddings asynchronously and store them in a dedicated approximate-nearest-neighbour (ANN) index. Use quantized/compressed vectors and disk-backed or storage-optimized indexes where appropriate; full-precision in-memory graphs for every vector are not the default billion-scale design. Partition the index into shards and replicate hot shards for query throughput and availability. Use ANN recall/latency measurements to tune index parameters.

### 5. Selective knowledge graph
Extract canonical entities and high-confidence relationships from valuable sources, not every sentence from every page. Use the graph for multi-hop questions and entity resolution. Keep edges linked to supporting passages and source records. A graph is an additional retrieval route, not a mandatory expensive transformation for the whole web.

## Ingestion pipeline

1. Discover URLs through allowed sources and crawl policies; respect robots.txt, terms, rate limits, copyright and applicable law.
2. Canonicalize URLs, normalize content and compute stable hashes.
3. Deduplicate exact and near-duplicate pages; identify boilerplate and low-value pages.
4. Classify language, topic, source quality, freshness and content type.
5. Chunk semantically with document/chunk lineage and exact offsets.
6. Extract entities, facts, claims and relationships with source evidence; preserve conflicts rather than overwriting them.
7. Generate embeddings in batches through a quota-aware queue.
8. Write immutable source objects, metadata, lexical records, vector records and derived facts through idempotent jobs.
9. Publish an index generation only after validation; retain the prior generation for rollback.
10. Revisit sources according to freshness and change signals. Reprocess only changed chunks or when the parser/embedding version changes.

Backpressure must pause or slow ingestion before it affects chat. Failed tasks go to a retry queue with bounded attempts and a dead-letter queue.

## Query-time retrieval path

1. Normalize the question and infer intent, entities, time range, language and required freshness.
2. Check answer and retrieval caches using a key that includes normalized query, filters, user scope and index generation.
3. Route to only relevant domain/topic/language/time partitions using metadata and a coarse semantic/topic router. If confidence is low, widen to a bounded fallback set.
4. Run lexical and ANN retrieval in parallel on the selected shards, with metadata filters applied before expensive ranking.
5. Fuse candidate lists (for example, reciprocal-rank fusion), deduplicate by source/chunk and apply freshness, authority and evidence-quality signals.
6. Rerank only a small candidate pool (for example, top 30–50), never the whole corpus.
7. Select a compact evidence pack (for example, 5–12 chunks subject to a strict token budget). Preserve citations and contradictory evidence.
8. If evidence is insufficient, perform a bounded second retrieval with a rewritten query or ask the live research subsystem for current sources. Do not fabricate confidence.
9. Send only the question and compact evidence pack to GPT-OSS. The model's context window is not the database.
10. Cache safe reusable retrieval results and record latency, recall proxies, source quality and answer feedback.

The example candidate counts are starting configuration values, not fixed universal limits. They must be tuned against Titan's real evaluation set and latency budget.

## Hierarchical partitioning

Use a coarse-to-fine index:
- Global catalogue: compact topic/domain/language/time summaries and shard routing metadata.
- Partition index: lexical and vector indexes for a manageable subject/domain/time slice.
- Local shard: ANN and lexical search over the relevant subset.
- Evidence store: fetch original text only for final candidates.

Use semantic clusters together with explicit dimensions (topic, domain, language, date and source class). Pure hash sharding balances storage but can force every query to fan out to every shard; routing metadata should reduce fan-out. Keep a bounded fallback route to protect recall when classification is uncertain.

## Hot, warm and cold knowledge

- **Hot:** frequently queried, recent, high-quality facts and chunks; cached retrieval results and compact indexes.
- **Warm:** the searchable long-tail index, available on demand.
- **Cold:** raw snapshots, older versions and low-frequency archival content; fetched only when needed.

Cold storage is not deleted knowledge. It is simply kept off the latency-sensitive path. Apply retention, deletion and source-removal policies consistently across snapshots, chunks, facts, embeddings and caches.

## Performance contract

Measure p50/p95/p99 latency separately for query embedding, routing, lexical search, ANN search, fusion, reranking, evidence fetch and model generation. Also measure:
- recall@k and nDCG on a fixed evaluation set;
- answer faithfulness and citation correctness;
- query fan-out (shards contacted) and candidate counts at every stage;
- cache hit rate and stale-cache rate;
- ingestion lag, freshness and retry/dead-letter rates;
- duplicate rate, storage per source and embedding/index cost;
- cost and quota consumption per 1,000 queries and per million ingested chunks.

Set explicit latency and spend SLOs only after benchmarking on the actual deployment tier. Do not promise a fixed millisecond target independent of hardware, corpus, traffic and model latency.

## Growth path

### Stage 0 — current prototype
D1 metadata, FTS5, bounded vector records, evidence-backed facts and scheduled research. Add hard query limits, pagination, caching, observability and tests. Keep corpus quotas small enough for the actual D1/Workers plan.

### Stage 1 — millions of chunks
Move raw page bodies to object storage; keep D1 as a compact catalogue only if measured row volume and query patterns remain within its limits. Introduce a dedicated lexical/vector index service or self-hosted index, background embedding queues, index generations and ingestion/serving isolation.

### Stage 2 — hundreds of millions of chunks
Partition lexical and vector indexes, use ANN compression and storage-optimized/disk-backed search, replicate hot shards, add hierarchical routing and multi-level caches. Run load tests and recall evaluation before increasing shard fan-out.

### Stage 3 — billions of pages
Operate distributed ingestion, metadata catalogues, object storage, lexical and vector indexes across multiple shards/replicas. Add automated rebalancing, compaction, index migrations, disaster recovery, regional routing and continuous quality/latency/cost monitoring. At this scale, infrastructure and bandwidth costs are real; no free-tier assumption is valid.

Each stage is a deliberate migration with benchmark gates. Do not switch to the next stage merely because the crawler has discovered more URLs.

## Safety, quality and governance

Treat page content as untrusted data and never execute crawled scripts or follow arbitrary redirects. Respect robots rules, publisher terms, copyright and applicable law. Keep source-level deletion and takedown propagation. Separate public-source knowledge from private user memory and tenant-specific data at the authorization layer. Prevent one user's queries, documents or caches from leaking into another user's context. Retain provenance and allow low-quality, stale or disputed sources to be downgraded or removed.

## LoRA relationship

RAG is Titan's complete required learning mechanism. LoRA training is not a prerequisite for ingestion, memory, retrieval or chat. If adapter experiments are ever run, they are optional offline research projects and cannot block the RAG pipeline.
