# data/

[한국어](README.md) | **English**

| File | Role |
|---|---|
| `gen.py` | Synthetic training data → `gen/{train,dev}.jsonl` |
| `build_mc.py` | Vanilla data generator output → `mcdata/mc.db` (items, blocks, mobs, recipes, tags, loot) |
| `build_mcx.py` | `mc.db` + worldgen → `mcx.db` (ore heights, spawns, mining times, item values) |
| `extract_chat.py` | Server log + bot log → `chat_raw.jsonl` (human utterances), `events_raw.jsonl` (deaths, damage, …) |

## gen.py row kinds

| kind | content | count env (default) |
|---|---|---|
| turn | utterance understanding: act/type/query/hint + spans + item links | `NT` 200000 |
| plan | method choice: planner candidates + simulated hidden outcomes + QED text, value targets | `NP` 40000 |
| prio | threat/state → survival priority | `NR` 30000 |
| tidy | inventory tidy (keep / drop / store) | `NTD` 20000 |

`SEED` fixes the random seed. Real utterances (`chat_raw.jsonl`) are reserved for evaluation, and exact matches are excluded from training.

```bash
.venv/bin/python data/gen.py
```

## Not included

These files are not in the repo:

- Mojang data (`mcdata/`, `mcx.db`): extract locally → [../docs/extract.en.md](../docs/extract.en.md)
- Chat and bot logs (`srvlog/`, `botlog/`, `chat_raw.jsonl`, `events_raw.jsonl`)
- Generated data (`gen/`)
- QED DB (`qed.db`): only the schema is published → [../qed/schema.sql](../qed/schema.sql)
