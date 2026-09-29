# model/

[한국어](README.md) | **English**

The model makes every decision. The planner and the DBs only compute facts.

| File | Role |
|---|---|
| `miya.py` | Model: mmBERT encoder + GLiNER2-style schema-input heads (option scoring, span extraction, item linking (bi-encoder + ColBERT), value). Vocab pruning is done with a remap buffer |
| `catalog.py` | Item, mob and group list (link bank) plus the slang and abbreviation generator for training data |
| `planner.py` | goal + state → candidate methods (via), step lists, estimated time and risk. Uses facts only (recipes, mining times) |
| `serve.py` | HTTP server (stdlib only). The API is listed in the module docstring |
| `train.py` | Trains on `data/gen/{train,dev}.jsonl` → `ckpt/miya-0.2` |
| `eval.py` | Evaluates real utterances (`eval/real.jsonl`), the slang holdout, dev and latency → `eval/last_errors.txt` |

## Input format

```
[CLS] utterance [SEP] state·QED [SEP] ([MASK]label)×n [SEP] (question: [MASK]option…[SEP])×m
```

Softmax is taken per question. "Ask back" is trained as just another option.

## Run

```bash
.venv/bin/python model/serve.py                      # :8765
.venv/bin/python model/train.py                      # train
.venv/bin/python model/eval.py                       # evaluate
```

| env | default | purpose |
|---|---|---|
| `CK` | `ckpt/miya-0.2` | checkpoint for serving and eval |
| `QED` | `data/qed.db` | experience DB |
| `PORT` | 8765 | server port |
| `SNAP` | hf_cache snapshot | base tokenizer/encoder path (downloaded from HF if missing) |
| `OUT` | `ckpt/miya-0.2` | training output |
| `EP` / `BS` / `LR` | 2 / 32 / 3e-5 | training hyperparameters |
| `PRUNE` | 1 | vocab pruning |

Requires `mcdata/mc.db` and `data/mcx.db` → [../docs/extract.en.md](../docs/extract.en.md)
