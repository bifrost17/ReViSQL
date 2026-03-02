# ReViSQL: Achieving Human-Level Text-to-SQL

**VLDB 2026 Artifact**

> ReViSQL is a streamlined framework that achieves human-level accuracy on BIRD for the first time. Instead of complex AI agents, ReViSQL leverages reinforcement learning with verifiable rewards (RLVR) on BIRD-Verified — a dataset of 2,462 expert-verified Text-to-SQL instances — and inference-time scaling via execution-based reconciliation and majority voting.


## Framework Overview

ReViSQL achieves human parity through three procedures:

1. **BIRD-Verified** — Expert-curated training data. We corrected annotation errors across 52.1% of SQL queries, 26.2% of questions, and 18.2% of external knowledge contexts in 2,462 BIRD Train instances.

2. **RLVR Training** — Fine-tuning with CISPO, a stable RLVR algorithm. The model generates multiple SQL rollouts per question; rollouts are rewarded based on execution correctness against the verified gold SQL.

3. **Inference-time Scaling with Reconciliation** — At inference, the fine-tuned model generates *N* candidate queries, which are grouped by execution result. A pre-RLVR base model (with broader linguistic knowledge) filters groups against the explicit question constraints. The surviving groups are resolved by majority voting.


## Repository Structure

```
ReViSQL/
├── data/                          # Datasets (tracked in git)
│   ├── bird-verified-train.json   # BIRD-Verified training split (85%, ~2088 instances)
│   ├── bird-verified-val.json     # BIRD-Verified validation split (15%, ~374 instances)
│   ├── bird-verified-train.parquet        # Training split in parquet (output of curate_final_data.py)
│   ├── bird-verified-train-{125,250,500,1000}.json  # Subsets for data-scaling ablation (Fig. 8)
│   ├── arcwise_plat_full.json     # Arcwise-Plat-Full eval set (all errors corrected)
│   ├── arcwise_plat_sql.json      # Arcwise-Plat-SQL eval set (SQL-only corrections)
│   ├── val_test.parquet           # Combined val+eval set in parquet (output of curate_final_data.py)
│   ├── bird-plat-2.5k-v1.json    # Raw BIRD-Platinum 2.5k training candidates (pre-verification)
│   ├── bird_eval.parquet          # Original BIRD mini-Dev evaluation set
│   ├── spider2sqlite_eval.parquet # Spider 2-SQLite evaluation set (135 questions)
│   ├── spider_2_snow_eval.parquet # Spider 2-Snow evaluation set (547 questions)
│   └── ddls/                      # Database schema DDL files (one per db_id)
│
├── scripts/
│   ├── train.py                   # RLVR fine-tuning with CISPO (via Tinker)
│   └── infer.py                   # Inference + evaluation with RLTestSetEvaluator
│
├── reconciliation/                # Inference-time reconciliation (Algorithm 1, §5.2)
│   ├── reconciliation.py          # Core Decide() function: LLM-based constraint filtering
│   ├── prompt.py                  # Reconciliation prompt templates
│   ├── run_reconciliation.py      # Batch reconciliation on graded results
│   └── run_reconciliation_detailed.py  # Detailed per-query reconciliation logging
│
├── data_scripts/                  # Data preparation scripts
│   ├── curate_final_data.py       # Main curation: produces bird-verified-train.parquet + val_test.parquet
│   ├── curate_RL_dataset.py       # Earlier curation pipeline (intermediate artifacts)
│   ├── curate_curriculum_data.py  # Curriculum learning stage splits (stage_1–4.parquet)
│   ├── construct_db_schema.py     # DDL generation for BIRD databases
│   ├── construct_spider2sqlite_db_schema.py  # DDL generation for Spider 2-SQLite databases
│   └── generate_spider2sqlite_tables.py      # tables.json generation for Spider 2-SQLite
│
├── tinker_cookbook/               # Bundled training framework (RLVR engine, SQL env, evaluators)
├── pyproject.toml                 # Project dependencies
└── .gitignore
```

---

## Setup

**Requirements:** Python 3.11+.

```bash
# Install ReViSQL and dependencies
uv sync

# Copy .env and fill in API keys (Together AI for inference, W&B for logging)
cp .env.example .env
```

**Required environment variables** (in `.env`):
```
TOGETHER_API_KEY=...      # For reconciliation LLM calls (Qwen3-235B via Together AI)
GROQ_API_KEY=...          # Optional: alternative provider for reconciliation
WANDB_API_KEY=...         # For training/eval logging
```

**Database files:** Download the BIRD mini-Dev databases and Spider 2-SQLite databases and note their paths. These are passed at runtime via `--db_path`.

---

## BIRD-Verified Dataset

BIRD-Verified is available in `data/`. The key files:

| File | Description |
|---|---|
| `data/bird-verified-train.json` | 2,088 training instances (85% split) |
| `data/bird-verified-val.json` | 374 validation instances (15% split) |
| `data/arcwise_plat_sql.json` | Arcwise-Plat-SQL evaluation set (500 questions, SQL corrected) |
| `data/arcwise_plat_full.json` | Arcwise-Plat-Full evaluation set (500 questions, fully corrected) |

