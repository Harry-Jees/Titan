# Titan candidate-training pipeline

This pipeline creates a **candidate LoRA adapter**, not a new foundation model and not a live model update.

## Pipeline
1. Crawl configured public sources while respecting robots rules, terms, privacy, copyright and licenses.
2. Chunk source pages with their provenance URLs.
3. Generate a bounded teacher dataset. Teacher calls are disabled unless TITAN_ALLOW_TEACHER_API=true is explicitly set; the default limit is 50 pages and 60 examples, with hard caps of 100 each. Provider calls may cost money, so do not enable this without an approved budget.
4. Preserve the exact source excerpt and its SHA-256 digest with each public-source example. The LoRA validator checks that the supporting quote appears in both the saved excerpt and answer, that the digest matches, and that the source URL is public.
5. Curate and manually review examples.
6. Keep the held-out evaluation set out of training. Reject duplicates, malformed examples, secret-shaped content, unsafe source URLs, source-quote mismatches and held-out overlap.
7. Train a LoRA adapter with a license-compatible base model and bounded compute. Titan pins the default Qwen2.5-0.5B-Instruct base to an immutable Hub commit; any alternative base requires TITAN_BASE_MODEL_REVISION to be a full 40-character commit SHA. The deterministic seeded sample is independent of input-file row order.
8. Compare base and candidate on the same held-out capability and safety cases. The gate requires at least 4 capability, 3 safe-cybersecurity and 4 safety cases, unique IDs, exact suite parity, no safety regression and 100% safety pass rate by default.
9. Retain the candidate as an artifact. The manifest records base revision, training/held-out hashes, selected-prompt fingerprint, package versions, trainer metrics and adapter files. Evaluation refuses an adapter if its manifest, base revision, adapter files or held-out digest do not match. Human review is required; there is no automatic promotion.

## Deterministic Stage A experience lab

Titan includes a standard-library-only toy balance simulator. It is a local
deterministic environment, not a robot bridge and not a model-training job.
It provides pure next-state prediction, measured outcomes, a fixed PD baseline,
prediction-error scoring, evidence-priority failure classification, and
ordered event records matching the Stage A API.

Run one episode:

~~~bash
python training/experience_lab.py --initial-angle 0.2 --initial-velocity 0.0
~~~

Write a JSONL trace for inspection or later ingestion through the authenticated
experience API:

~~~bash
python training/experience_lab.py --episode-id toy-balance-run-0001 --output /tmp/titan-experience.jsonl
~~~

The fixed controller is only a baseline, not a learned policy. Tests compare it
with a no-op on five deterministic held-out initial states. No physical
actuator, external tool, hosted model, or GPU is used by this lab.

## Caveats
The checked-in held-out set is a deterministic regression smoke test, not comprehensive safety certification, factuality grading or human review. Canary strings test whether a model repeats explicitly supplied sensitive markers; they do not prove real-world privacy isolation. Free GPU availability is not guaranteed. Training can fail due to memory, runtime or model-download limits.

## User-approved conversation examples

Conversation curation is disabled by default. A user must enable training in the app, inspect the candidate examples, and explicitly approve each example. They can delete individual examples or all of their examples at any time. The authenticated export endpoint returns only approved examples as JSONL. To include those rows in a candidate LoRA run, set TITAN_ALLOW_USER_CONVERSATION_DATA=true; the training script still checks secrets, held-out overlap, duplicates and minimum example counts. Do not combine another user's data or export it without their consent.


## Reproducibility and candidate integrity

The default base revision is pinned to 7ae557604adf67be50417f59c2c2f167def9a775. If TITAN_BASE_MODEL is changed, set TITAN_BASE_MODEL_REVISION to that repository's immutable 40-character commit SHA; floating branches and tags are rejected. The training sample is sorted and then shuffled with the configured seed before applying the row cap, so reordering the JSONL file does not change the selected sample.

The evaluator verifies the candidate manifest against the exact base model, base revision and held-out dataset SHA-256 before loading either model. Promotion thresholds must be finite values in the inclusive range 0–1. These checks improve reproducibility and prevent accidental mismatched comparisons; they do not replace human review or independent safety evaluation.

## Automatic RAG-to-LoRA training (local runner)

The core Worker exposes an authenticated `POST /training/rag-export` endpoint.
It exports only public, evidence-backed, non-conflicting RAG facts with their
source URL, exact supporting quote, source excerpt and SHA-256 digest. It does
not export user conversations or unresolved contradictory facts.

On a machine you control, install the optional training dependencies from
`training/requirements.txt`, make sure CUDA and at least 8 GiB GPU VRAM are
available, then set:

```bash
export TITAN_TRAINING_EXPORT_URL="https://YOUR-TITAN-WORKER/training/rag-export"
export TITAN_ADMIN_TOKEN="YOUR_EXISTING_TITAN_ADMIN_TOKEN"
python training/auto_train.py --watch
```

The runner polls every six hours by default. It starts a local training cycle
only after at least 100 unique grounded examples from at least 10 source
domains exist and at least 20 genuinely new examples have arrived since the
last successful cycle. Thresholds can be raised with
`TITAN_AUTO_MIN_EXAMPLES`, `TITAN_AUTO_MIN_DOMAINS`, and
`TITAN_AUTO_MIN_NEW_EXAMPLES`.

The runner performs a read-only compute preflight first. It requires a local
CUDA GPU with at least 8 GiB VRAM, sufficient disk, validated data and the
training packages. If these are unavailable, it skips training; it never
provisions a hosted GPU, enables a paid teacher API, or falls back to paid
compute. It trains a local candidate adapter and runs the held-out evaluator.
A passing adapter is still only a candidate: this runner does not upload,
deploy, or promote weights automatically.

**Important model boundary:** the current training default is Qwen2.5-0.5B,
while Titan's deployed reasoning model is GPT-OSS-20B. A Qwen adapter does not
modify or attach to GPT-OSS. Cloudflare's current Workers AI LoRA inference
support accepts compatible Llama, Gemma or Mistral adapter families; it does
not turn Workers AI into a training service. The current local runner therefore
produces a separate experimental student adapter. Selecting a compatible
Cloudflare LoRA base and adding an approved deployment route is a separate
reviewed change, not an automatic weight swap.

The local runner is intentionally opt-in because it requires a machine to be
online. Starting it once with `--watch` keeps it monitoring; it does not run
when that computer is off. No GitHub Actions workflow is used for recurring
research or local model training.
