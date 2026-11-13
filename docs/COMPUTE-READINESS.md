# Titan compute readiness — 2026-11-08

## Current connected capacity (read-only inspection)

- ATL Sandbox account is on the Free plan with USD 0.00 available compute credit. Its account-level GPU catalog lists NVIDIA T4 16 GB, A10G 24 GB, L4 24 GB, RTX PRO 4500 32 GB and RTX PRO 6000 96 GB, but GPU entitlement is disabled for this account. Four existing sandboxes are stopped.
- Hugging Face account `harryjees` is authenticated on the Free plan. The Jobs API is accessible, but there are no active jobs. A Jobs API call can create billable compute; Titan must not submit a job until the user explicitly approves a specific flavor, maximum runtime and estimated cost.
- Cloudflare is connected. The deployed titan-ai-core Worker currently has only its D1 binding and no Cron Trigger; the proposed semantic-learning branch adds Workers AI and a durable Workflow. Workers AI is inference capacity, not a LoRA fine-tuning GPU.
- TinyFish wallet and Firecrawl credits are reserved for their intended research tasks; neither is a model-training compute balance.

No GPU, CPU job, training run, model download, billing change, secret update, database migration or deployment was started during this inspection.

## Safe local preflight

From the repository root:

```bash
python -m training.compute_preflight
```

The command is read-only. It checks Python training dependencies, CUDA visibility and VRAM, system RAM, free disk, curated JSONL row count and held-out JSONL presence. It never downloads weights or starts training.

The strict dataset checks also require at least 20 training objects with non-empty instruction/response fields, and a held-out suite with unique IDs, supported categories, explicit expected behavior, non-vacuous scoring terms and minimum coverage of 4 capability, 3 safe-cybersecurity and 4 safety cases. This is a structural gate; the LoRA validator still performs the deeper source-provenance, digest, secret-pattern and held-out-overlap checks.

CPU fallback is deliberately opt-in:

```bash
python -m training.compute_preflight --allow-cpu
```

CPU mode requires at least 16 GiB system RAM. GPU mode requires CUDA and at least 8 GiB VRAM. Both modes require all training dependencies, at least 20 curated examples, a valid held-out suite and at least 10 GiB free disk.

## Training launch remains a separate human action

Only after preflight reports `"ready": true`, the user has reviewed the dataset and compute cost, and the selected machine has an approved resource budget should training be launched:

```bash
python training/train_lora.py
python training/evaluate_adapter.py
```

The trainer writes a candidate adapter only. The held-out evaluation and human review remain mandatory. No workflow may auto-merge, deploy, or promote adapter weights.

## Remote compute connection required

To use ATL GPU compute, the account owner must explicitly upgrade/enable a GPU-capable plan or add compute credit in the ATL Sandbox account dashboard. The current account reports USD 0.00 and GPU disabled.

To use Hugging Face Jobs, the account owner must first review the Jobs billing page and confirm a maximum spend/runtime budget. The connected token already has Jobs API scope, but API access is not proof of free compute. No job has been submitted.

If neither provider can be funded, use an existing local computer with a compatible NVIDIA GPU, or the explicit CPU fallback on a sufficiently provisioned machine. Do not silently switch to hosted paid inference or training.


## GPT-OSS inference budget for the semantic-learning branch

The proposed runtime uses OpenAI GPT-OSS-20B for reasoning and BGE-M3 for embeddings through the Cloudflare Workers AI binding. Cloudflare's current published free allocation is 10,000 neurons per UTC day. Titan's application-side reservation ceiling is 9,000 neurons/day, with up to 3,500 neurons per research run and 2,000 for chat; no paid fallback is configured. The reservation is deliberately conservative and may stop early. Check actual usage in the Cloudflare dashboard.

The branch does not change the live Worker or apply D1 migration 0009. Deployment requires applying the migration and reviewing the new AI and Workflow bindings. No paid plan, credit purchase, secret, GPU job, or model training is started by this branch.
