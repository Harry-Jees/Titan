# Titan roadmap

## Foundation — implemented on development/titan-foundation
- [x] Cloudflare Worker API shell and configurable inference/fallback
- [x] Bearer-token-scoped persistent memory and conversations
- [x] D1 knowledge indexing with source attribution
- [x] Per-user API tool registry and encrypted credential storage
- [x] Model-driven tool selection and explicit POST confirmation
- [x] Tool audit records and atomic per-user daily request limits
- [x] User-controlled opt-in for conversation curation
- [x] Separate scheduled curation worker with privacy screening and quality grading
- [x] Robots-aware daily research workflow and resumable crawler
- [x] Candidate LoRA training/evaluation scripts and held-out safety gate
- [x] Bounded self-build workflow that opens review PRs only
- [x] Python, TypeScript and Vitest CI

## Next
- [ ] Finish current expanded CI and fix any regressions
- [ ] Route-level tests using disposable D1 and mocked external APIs
- [ ] Verify auth-map rotation, token lifecycle, rate limiting and abuse controls
- [ ] Stage-test all migrations against a disposable copy of the live D1 schema
- [ ] Port any remaining live-only gateway behavior
- [ ] Semantic/vector retrieval after confirming current Cloudflare plan and API support
- [ ] Broader independent evaluations for factuality, reasoning, coding, tool use, privacy and adversarial behavior
- [ ] Human-reviewed candidate adapter promotion only after evaluation; never auto-deploy weights

## Safety and cost boundaries
No live Worker, D1 database, secret or schedule is modified by this repository work. The scheduled noon research workflow does not call a teacher model. Conversation curation is opt-in and stores candidates only. Teacher calls and GPU training remain separate, manual and budget-dependent. All production integration requires staging, review and explicit approval.
