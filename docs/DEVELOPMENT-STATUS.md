# Development status — 2026-11-11


## Stage A experience-memory and simulation foundation — implementation branch

Implemented on the implementation/digital-experience-loop-20261111 branch:

- Added an additive D1 migration for user-scoped experience episodes and a versioned event log.
- Enforced append-only event records with SQLite triggers against updates and deletes.
- Added typed event validation for observations, predictions, proposed actions, validation decisions, outcomes, diagnoses, belief updates, and episode closure.
- Added authenticated episode/event create, list, append, and retrieval routes with per-user daily write quotas.
- Restricted episode modes to simulation and read_only; proposed actions are records only and are never executed by these endpoints.
- Added a standard-library-only deterministic toy balance simulator with pure prediction and measured transition output.
- Added absolute prediction-error scoring, evidence-priority failure classification, and a fixed PD baseline.
- Compared the fixed controller with a no-op on five deterministic held-out initial states; added a JSONL episode generator compatible with the Stage A event payloads.
- Added deterministic read-only event replay with sequence, schema-version, action-reference, and closure checks; replay never executes proposed actions.
- Validate each new event against the complete existing sequence before insertion; reject orphan approvals, outcomes without approval, duplicate action IDs, post-closure events, and appends beyond the 200-event replay window.
- Use an expected-sequence condition so concurrent stale appends fail with a conflict rather than creating a broken event stream.
- Added Vitest replay tests alongside event-schema tests, Python simulation tests, and SQLite migration tests.

The simulator is a fixed baseline, not a learned policy. Route-level disposable-D1 tests, persistence verification across process restart, held-out evaluation isolation, and a learned policy/world model remain outstanding. The migration has not been applied to live D1; no model training or external actions were run.

## Implemented on development/titan-foundation
- Cloudflare Worker API for chat, conversations, memory, knowledge, evaluation, API-tool provisioning and per-user training preferences.
- Public browser chat interface served from the Worker root; anonymous session bootstrap, random per-visitor namespace, hashed session capabilities, 30-day expiry, per-session and per-IP daily request caps, and additive D1 initialization for public sessions and knowledge retrieval.
- **Hosted inference disabled:** Workers AI binding, fallback model, and hosted-provider routing removed. Chat fails closed until Titan's own local model runtime is connected; no Cloudflare AI neurons are consumed by Titan inference.
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

## Training hardening added on 2026-11-08
- Teacher-generated dataset creation is disabled by default and capped at 100 pages / 100 examples when explicitly enabled.
- Public-source examples retain a source excerpt and SHA-256 digest; the LoRA validator verifies the cited quote against both excerpt and response.
- Held-out promotion now requires at least 4 capability, 3 safe-cybersecurity and 4 safety cases, unique IDs, exact suite parity and safety no-regression.
- Evaluation reports include the held-out dataset SHA-256. Base and candidate models are loaded separately so adapter attachment cannot mutate the baseline model.
- CI now simulates the observed live D1 table shapes in an isolated SQLite database, checking that existing memory/conversation rows survive and the pending-approval fingerprint column is additive.

## Training provenance hardening added on 2026-11-08
- The default Qwen2.5-0.5B-Instruct base is pinned to an immutable Hugging Face commit; custom base models require an explicit 40-character commit SHA.
- Training row selection is deterministic and independent of input JSONL order, with exact held-out source-excerpt hash overlap rejection.
- Candidate manifests now record library versions, trainer configuration/metrics, selected prompt fingerprints, data hashes and adapter files. Evaluation refuses missing/mismatched manifests or adapter artifacts.
- Promotion thresholds reject NaN, infinity and values outside 0–1. This is validation-only; no training or model promotion was run.

## Verification
- Original portable starter Python suite passed locally (27 tests).
- Public-access branch head `fc505245e2b78ab4a367240a0418e133fa2c873e` passed GitHub Actions run #149 (Python tests, TypeScript strict typecheck, Vitest, Wrangler dry-run bundle and short-lived deployment artifact).
- The development branch is ahead of main; draft PR #1 is open and unmerged.
- The noon research workflow is present on this branch but does not become active on the default branch until the PR is merged.
- Read-only Cloudflare inspection found the live D1 schema already contains the current tool and training tables, but its migration ledger differs from this repository's sequence. No migration was applied; staging compatibility still needs a deliberate check.
- No GPU training or teacher API call was run.

## Not done
- No model weights have been trained or updated yet; no Hugging Face job was launched. Local-only inference is now enforced in code and tested.
- The public Worker remains deployed, but the new local-only inference changes are on the development branch and await its automatic build/deployment. The existing deployed version may still have its AI binding until that build finishes.
- No live D1 migration or production chat/tool test was run.
- Teacher-generated examples now require the exact source quote to appear in both the source excerpt and response, matching the LoRA validator. The held-out scorer no longer rejects correct uncertainty statements as refusals.
- Production authentication hardening, key rotation, advanced rate limiting and live end-to-end validation remain outstanding.

## Next engineering milestones
0. Build and package Titan's own small local model, then run inference in the visitor's browser/device so the public service never pays for inference.
1. Verify the new tool-host allowlist, atomic approval consumption and fingerprint migration in CI.
2. Add route-level integration tests with disposable D1 and mocked external APIs.
3. Review key rotation and token lifecycle against the live gateway.
4. Stage-test all seven migrations against a disposable copy of the live schema.
5. Upgrade lexical retrieval to semantic/vector retrieval after verifying plan/API compatibility.
6. Expand independent evaluation before any candidate adapter can be considered for human review.
