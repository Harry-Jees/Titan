# Titan — personal autonomous AI agent

Titan is a separate, cloud-first personal agent. This repository is the portable Cloudflare Worker foundation for chat, user-scoped memory, persistent conversations, source-attributed knowledge retrieval, model fallback, evaluation, and bounded self-building.

**Safety boundary:** this is a development foundation, not a deployed replacement for the existing Titan Cloudflare services. No live Worker, D1 database, credentials, schedule, model weights, or paid compute are changed by this repository work.

## Stack
- Cloudflare Workers + TypeScript
- Cloudflare D1 for memory, conversations, knowledge and evaluation records
- Configurable OpenAI-compatible model provider with Workers AI fallback
- Scheduled data curation and candidate LoRA evaluation (no automatic model promotion)
- Bounded self-build workflow that opens a PR for human review

## Local development
Requirements: Node.js 20+, npm, Python 3.11+.

```bash
npm install
python -m pip install -r training/requirements.txt
npm run typecheck
npm test
python -m pytest -q
```

Apply SQL migrations 0001 through 0004 in order to a **development** D1 database. Do not run them against the live Titan database until backed up and reviewed.

## Worker configuration
Required bindings: `DB` (D1) and `AI` (Workers AI). Optional secrets: `TITAN_ADMIN_TOKEN`, `TITAN_API_BASE`, `TITAN_API_KEY`, `TITAN_MODEL`, and `TITAN_AUTH_MAP_B64`. Keep secrets out of source control. The fallback model is `@cf/zai-org/glm-4.7-flash`; availability and cost depend on provider/plan and are not guaranteed free.

## API
- `GET /health`
- `POST /chat` — `{ "message": "...", "conversationId": "optional-id" }`
- `GET /conversations`, `DELETE /conversations?id=...`
- `GET /memory?q=...`, `POST /memory`
- `POST /knowledge`, `GET /knowledge?q=...` (admin token)
- `POST /evaluate` (admin token)

Conversation history is loaded server-side and scoped to the bearer namespace; client-supplied history is ignored. This is capability-token isolation, not a complete public account-authentication system. A public multi-user deployment still needs verified authentication, rate limits, abuse controls and key rotation.

## Learning and self-building
The daily learning workflow is scheduled for 06:30 UTC (12:00 PM IST), subject to GitHub Actions delays. It can crawl configured public sources, curate grounded examples, attempt candidate LoRA training and evaluate candidates against a held-out suite. Provider calls can incur charges; configure them only with an approved budget. Crawling must respect source terms, robots rules, copyright, privacy and applicable law. No adapter is auto-promoted, merged or deployed.

The self-build workflow is constrained and PR-only. Review every proposed change.

## Live integration boundary
The existing live Titan services have additional capabilities including API-tool registry, explicit tool-call approval, encrypted credentials, audit records and usage limits. These must be ported and tested before this foundation can replace or integrate with the live API. See [development status](docs/DEVELOPMENT-STATUS.md), [live integration](docs/LIVE-INTEGRATION.md), and [roadmap](docs/ROADMAP.md).

## Status
Work is on `development/titan-foundation`. The starter's Python suite currently passes locally (27 tests). TypeScript/Vitest verification still needs a clean dependency install. No model training, production deployment or live database migration has been performed.
