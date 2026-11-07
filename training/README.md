# Titan candidate-training pipeline

This pipeline creates a **candidate LoRA adapter**, not a new foundation model and not a live model update.

## Pipeline
1. Crawl configured public sources while respecting robots rules, terms, privacy, copyright and licenses.
2. Chunk source pages with their provenance URLs.
3. Generate a bounded teacher dataset. Provider calls may cost money; only configure a provider with an approved budget.
4. Curate and manually review examples.
5. Keep the held-out evaluation set out of training. Reject duplicates, malformed examples, secret-shaped content, unsafe source URLs and insufficient source grounding.
6. Train a LoRA adapter with a license-compatible base model and bounded compute.
7. Compare base and candidate on the same held-out capability and safety cases.
8. Retain the candidate as an artifact. Human review is required; there is no automatic promotion.

## Caveats
The held-out set is small and keyword-oriented. It is a regression smoke test, not comprehensive safety certification, factuality grading or human review. Free GPU availability is not guaranteed. Training can fail due to memory, runtime or model-download limits.
