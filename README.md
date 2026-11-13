# Titan — personal autonomous AI agent

Titan is a separate, cloud-first personal agent. This repository contains a portable Cloudflare Workers foundation for chat, persistent memory, API tools, opt-in conversation curation, source-attributed knowledge, autonomous research, evaluation and bounded self-building.

**Deployment boundary:** the public preview runs as a separate Worker at [titan-ai-core.harryjees.workers.dev](https://titan-ai-core.harryjees.workers.dev/). It does not replace the existing live `titan-agent-api` or `titan-training-pipeline`. It reuses the existing `titan-memory` D1 database and creates only additive public-session and knowledge tables; existing rows and secrets are not rewritten.

## Stack
- Cloudflare Workers + TypeScript
- Cloudflare D1 for the current prototype's memory, conversations, knowledge, tool registry, approvals, audit and quotas
- GPT-OSS-20B reasoning through Workers AI, protected by a conservative daily free-neuron reservation budget
- BGE-M3 embeddings and hybrid D1 FTS5 + vector RAG
- Robots-aware public research crawler and source-attributed chunking
- **RAG is Titan's primary long-term learning system.** It stores versioned, evidence-backed knowledge outside model weights and retrieves only relevant context at answer time.
- **LoRA training is optional experimentation only.** Titan does not require training, a local GPU, or model-weight updates to learn and use new information.
- PR-only self-build workflow; no auto-merge. The separate public Worker auto-deploys only from `development/titan-foundation`.

## Local development
Requirements: Node.js 20+, npm, Python 3.11+.

    npm install
    python -m pip install -r training/requirements.txt
    npm run typecheck
    npm test
    python -m pytest -q

Apply migrations 0001 through 0009 in numeric order to a **disposable development** D1 database. The schemas are aligned with the current live Titan D1 table shapes, but must still be applied to a staging copy first. Do not run them against the live database from this repository.

## Worker configuration
Main Worker: wrangler.toml, entry src/index.ts.

Separate opt-in curation Worker: wrangler.training.toml, entry src/training-pipeline.ts, cron 30 3 * * * (09:00 IST).

`wrangler.toml` binds the existing `titan-memory` D1 database for the isolated public preview. `wrangler.training.toml` remains a separate configuration; use a development database ID for local/staging training tests.

Required bindings: DB (D1), AI (Workers AI), and RESEARCH_WORKFLOW (Cloudflare Workflows).

Optional secrets/vars:
- TITAN_ADMIN_TOKEN
- TITAN_API_BASE, TITAN_API_KEY, TITAN_MODEL
- TITAN_AUTH_MAP_B64 (compatibility mapping; secret only)
- TITAN_VAULT_KEY_B64 (32-byte AES-GCM key for provisioned API credentials)
- TITAN_TOOL_REGISTRY (server-managed tool definitions)
- TITAN_TOOL_HOST_ALLOWLIST (comma-separated exact trusted hostnames; no wildcards)
- TITAN_TOOL_SECRET_* (optional Worker secrets referenced by server-managed tool definitions only)
- TITAN_DAILY_REQUEST_LIMIT (default 200 per user per UTC day)
- TITAN_TRAINING_CRON_SECRET (optional HTTP trigger secret for the optional training worker)

Keep secrets out of source control. The semantic-learning branch connects GPT-OSS-20B and BGE-M3 through the Worker AI binding. Titan reserves against a conservative 7,000-neuron daily estimate out of the documented 10,000 free Workers AI neurons per UTC day and has no paid-model fallback. Other Workers AI workloads in the same account share the free allocation. The live Worker is not updated by a branch push; apply the pending repository D1 migrations and deploy the reviewed branch before expecting this inference path to work. The live D1 ledger currently records only 0001–0002; CI includes a compatibility test against the observed live table shape.

## API
- GET /health
- POST /chat — message and optional conversationId
- GET /conversations, DELETE /conversations?id=...
- GET /memory?q=..., POST /memory
- GET /tools — list registered tools without exposing credentials
- POST /tools/provision — validate and save a per-user tool; credentials are AES-GCM encrypted
- DELETE /tools?name=...
- GET /experiences/episodes/:id/replay — deterministic read-only projection; never executes actions
- GET /experiences/episodes/:id/events?after=0&limit=200 — sequence-cursor event pages (limit 1–200; `nextAfter` is exclusive)
- GET /research/status and POST /research/run — admin-only research status and one-off test run
- GET /training/preferences, POST /training/preferences — explicit user opt-in/out
- GET /training/examples, DELETE /training/examples?id=... — view or delete your own curation examples
- GET /training/examples/export — export only your own approved examples as JSONL
- POST /training/rag-export — admin-only export of evidence-backed public RAG facts for optional local experiments
- POST /training/examples/review — approve/reject one of your own candidate examples
- POST /knowledge, GET /knowledge?q=... (admin token)
- POST /evaluate (admin token)

Conversation history is loaded server-side and scoped to the bearer namespace; client-supplied history is ignored. The public page obtains a random anonymous capability from `POST /public/session`; sessions are isolated per browser and rate-limited per session and network. This is anonymous capability-based access, not a user-account or identity-verification system. Admin and knowledge-ingestion routes remain protected.

Registered tools can be selected by the model and run with strict parameter allowlists. Provisioning and execution fail closed unless the target hostname exactly matches TITAN_TOOL_HOST_ALLOWLIST; do not add user-controlled domains, redirectors or untrusted hosts. Server-managed tools may reference only dedicated TITAN_TOOL_SECRET_* bindings, never general model, auth or admin secrets. POST tools create a 10-minute, single-use approval bound to a fingerprint of the tool definition; changing the tool invalidates the pending approval. Tool calls are audited. External tool metadata and responses are treated as untrusted data.

## Research and learning schedules
- **06:00 AM and 06:00 PM IST:** native Cloudflare Worker Cron Triggers start durable 30-minute research workflows. GPT-OSS converts pages into evidence-backed facts, concepts and concise knowledge units; BGE-M3 embeddings and FTS5 power hybrid RAG. GitHub Actions do not trigger research.
- **09:00 AM IST (03:30 UTC):** separate D1 curation worker. It processes only conversations from users who explicitly enable `training_preferences`, screens sensitive data, grades at most eight pairs and stores candidates. It does not update model weights.
- **No training dependency:** the research → extraction → indexing → retrieval loop is the complete learning path. LoRA candidate training is an optional, separately invoked local experiment; Titan remains fully usable when no training machine exists.

Crawling must respect source terms, robots rules, copyright, privacy and applicable law.

## RAG scale and performance

The current D1 FTS5 + cosine implementation is a functional prototype, **not a billion-page production index**. See [docs/RAG-SCALING-ARCHITECTURE.md](docs/RAG-SCALING-ARCHITECTURE.md) for the scale-out design. The key invariant is that query-time work is bounded: route to relevant partitions, retrieve a small candidate set using hybrid indexes, rerank only those candidates, and send a compact evidence pack to the reasoning model. Never scan the corpus or place the entire corpus in a prompt.

The design separates raw source storage, metadata, lexical indexes, vector indexes and derived knowledge. It supports incremental ingestion, deduplication, hierarchical routing, sharding, replicas, caching, selective graph retrieval and gradual migration from the current D1 prototype. Billions of pages are an architectural target, not a claim about the current deployment or free-tier capacity.

## Self-building
The self-build workflow is manual and bounded. It only proposes changes in approved source/test/docs paths, runs checks and opens a PR for human review. It cannot edit workflows, dependencies, secrets, deployment configuration or migrations, and never auto-merges.

## Public access

The public Titan preview is live: [Open Titan](https://titan-ai-core.harryjees.workers.dev/). The Worker serves a browser-based Titan chat interface at `/`. Visitors can use it without registration: the page requests an isolated anonymous session from `POST /public/session` and then sends authenticated chat requests on the visitor's behalf. Session capabilities are stored in that browser only. Public-use limits and the frontend integration contract are documented in [docs/PUBLIC-ACCESS.md](docs/PUBLIC-ACCESS.md).

This is an anonymous public preview, not a user-account system. Do not store sensitive personal information in a shared browser, and do not share session tokens.

## Live integration boundary
This repository ports the live tool registry, credential encryption, explicit POST approval, tool audit, daily quota and opt-in training curation patterns. Before replacing or integrating with the live API, port and test remaining authentication hardening, key rotation, rate limiting, and any live-only business logic. The public preview is deployed separately. The existing live API has not been replaced, and no existing live user rows, credentials or auth secrets have been rewritten.

See docs/DEVELOPMENT-STATUS.md, docs/LIVE-INTEGRATION.md and docs/ROADMAP.md.
