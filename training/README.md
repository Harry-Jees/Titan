# Titan candidate-training pipeline

This pipeline creates a **candidate LoRA adapter**, not a new foundation model and not a live model update.

## Pipeline
1. Crawl configured public sources while respecting robots rules, terms, privacy, copyright and licenses.
2. Chunk source pages with their provenance URLs.
3. Generate a bounded teacher dataset. Teacher calls are disabled unless TITAN_ALLOW_TEACHER_API=true is explicitly set; the default limit is 50 pages and 60 examples, with hard caps of 100 each. Provider calls may cost money, so do not enable this without an approved budget.
4. Preserve the exact source excerpt and its SHA-256 digest with each public-source example. The LoRA validator checks that the supporting quote appears in both the saved excerpt and answer, that the digest matches, and that the source URL is public.
5. Curate and manually review examples.
6. Keep the held-out evaluation set out of training. Reject duplicates, malformed examples, secret-shaped content, unsafe source URLs, source-quote mismatches and held-out overlap.
7. Train a LoRA adapter with a license-compatible base model and bounded compute.
8. Compare base and candidate on the same held-out capability and safety cases. The gate requires at least 4 capability, 3 safe-cybersecurity and 4 safety cases, unique IDs, exact suite parity, no safety regression and 100% safety pass rate by default.
9. Retain the candidate as an artifact. Human review is required; there is no automatic promotion.

## Caveats
The checked-in held-out set is a deterministic regression smoke test, not comprehensive safety certification, factuality grading or human review. Canary strings test whether a model repeats explicitly supplied sensitive markers; they do not prove real-world privacy isolation. Free GPU availability is not guaranteed. Training can fail due to memory, runtime or model-download limits.

## User-approved conversation examples

Conversation curation is disabled by default. A user must enable training in the app, inspect the candidate examples, and explicitly approve each example. They can delete individual examples or all of their examples at any time. The authenticated export endpoint returns only approved examples as JSONL. To include those rows in a candidate LoRA run, set TITAN_ALLOW_USER_CONVERSATION_DATA=true; the training script still checks secrets, held-out overlap, duplicates and minimum example counts. Do not combine another user's data or export it without their consent.
