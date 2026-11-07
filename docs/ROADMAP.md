# Titan roadmap

## Foundation
- [x] Cloudflare Worker API shell
- [x] Configurable model route and Workers AI fallback
- [x] D1-backed bearer-scoped memory
- [x] Persistent conversation history and bounded retention
- [x] D1 lexical knowledge retrieval with source attribution
- [x] Additive SQL migrations and URL validation

## Next
- [ ] Import complete crawler, curation, training and evaluation scripts
- [ ] Import all regression tests and enable CI
- [ ] Port live API-tool registry and approval flow
- [ ] Port encrypted credential storage, audit trail and usage limits
- [ ] Add verified authentication, rate limiting and key rotation
- [ ] Upgrade lexical retrieval to semantic/vector retrieval after checking plan/API support
- [ ] Build query-driven source discovery with an approved budget
- [ ] Expand independent evaluations for factuality, reasoning, coding, tool use, privacy and adversarial behavior
- [ ] Add human-reviewed adapter promotion; never auto-deploy model weights

## Safety
No live service is replaced, no secrets are stored in Git, and no candidate adapter is promoted automatically.
