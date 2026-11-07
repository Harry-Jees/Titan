# Existing Titan deployment — integration boundary

The portable Worker is not a drop-in replacement for the existing live Titan services.

The live deployment has additional capabilities, including an API-tool registry, pending tool-call approvals, encrypted credential storage, tool audit records, usage limits and training-run metadata. These capabilities must be preserved and tested before this repository can replace or integrate with the live API.

## Safe integration sequence
1. Keep live Workers and D1 untouched during development.
2. Back up the live D1 database before any schema operation.
3. Keep `TITAN_AUTH_MAP_B64` in a Worker secret; never commit token mappings.
4. Review migration 0004 against the live conversations schema and stage-test it first.
5. Port tool approval, encrypted credentials, audit and rate-limit behavior.
6. Require reviewed PRs, staging verification and explicit approval before deployment.

This repository work has not changed any live Cloudflare resource.
