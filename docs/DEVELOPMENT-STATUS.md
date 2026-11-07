# Development status — 2026-11-07

## Implemented on development/titan-foundation
- Cloudflare Worker API for chat, conversations, memory, knowledge, evaluation, API-tool provisioning and per-user training preferences.
- Configurable OpenAI-compatible inference with bounded timeout and Workers AI fallback.
- Bearer-token namespace isolation and compatibility with the existing Titan auth map.
- Server-side conversation history; client-supplied history is ignored.
- Additive D1 migrations for memory, knowledge, conversations, encrypted API tools, pending approvals, audit, daily quotas and training records.
- Live API-tool pattern ported: per-user registry, AES-GCM credential storage, strict GET/POST parameter allowlists, model-driven selection, 10-minute POST approval, audit logging and atomic daily quotas.
- Memory schema aligned with the existing live D1 table shape.
- JSON request bodies capped at 20 KB; external tool responses streamed with a 30 KB cap; redirects rejected.
- Robots-aware crawler with same-host sitemap traversal, per-host pacing, bounded downloads and resumable state.
- Source-attributed chunking, topic coverage planning and candidate LoRA training/evaluation scripts.
- Daily research workflow at 06:30 UTC (12:00 PM IST): crawl, plan, chunk and upload artifacts. It does not call a teacher model or fine-tune.
- Separate curation worker at 03:30 UTC (09:00 AM IST): only processes conversations from users who explicitly opt in, screens sensitive content, grades at most eight pairs and stores candidates. It never updates model weights.
- Bounded self-build workflow is manual and PR-only; no auto-merge or deployment.
- CI covers Python regression tests, TypeScript strict checking and Vitest.

## Verification
- Original portable starter Python suite passed locally (27 tests).
- GitHub Actions Python tests and TypeScript/Vitest passed on commit 4eeed910a1d8d30350a28687cc4cad765fa344dc.
- Additional tests for opt-in curation, schema compatibility and body-size limits have since been added; the newest full CI run is pending.
- No GPU training or teacher API call was run.

## Not done
- No model weights were trained or updated; no Hugging Face job was launched.
- No Cloudflare Worker, D1 database, secret, schedule or deployment was changed.
- No live D1 migration or production chat/tool test was run.
- Production authentication hardening, key rotation, advanced rate limiting and live end-to-end validation remain outstanding.

## Next engineering milestones
1. Finish the latest expanded CI run and fix any failures.
2. Add route-level integration tests with disposable D1 and mocked external APIs.
3. Review key rotation and token lifecycle against the live gateway.
4. Stage-test all six migrations against a disposable copy of the live schema.
5. Upgrade lexical retrieval to semantic/vector retrieval after verifying plan/API compatibility.
6. Expand independent evaluation before any candidate adapter can be considered for human review.
