# Titan zero-cost MVP acceptance audit (living checklist)

## Verified in the current development stack
- [x] GPT-OSS provider response handling includes Responses API shape coverage.
- [x] RAG ingestion balances OSINT and general knowledge records.
- [x] Optional OSINT feed failures are isolated from the main indexing pipeline.
- [x] Research crawler work adds resumable frontier, aggregate budgets and sitemap bounds.
- [x] URL validation includes public-address policy, malformed URL checks and budget-boundary regressions.
- [x] CI covers Python tests, TypeScript typecheck/tests and Wrangler dry-run.

## Acceptance gates
- [ ] Verify robots policy and robots caching in the execution path; document the failure policy.
- [ ] Prove checkpoint recovery from interrupted fetches/index writes without duplicate ingestion.
- [ ] Confirm DNS pinning is maintained for every redirect and request; test redirect chains and SSRF cases.
- [ ] Verify byte/time/page/domain/queue/concurrency/rate budgets are enforced across the whole run, not only per worker.
- [ ] Ensure crawler records remain untrusted data; retrieval must not elevate embedded instructions.
- [ ] Validate provenance and citations (canonical URL, fetch time, hash, source identity) end-to-end.
- [ ] Verify scheduled run permissions, pause/stop behavior, and failure reporting without secrets in logs.
- [ ] Run dry-run with local fixtures; avoid uncontrolled live crawling.
- [ ] Confirm free-tier constraints and identify any dependency requiring a paid plan; do not enable paid resources.
- [ ] Run complete tests, typecheck, lint and build from a clean checkout.

## Scope
Daily learning is retrieval, summarization/structuring, indexing and evaluation—not silent model-weight training. The crawler is bounded and incremental, not an internet-wide crawler.
