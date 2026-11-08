"""Bounded LoRA self-distillation. Produces a candidate adapter, never a deployed model."""
from __future__ import annotations
import hashlib, ipaddress, json, os, re
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

DATA = Path(os.environ.get("TITAN_TRAIN_DATA", "training/curated.jsonl"))
OUT = Path(os.environ.get("TITAN_ADAPTER_OUT", "artifacts/titan-lora"))
EVAL_DATA = Path(os.environ.get("TITAN_EVAL_DATA", "training/heldout.example.jsonl"))
MAX_ROWS = max(1, min(10000, int(os.environ.get("TITAN_MAX_TRAIN_ROWS", "1000"))))
EPOCHS = max(1, min(3, int(os.environ.get("TITAN_EPOCHS", "1"))))
SEED = max(0, min(2**31 - 1, int(os.environ.get("TITAN_SEED", "42"))))
REQUIRE_SOURCE_GROUNDING = os.environ.get("TITAN_REQUIRE_SOURCE_GROUNDING", "true").lower() not in {"0", "false", "no"}
ALLOW_USER_CONVERSATION_DATA = os.environ.get("TITAN_ALLOW_USER_CONVERSATION_DATA", "false").lower() in {"1", "true", "yes"}
SECRET_PATTERNS = [
    re.compile(r"(?i)api[_ -]?key\s*[:=]\s*\S{12,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{24,}"),
]

def normalize_instruction(value: str) -> str:
    return re.sub(r"\W+", " ", value.lower()).strip()

