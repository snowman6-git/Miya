# qed/ — Quasi-Evolutionary Diary

[한국어](README.md) | **English**

QED records actions and their outcomes, then injects them as experience into the next decision. The DB (`data/qed.db`) is not published; only the schema is.

| Table | Content |
|---|---|
| `goals` | One GOAL run: request, goal, count, method (via), success, ms, failure reason, model input ctx, variables (tool tier, gear, time) |
| `steps` | Per step of a GOAL: type, target, count, tool, ms, success, failure reason |
| `deaths` | Death: cause, killer, HP, hunger, night, armor, weapon, position, inventory and its value, the GOAL in progress |
| `placed` | Blocks the bot placed (reuses tables, furnaces and chests; tells its chests apart from others') |

`serve.py` creates these tables at startup. `schema.sql` is for reference.

## How experience is injected (`qed_of` in `serve.py`)

1. Collect the last 20 runs of the same goal with the same method path (`via:` tokens).
   - Excluded: user stops or preemptions (`stopped`) and a fixed bot bug (`craft_unsynced`).
   - A death during the run counts as a failure.
2. Append `경험 N회 성공 X% 평균 T초 최근실패 K회(reason)` to the option text. It reads "N runs, X% success, avg T s, K recent failures (reason)".
3. Choose once more without the experience. If the pick differs, mark it `changed`, meaning experience changed the decision.