To regenerate the parquet files used by the training scripts:
```bash
# Run from the repo root
uv run data_scripts/curate_final_data.py
# Outputs: data/bird-verified-train.parquet, data/val_test.parquet
```

---

## Training

Training uses RLVR with the CISPO algorithm via the bundled Tinker framework. The training script accepts CLI arguments using the `chz` configuration system.

**ReViSQL-30B-A3B (low-cost model):**
```bash
uv run scripts/train.py \
    model_name=Qwen/Qwen3-30B-A3B \
    train_data_path=data/bird-verified-train.parquet \
    test_data_path=data/val_test.parquet \
    db_path=/path/to/bird/databases \
    loss_fn=cispo \
    group_size=16 \
    batch_size=64 \
    learning_rate=5e-5 \
    lora_rank=32 \
    max_turns=5 \
    max_output_tokens_per_turn=3000 \
    wandb_project=revisql \
    log_path=models/revisql-30b
```

**ReViSQL-235B-A22B (high-accuracy model):**
```bash
uv run scripts/train.py \
    model_name=Qwen/Qwen3-235B-A22B \
    train_data_path=data/bird-verified-train.parquet \
    test_data_path=data/val_test.parquet \
    db_path=/path/to/bird/databases \
    loss_fn=cispo \
    group_size=16 \
    batch_size=64 \
    learning_rate=5e-5 \
    lora_rank=32 \
    max_turns=5 \
    wandb_project=revisql \
    log_path=models/revisql-235b
```

Key hyperparameters (matching §5.1):

| Parameter | Value |
|---|---|
| LoRA rank | 32 |
| Batch size | 64 |
| Group size | 16 |
| Learning rate | 5 × 10⁻⁵ |
| Max turns | 5 |
| Max output tokens/turn | 3,000 |
| Train/val split | 85:15 |
| Algorithm | CISPO |

The training checkpoint with the highest validation accuracy on `data/val_test.parquet` (Arcwise-Plat-Full + Arcwise-Plat-SQL split) is selected for inference, as described in §6.5 (Table 6).

---

## Inference

The inference script runs greedy decoding and/or temperature sampling to generate *N* SQL candidates per question, then passes them through reconciliation and majority voting (Algorithm 1, §5.2).

**Low-budget setting (5 candidates, greedy + 4 temperatures):**
```bash
uv run scripts/infer.py \
    model_name=Qwen/Qwen3-30B-A3B \
    sampler_path=models/revisql-30b/best_checkpoint \
    data_path=data \
    test_data=val_test.parquet \
    db_path=/path/to/bird/databases \
    output_path=outputs/revisql-30b-low \
    run_name=revisql-30b-low \
    temperature=0.7 \
    repeat=5
```

**High-budget setting (129 candidates):**
```bash
uv run scripts/infer.py \
    model_name=Qwen/Qwen3-235B-A22B \
    sampler_path=models/revisql-235b/best_checkpoint \
    data_path=data \
    test_data=val_test.parquet \
    db_path=/path/to/bird/databases \
    output_path=outputs/revisql-235b-high \
    run_name=revisql-235b-high \
    temperature=1.0 \
    repeat=129
```

Inference-time reconciliation (the `Decide()` step in Algorithm 1) is performed by `reconciliation/reconciliation.py` using a pre-RLVR base model (Qwen3-235B via Together AI). Set `TOGETHER_API_KEY` in your `.env` before running.

---

## Reconciliation Module

The `reconciliation/` module implements the inference-time constraint filtering described in §5.2. It uses an LLM to judge whether a set of SQL candidates correctly covers the constraints in the question and external knowledge hint.

**Standalone batch reconciliation** (for post-hoc analysis on graded results):
```bash
cd reconciliation
uv run run_reconciliation.py \
    --graded_result_path ../graded_results/my_run \
    --output_path decisions.jsonl \
    --data_file ../data/arcwise_plat_sql.json \
    --model_name Qwen/Qwen3-235B-A22B-Instruct-2507-tput
```

The core function is `determine_one_generation_defensive()` in `reconciliation/reconciliation.py`, which corresponds to `Decide(M, x, G[j])` in Algorithm 1.

---

## Reproducing Paper Results

### Table 4 — BIRD benchmarks (Arcwise-Plat-SQL, Arcwise-Plat-Full)

1. Fine-tune on `data/bird-verified-train.parquet` using the training commands above.
2. Select the checkpoint with the highest validation accuracy on `data/val_test.parquet`.
3. Run inference on `arcwise_plat_sql.json` and `arcwise_plat_full.json` test splits within `val_test.parquet`.

### Table 4 — Spider 2-SQLite

Run inference on `data/spider2sqlite_eval.parquet` with `sql_engine=SQLite`.

### Table 5 — Spider 2-Snow

Run inference on `data/spider_2_snow_eval.parquet` with `sql_engine=Snowflake` (requires Snowflake credentials in `.env`).

### Figure 8 — Data scaling ablation

Train separate models using the subsets:
```
data/bird-verified-train-125.json
data/bird-verified-train-250.json
data/bird-verified-train-500.json
data/bird-verified-train-1000.json
data/bird-verified-train.json   # full ~2088 instances
```
