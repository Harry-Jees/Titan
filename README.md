# Titan — personal autonomous AI agent

Titan is a separate, cloud-first personal agent. This repository contains a portable Cloudflare Workers foundation for chat, persistent memory, API tools, opt-in conversation curation, source-attributed knowledge, research automation, evaluation and bounded self-building.

**Safety boundary:** this is a development repository, not a deployed replacement for the existing live Titan services. No live Worker, D1 database, credential, schedule, model weight or paid compute resource is changed by this work.

## Stack
- Cloudflare Workers + TypeScript
- Cloudflare D1 for memory, conversations, knowledge, tool registry, approvals, audit, quotas and training records
- Configurable OpenAI-compatible inference with Workers AI fallback
- Robots-aware public research crawler and source-attributed chunking
- Opt-in conversation curation; candidate LoRA training is separate and manual
- PR-only self-build workflow; no auto-merge or deployment

## Local development
Requirements: Node.js 20+, npm, Python 3.11+.

    npm install
    python -m pip install -r training/requirements.txt
    npm run typecheck
    npm test
    python -m pytest -q

Apply migrations 0001 through 0007 in numeric order to a **development** D1 database. The schemas are aligned with the current live Titan D1 table shapes, but must still be applied to a staging copy first. Do not run them against the live database from this repository.

## Worker configuration
Main Worker: wrangler.toml, entry src/index.ts.

Separate opt-in curation Worker: wrangler.training.toml, entry src/training-pipeline.ts, cron 30 3 * * * (09:00 IST).

Both configs contain a placeholder D1 database ID. Replace it only with a development database ID before local testing or deployment.

Required bindings: DB (D1) and AI (Workers AI).

Optional secrets/vars:
- TITAN_ADMIN_TOKEN
- TITAN_API_BASE, TITAN_API_KEY, TITAN_MODEL
- TITAN_AUTH_MAP_B64 (compatibility mapping; secret only)
- TITAN_VAULT_KEY_B64 (32-byte AES-GCM key for provisioned API credentials)
- TITAN_TOOL_REGISTRY (server-managed tool definitions)
- TITAN_TOOL_HOST_ALLOWLIST (comma-separated exact trusted hostnames; no wildcards)
- TITAN_TOOL_SECRET_* (optional Worker secrets referenced by server-managed tool definitions only)
- TITAN_DAILY_REQUEST_LIMIT (default 200 per user per UTC day)
- TITAN_TRAINING_CRON_SECRET (optional HTTP trigger secret for the training worker)

Keep secrets out of source control. The fallback model is @cf/zai-org/glm-4.7-flash; availability and cost depend on provider and plan and are not guaranteed free.

## API
- GET /health
- POST /chat — message and optional conversationId
- GET /conversations, DELETE /conversations?id=...
- GET /memory?q=..., POST /memory
- GET /tools — list registered tools without exposing credentials
- POST /tools/provision — validate and save a per-user tool; credentials are AES-GCM encrypted
- DELETE /tools?name=...
- GET /training/preferences, POST /training/preferences — explicit user opt-in/out
- GET /training/examples, DELETE /training/examples?id=... — view or delete your own curation examples
- GET /training/examples/export — export only your own approved examples as JSONL
- POST /training/examples/review — approve/reject one of your own candidate examples
- POST /knowledge, GET /knowledge?q=... (admin token)
- POST /evaluate (admin token)

Conversation history is loaded server-side and scoped to the authenticated bearer namespace; client-supplied history is ignored. This is capability-token isolation, not a complete public account-authentication system. A public multi-user deployment still needs verified authentication, rate limits, abuse controls and key rotation.

Registered tools can be selected by the model and run with strict parameter allowlists. Provisioning and execution fail closed unless the target hostname exactly matches TITAN_TOOL_HOST_ALLOWLIST; do not add user-controlled domains, redirectors or untrusted hosts. Server-managed tools may reference only dedicated TITAN_TOOL_SECRET_* bindings, never general model, auth or admin secrets. POST tools create a 10-minute, single-use approval bound to a fingerprint of the tool definition; changing the tool invalidates the pending approval. Tool calls are audited. External tool metadata and responses are treated as untrusted data.

## Research and learning schedules
- **12:00 PM IST (06:30 UTC):** GitHub Actions daily research workflow. It crawls public sitemaps with robots-aware access, host pacing and bounded downloads, plans coverage gaps, creates source-attributed chunks and uploads a cycle artifact. It does not call a teacher model or fine-tune.
- **09:00 AM IST (03:30 UTC):** separate D1 curation worker. It processes only conversations from users who explicitly enable training_preferences, screens sensitive data, grades at most eight pairs and stores candidates. It does not update model weights.
- **Candidate LoRA training:** manual and separate. Teacher API calls may incur costs; GPU availability and model downloads are not guaranteed free. Candidates must pass held-out capability and safety checks and require human review. No adapter is automatically promoted, merged or deployed.

Crawling must respect source terms, robots rules, copyright, privacy and applicable law.

## Self-building
The self-build workflow is manual and bounded. It only proposes changes in approved source/test/docs paths, runs checks and opens a PR for human review. It cannot edit workflows, dependencies, secrets, deployment configuration or migrations, and never auto-merges.

## Public access

The Worker serves a browser-based Titan chat interface at `/`. Visitors can use it without registration: the page requests an isolated anonymous session from `POST /public/session` and then sends authenticated chat requests on the visitor's behalf. Session capabilities are stored in that browser only. Public-use limits and the frontend integration contract are documented in [docs/PUBLIC-ACCESS.md](docs/PUBLIC-ACCESS.md).

This is an anonymous public preview, not a user-account system. Do not store sensitive personal information in a shared browser, and do not share session tokens.

## Live integration boundary
This repository ports the live tool registry, credential encryption, explicit POST approval, tool audit, daily quota and opt-in training curation patterns. Before replacing or integrating with the live API, port and test remaining authentication hardening, key rotation, rate limiting, and any live-only business logic. No production deployment or live database migration has been performed.

See docs/DEVELOPMENT-STATUS.md, docs/LIVE-INTEGRATION.md and docs/ROADMAP.md.
