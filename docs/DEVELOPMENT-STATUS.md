# Development status — 2026-11-07

## Implemented on development/titan-foundation
- Cloudflare Worker API for chat, conversations, memory, knowledge, evaluation, API-tool provisioning and per-user training preferences.
- Configurable OpenAI-compatible inference with bounded timeout and Workers AI fallback.
- Bearer-token namespace isolation and compatibility with the existing Titan auth map.
- Server-side conversation history; client-supplied history is ignored.
- Additive D1 migrations for memory, knowledge, conversations, encrypted API tools, pending approvals, audit, daily quotas and training records.
- Live API-tool pattern ported: per-user registry, AES-GCM credential storage, strict GET/POST parameter allowlists, exact hostname allowlisting, model-driven selection, 10-minute single-use POST approvals bound to a tool-definition fingerprint, visible bounded POST payload previews, audit logging and atomic daily quotas.
- Memory schema aligned with the existing live D1 table shape.
- JSON request bodies capped at 20 KB; external tool responses streamed with a 30 KB cap; redirects rejected; tool execution is disabled until an exact trusted-host allowlist is configured.
- Robots-aware crawler with same-host sitemap traversal, per-host pacing, bounded downloads and resumable state.
- Source-attributed chunking, topic coverage planning and candidate LoRA training/evaluation scripts.
- Daily research workflow at 06:30 UTC (12:00 PM IST): crawl, plan, chunk and upload artifacts. It does not call a teacher model or fine-tune.
- Separate curation worker at 03:30 UTC (09:00 AM IST): only processes conversations from users who explicitly opt in, screens sensitive content, grades at most eight pairs and stores candidates. Users can inspect, approve, reject, export only approved rows, or delete their own examples. The worker never updates model weights.
- Bounded self-build workflow is manual and PR-only; generated patches are restricted to source/tests/docs and now run TypeScript, Vitest and Python regression checks before a PR; no auto-merge or deployment.
- CI covers Python regression tests, TypeScript strict checking and Vitest.

## Verification
- Original portable starter Python suite passed locally (27 tests).
- Latest GitHub Actions run #106 (run ID 42375154081) passed on commit 0eba943ba6ae285222a35c14f9216f4d7ad72413: Python pytest, TypeScript typecheck and Vitest all succeeded.
- The development branch is 104 commits ahead of main; draft PR #1 is open and unmerged.
- Read-only Cloudflare inspection found the live D1 schema already contains the current tool and training tables, but its migration ledger differs from this repository's sequence. No migration was applied; staging compatibility still needs a deliberate check.
- No GPU training or teacher API call was run.

## Not done
- No model weights were trained or updated; no Hugging Face job was launched.
- No Cloudflare Worker, D1 database, secret, schedule or deployment was changed.
- No live D1 migration or production chat/tool test was run.
- Teacher-generated examples now require the exact source quote to appear in both the source excerpt and response, matching the LoRA validator. The held-out scorer no longer rejects correct uncertainty statements as refusals.
- Production authentication hardening, key rotation, advanced rate limiting and live end-to-end validation remain outstanding.

## Next engineering milestones
1. Verify the new tool-host allowlist, atomic approval consumption and fingerprint migration in CI.
2. Add route-level integration tests with disposable D1 and mocked external APIs.
3. Review key rotation and token lifecycle against the live gateway.
4. Stage-test all seven migrations against a disposable copy of the live schema.
5. Upgrade lexical retrieval to semantic/vector retrieval after verifying plan/API compatibility.
6. Expand independent evaluation before any candidate adapter can be considered for human review.
