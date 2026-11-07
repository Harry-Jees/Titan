# Development status — 2026-11-07

## Implemented on development/titan-foundation
- Cloudflare Worker API routes for chat, memory, conversations, knowledge and evaluation.
- Configurable OpenAI-compatible inference with bounded timeout and Workers AI fallback.
- Bearer-token namespace isolation and optional compatibility with the existing Titan auth map.
- Server-side persistent conversation history; client-supplied history is ignored.
- Additive D1 migrations for knowledge, user memories and conversations.
- URL validation, input limits, bounded conversation retention and regression tests.
- Source crawler with robots-aware access, same-host sitemap traversal, per-host pacing, bounded downloads and resumable state.
- Source-attributed knowledge chunking, coverage-goal planning and candidate training/evaluation scripts.
- Daily research workflow scheduled for 06:30 UTC (12:00 PM IST). It crawls, plans, chunks and uploads artifacts; it does not call a teacher model or fine-tune on its own.
- Bounded self-build workflow is manual and PR-only; it does not auto-merge or deploy.
- CI covers Python tests, TypeScript typechecking and Vitest.

## Verification
- The portable starter's original Python suite passed locally (27 tests).
- GitHub Actions Python tests passed during the repository import.
- GitHub Actions TypeScript install, strict typecheck and Vitest passed on commit `f6ff99e3542c75fa2d7bb9efd9ee76dedfea79ba`.
- Additional crawler-safety and training validation tests have since been added; their latest full CI run is still pending.
- No GPU training or teacher API call was run.

## Not done
- No model weights were trained or updated; no Hugging Face job was launched.
- No Cloudflare Worker, D1 database, secret, schedule or deployment was changed.
- No live D1 migration or end-to-end production chat test was run.
- The existing live API-tool registry, explicit tool-call approval, encrypted credential storage, audit records and usage limits have not yet been ported.

## Next engineering milestones
1. Finish and pass the expanded CI suite after the training/crawler imports.
2. Port live API-tool registry, tool approval, encrypted credentials, audit logging and usage limits.
3. Add verified authentication, rate limiting and key rotation.
4. Stage-test schema compatibility before any production integration.
5. Upgrade lexical retrieval to semantic/vector retrieval after checking current Cloudflare plan/API compatibility.
6. Add human-reviewed adapter promotion only after stronger independent evaluation.