def normalize_grounding(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Dataset file missing: {path}")
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSONL at {path}:{line_no}: {exc}")
        if not isinstance(row, dict):
            raise SystemExit(f"Expected an object at {path}:{line_no}")
        rows.append(row)
    return rows

def is_valid_source_url(source: str) -> bool:
    try:
        parsed = urlparse(source)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
            return False
        if parsed.port is not None and parsed.port not in {80, 443}:
            return False
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal", ".lan", ".test", ".invalid")):
            return False
        try:
            return ipaddress.ip_address(hostname).is_global
        except ValueError:
            return "." in hostname and not hostname.startswith(".") and not hostname.endswith(".")
    except ValueError:
        return False

def validate_training_rows(rows: list[dict[str, Any]], heldout: list[dict[str, Any]]) -> list[dict[str, Any]]:
    heldout_instructions = {
        normalize_instruction(str(row.get("instruction", "")))
        for row in heldout if str(row.get("instruction", "")).strip()
    }
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    rejected = {"invalid": 0, "heldout_overlap": 0, "duplicate": 0, "secret_like": 0, "ungrounded": 0}
    for row in rows:
        instruction = str(row.get("instruction", "")).strip()
        response = str(row.get("response", "")).strip()
        key = normalize_instruction(instruction)
        if len(instruction) < 12 or len(response) < 30 or len(response) > 6000:
            rejected["invalid"] += 1
            continue
        if key in heldout_instructions:
            rejected["heldout_overlap"] += 1
            continue
        if key in seen:
            rejected["duplicate"] += 1
            continue
        if any(pattern.search(instruction + "\n" + response) for pattern in SECRET_PATTERNS):
            rejected["secret_like"] += 1
            continue
        if REQUIRE_SOURCE_GROUNDING:
            source_type = str(row.get("source_type", "public_source"))
            if source_type == "user_conversation":
                if not ALLOW_USER_CONVERSATION_DATA or row.get("consent") is not True:
                    rejected["ungrounded"] += 1
                    continue
            elif source_type == "public_source":
                source = str(row.get("source_url", "")).strip()
                quote = str(row.get("supporting_quote", "")).strip()
                excerpt = str(row.get("source_excerpt", ""))
                excerpt_hash = str(row.get("source_excerpt_sha256", "")).strip().lower()
                normalized_quote = normalize_grounding(quote)
                normalized_response = normalize_grounding(response)
                normalized_excerpt = normalize_grounding(excerpt)
                excerpt_length = len(excerpt.strip())
                digest_matches = bool(re.fullmatch(r"[a-f0-9]{64}", excerpt_hash)) and hashlib.sha256(excerpt.encode("utf-8")).hexdigest() == excerpt_hash
                if (not is_valid_source_url(source) or len(quote) < 12 or excerpt_length < 200 or excerpt_length > 6500
                        or not digest_matches or normalized_quote not in normalized_excerpt
                        or normalized_quote not in normalized_response):
                    rejected["ungrounded"] += 1
                    continue
            else:
                rejected["ungrounded"] += 1
                continue
        seen.add(key)
        accepted.append({**row, "instruction": instruction, "response": response})
        if len(accepted) >= MAX_ROWS:
            break
    print(json.dumps({"input_rows": len(rows), "accepted_rows": len(accepted), "rejected": rejected}, sort_keys=True))
    if len(accepted) < 20:
        raise SystemExit("Need at least 20 valid, deduplicated, held-out-disjoint examples; refusing to train.")
    return accepted

def choose_lora_targets(model: Any) -> list[str]:
    import torch
    linear_suffixes = {name.rsplit(".", 1)[-1] for name, module in model.named_modules() if isinstance(module, torch.nn.Linear)}
    candidates = [["q_proj", "k_proj", "v_proj", "o_proj"], ["query_key_value"], ["qkv_proj"], ["c_attn"], ["Wqkv"], ["wq", "wk", "wv", "wo"]]
    for group in candidates:
        found = [name for name in group if name in linear_suffixes]
        if found:
            return found
    raise SystemExit("Could not identify common attention projection modules for LoRA.")

def main() -> None:
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
    from trl import SFTConfig, SFTTrainer
    base_model_name = os.environ.get("TITAN_BASE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    if OUT.exists() and (not OUT.is_dir() or any(OUT.iterdir())):
        raise SystemExit(f"Output path is not an empty directory: {OUT}. Choose a fresh candidate path.")
    rows = validate_training_rows(load_jsonl(DATA), load_jsonl(EVAL_DATA))
    set_seed(SEED)
    tokenizer = AutoTokenizer.from_pretrained(base_model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    def format_example(row: dict[str, Any]) -> dict[str, str]:
        messages = [
            {"role": "system", "content": "You are Titan, a reliable AI assistant. Be accurate, helpful, safe, and explicit about uncertainty."},
            {"role": "user", "content": row["instruction"]},
            {"role": "assistant", "content": row["response"]},
        ]
        return {"text": tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)}
    dataset = Dataset.from_list([format_example(row) for row in rows])
    model = AutoModelForCausalLM.from_pretrained(base_model_name)
    targets = choose_lora_targets(model)
    has_cuda = torch.cuda.is_available()
    use_bf16 = bool(has_cuda and torch.cuda.is_bf16_supported())
    use_fp16 = bool(has_cuda and not use_bf16)
    lora = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM", target_modules=targets)
    args = SFTConfig(
        output_dir=str(OUT), num_train_epochs=EPOCHS, per_device_train_batch_size=1,
        gradient_accumulation_steps=8, learning_rate=2e-4, logging_steps=5,
        save_strategy="epoch", save_total_limit=1, report_to="none", max_length=1024,
        dataset_text_field="text", fp16=use_fp16, bf16=use_bf16,
        gradient_checkpointing=has_cuda, seed=SEED, data_seed=SEED,
    )
    trainer = SFTTrainer(model=model, args=args, train_dataset=dataset, peft_config=lora, processing_class=tokenizer)
    trainer.train()
    trainer.save_model(str(OUT))
    tokenizer.save_pretrained(str(OUT))
    manifest = {
        "base_model": base_model_name, "train_data_sha256": sha256_file(DATA),
        "heldout_data_sha256": sha256_file(EVAL_DATA), "rows": len(rows), "epochs": EPOCHS,
        "seed": SEED, "method": "LoRA SFT self-distillation", "target_modules": targets,
        "accelerator": "cuda" if has_cuda else "cpu", "reviewed_by_human": False,
        "source_grounded": REQUIRE_SOURCE_GROUNDING,
        "promotion": "candidate-only; requires held-out capability and safety gate",
    }
    (OUT / "titan_training_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved candidate adapter to {OUT}. Evaluate against the base model before any promotion.")

if __name__ == "__main__":
    main()
