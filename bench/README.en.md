# bench/

[한국어](README.md) | **English**

Compares Miya-0.2 with LAYA base (zero-shot). Planner, QED and bot are identical; only the decision model is swapped. Summary: [RESULT.md](RESULT.md) (Korean)

| File | Content |
|---|---|
| `RESULT.md` | Offline + in-game summary |
| `offline.md` | `eval/bench.py` output (real utterances, plan, prio, tidy accuracy, latency) |
| `game.md`, `game_re.md` | `eval/bench_game.py` output (14 scenarios, first run and re-run) |
| `rcon.py` | `rcon.py <port> <cmd…>` sends a command to a bench server (stdlib) |

## In-game setup

Two local Paper servers with the same seed, one bot each.

| | server | rcon | model server | bot web |
|---|---|---|---|---|
| Miya | `bench/b` (:25581) | 25591 | :8767 | :8190 |
| LAYA | `bench/a` (:25582) | 25592 | :8766 | :8191 |

Server folders (`a/`, `b/`, `base/` = shared Paper libraries), logs and `*.db` files are not in the repo. Create both servers with the same `level-seed` in `server.properties`.
