# Titan completion baseline

Audit date: 2026-11-16  
Repository: `Harry-Jees/Titan`  
Baseline branch: `feature/multilingual-rag-terms-20261115`  
Baseline commit: `2dbab36b1e53abfa48458035d7c134bd46c7fd6c`

Titan is the separate personal cloud AI agent. This plan treats the existing crawler, scheduled research workflow, RAG and experience-memory implementation as the baseline; it does not create a second crawler or a duplicate project.

## Current verified baseline

- Default branch is `main`; the latest development work is a stacked PR chain.
- Latest PR at audit: [#12 — multilingual hybrid RAG terms](https://github.com/Harry-Jees/Titan/pull/12), based on PR #11. PR #10 contains GPT-OSS semantic learning, hybrid RAG and native twice-daily research; PR #9 contains the 30-minute public-web exploration engine.
- Open PRs #1–#12; no open repository issues at this audit.
- Latest CI: [Titan CI #43632205484](https://github.com/Harry-Jees/Titan/actions/runs/43632205484), completed successfully for the baseline commit.
- Existing stack: Cloudflare Workers/TypeScript, D1, Workers AI, GPT-OSS-20B reasoning, BGE-M3 embeddings, FTS5 + vector retrieval, encrypted per-user API tools with approval/audit controls, public anonymous chat preview, opt-in conversation curation, and a PR-only self-build workflow.
- The semantic-learning branch defines native Worker cron runs at 06:00 and 18:00 IST with durable 30-minute research workflows; the separate curation worker is opt-in and does not train model weights.
- A separate Python `titan_explorer` supports manual 30-minute public-web sessions (default 500 pages, hard cap 1,500), robots checks, host pacing, public-IP checks, HTML/content caps, resumable session output and source hashes. Its output is currently a local JSONL artifact requiring human review/import; it is not yet a continuously scheduled crawler feeding the production knowledge store.
- Current D1 hybrid retrieval is a bounded prototype, not a billion-page production index. The README and scaling architecture already state this distinction.
- Stage A experience-memory work still lists restart persistence, held-out isolation and learned world-model/policy updates as outstanding. These are not required for the RAG-first web-learning MVP unless needed for safe release.

## v1 completion definition

Titan v1 is complete when the following end-to-end path is implemented and verified:

1. **Autonomous discovery and crawl:** scheduled discovery can run without a manual GitHub Actions click; crawl jobs are resumable, incremental and bounded by domain/page/byte/time budgets.
2. **Safe public-web policy:** robots.txt is honored and fails closed when policy cannot be checked; enforce HTTP(S), DNS/IP validation at connection time, SSRF/private-network protections, redirect revalidation, per-host rate limits, timeouts, content-type/size limits, and domain allow/deny controls. No logins, paywalls, CAPTCHA bypass, private endpoints or downloaded-code execution.
3. **Reliable ingestion:** extracted documents are canonicalized, deduplicated and stored with URL, fetch time, content hash, content type, crawl policy and provenance. Crawled text remains untrusted data and is never promoted to system instructions.
4. **Unified knowledge memory:** crawler output feeds the existing source-attributed knowledge/RAG pipeline without requiring manual artifact download/import. Re-crawls update changed sources and preserve history/provenance.
5. **Useful retrieval:** bounded hybrid retrieval returns relevant evidence with source links and freshness; multilingual lexical support and context budgets remain covered by tests.
6. **Agent integration:** GPT-OSS reasoning and existing API/tool calling can use retrieved knowledge; external tools remain allowlisted, approval-gated where mutating, audited and quota-bound.
7. **Daily learning:** scheduled learning discovers, extracts, indexes and evaluates new knowledge. This is RAG/knowledge learning; do not claim model-weight training unless a real training run and evaluation are performed.
8. **Cost and operations:** free-tier use is bounded and observable, with graceful quota exhaustion, backoff, pause/stop controls, run status, retries and failure isolation. No paid services are activated.
9. **Verification:** unit/integration tests cover robots, DNS/SSRF, redirects, limits, deduplication, restart/resume, ingestion, provenance, retrieval, prompt-injection isolation, provider failures and scheduler behavior. Typecheck, Vitest, Python tests, Wrangler dry-run and CI pass.

The target is a practical continuously expanding knowledge crawler, not unlimited crawling or an unsupported guarantee of billions of indexed pages.

## 15-day delivery sequence

| Day | Date | Titan milestone | Exit evidence |
|---|---|---|---|
| 1 | Nov 16 | Audit architecture, open PRs, CI and define MVP acceptance | This document and verified baseline |
| 2 | Nov 17 | Crawler threat model and configuration contract | URL policy, DNS/redirect threat tests |
| 3 | Nov 18 | Harden crawler transport and SSRF defenses | DNS/IP, redirect and timeout tests |
| 4 | Nov 19 | Add persistent crawl jobs/frontier and checkpoint model | Resume/restart tests |
| 5 | Nov 20 | Incremental fetch, canonicalization and deduplication | Conditional-fetch and content-hash tests |
| 6 | Nov 21 | Normalize extracted content and provenance records | Fixture ingestion tests |
| 7 | Nov 22 | Connect crawler output to existing knowledge ingestion | End-to-end local ingestion test |
| 8 | Nov 23 | Schedule autonomous crawl and enforce budgets | Scheduler, pause/stop and quota tests |
| 9 | Nov 24 | Integrate crawl results with hybrid RAG | Evidence and citation tests |
| 10 | Nov 25 | GPT-OSS answer grounding and source freshness | Grounded-answer regression suite |
| 11 | Nov 26 | API/tool workflow integration and isolation | Allowlist, approval and audit tests |
| 12 | Nov 27 | Daily learning/evaluation cycle | Idempotent scheduled learning test |
| 13 | Nov 28 | Security, privacy and failure-mode audit | SSRF, prompt injection, abuse and quota tests |
| 14 | Nov 29 | Full integration, cost and operational verification | Complete CI and dry-run evidence |
| 15 | Nov 30 | Titan v1 completion audit | Evidence-based completion report or exact remaining gaps |

## Working rules

- Inspect the actual latest branch, PRs, commits, issues and CI before each change; do not assume the previous run's branch is still current.
- Keep work on development/feature branches. Do not merge into `main`, deploy Workers, apply D1 migrations to live data or alter secrets without explicit approval.
- Never crawl without enforceable budgets and safety controls. Treat crawled content as untrusted.
- Use existing free-tier services and local tests; no paid resources, external teacher calls or GPU jobs without separate authorization.
- Do not claim the live Worker has a feature merely because a development branch contains it.
- A feature is complete only after implementation, tests, documentation and passing CI. Report blocked or incomplete work precisely.
