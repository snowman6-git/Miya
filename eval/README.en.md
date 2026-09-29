# eval/

[한국어](README.md) | **English**

| File | Role |
|---|---|
| `real.jsonl` | Real-utterance eval set (server chat + labels, excluded from training) |
| `real_labels.txt` | Label source |
| `bench.py` | Offline A/B: sends the same set to two servers over HTTP, then writes an accuracy and latency table |
| `bench_game.py` | In-game A/B: two local Paper servers with the same seed, Miya and LAYA bots run the same scenarios in parallel |
| `laya_serve.py` | LAYA base (zero-shot) server for comparison. Same API as `serve.py`; only the decisions are swapped |

The model's own evaluation lives in `model/eval.py`.

```bash
PORT=8767 .venv/bin/python model/serve.py &          # Miya
.venv/bin/python eval/laya_serve.py &                # LAYA :8766
.venv/bin/python eval/bench.py 8767 8766 > bench/offline.md
.venv/bin/python eval/bench_game.py > bench/game.md  # start servers and bots first (../bench/README.en.md)
```
