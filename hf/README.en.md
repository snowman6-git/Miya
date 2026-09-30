<h1 align="center">
  <img src="miya_icon.webp" width="110" align="middle" alt="Miya icon">&nbsp;Miya-0.3
</h1>

<p align="center">Korean Minecraft AI decision model · 139M encoder · ~18 ms per pass<br><a href="https://github.com/snowman6-git/Miya">GitHub: bot · serving · training code</a> · <a href="https://huggingface.co/snowman6/Miya-0.3">한국어</a></p>

> [!WARNING]
> **Work in progress.** 0.3 is a research snapshot, not a finished agent.
> There is no autonomous mode yet, and unseen-item linking and some survival decisions are weak ([Limitations](#limitations--work-in-progress)).
> Weights, label schema and API may change without compatibility in the next version.

![Miya character sheet](charasheet.webp)

## At a glance

![Miya at a glance](infographic.en.webp)

<details><summary>Korean version</summary>

![Miya 한눈에 보기](infographic.webp)

</details>

## What it does

Miya is the **decision model** of a Minecraft AI built on one rule: the model makes every decision, and the bot only executes.
No regex or if-chains decide anything. Facts such as recipes and ore heights are computed by the planner; the model chooses what to do.

- **Casual Korean**: `철곡 ㄱㄱ` (iron pickaxe, go), `철뚝` (iron helmet), `철셋` (iron set), clipped endings, internet slang
- **Criticism / advice**: `그거론 한참걸리겠는데?` ("that'll take forever"), `그거 맞아?` ("is that right?")
- **Asks when unsure**: if the item link is NULL it asks back, then re-reads the request together with the answer (multi-turn)
- **Method choice**: picks one of the planner's options after reading QED experience
- **Survival priority**: from HP, hunger, threats, night and air, picks fight, flee, eat, hide or resume
- **Human-like fine judgments (0.3)**: ten decisions that used to be bot if/else now come from the model.
  | Judgment | Example |
  |---|---|
  | food | HP 3 → golden apple, otherwise bread |
  | weapon / shield | one zombie → iron sword; skeleton or several → + shield |
  | combat target | zombie + spider → zombie first |
  | hunt target | "사냥해" (go hunt) → cow among armadillo, chicken, cow, horse, sheep |
  | explore direction | sand → picks northeast from per-direction terrain samples and visit counts |
  | failure handling | no target → replan → replan → ask for help |
  | death recovery | value 58, bare-handed, spider nearby → give up |
  | quantity meaning | `조약돌 3개 줘` (give 3 cobble) → 3; `철 원석 버려` (drop raw iron, 4 held) → "how many?" |
  | group target | `나무 버려` (drop wood) → "oak log or acacia log?" |
  | advice → action | `그거론 한참걸리겠는데?` → switch if a faster method exists, else explain and continue |

## Architecture

### System

```
Player chat ─▶ Paper server ─▶ bot (TS·mineflayer) ─HTTP JSON─▶ serving (Python stdlib, :8765)
                                   │                            ├─ Miya model (this repo, decisions)
                                   │                            ├─ planner    (facts: recipes, dig time, method options)
                                   │                            ├─ mcx.db     (game knowledge: ore heights, spawns, value)
                                   └─ results /qed ────────────▶└─ QED DB     (experience)
```

| Component | Does | Does not |
|---|---|---|
| **Miya model** | understand requests, choose methods, survival priority, inventory tidy, 10 fine judgments | pathfinding, block manipulation |
| **planner** | goal + state → up to 6 method options with steps, est. time and risk | choose among options |
| **QED DB** | record actions and results, inject them as experience text into the next decision | block things by rule |
| **bot** | walk, dig, craft, fight; report results | decide |

### Model

**Encoder.** mmBERT, 22 layers, bf16.

- Fine-tuned from the encoder weights of [laya-multilingual](https://huggingface.co/convaiinnovations/laya-multilingual); all heads are new.
- Vocabulary pruned 256,000 → 29,252, parameters 312M → 139M.
- The original tokenizer is used as is; a remap buffer inside the model maps the ids.

**Input.** GLiNER2-style schema input. Questions and options are placed in the input itself, so **one encoding pass produces every output**.

```
[CLS] utterance [SEP] state·QED [SEP] ([MASK]label)×n [SEP] (question: [MASK]option…[SEP])×m
```

The vector at each `[MASK]` becomes that option's score, with a softmax per question.
Because options are input text, heads need no rebuilding when planner options or QED experience sentences change.

**Heads.**

| Head | Output |
|---|---|
| Option scores | act(11) · task_type(39) · query(18) · hint(5) · prio(9) · method (via) · tidy(3) |
| Judgment questions (0.3) | food · weapon · target · hunt · explore · fail · recover · qty · pick · hintact. Options are input text, so no new heads, only new questions |
| Span extraction | target · count · tool · person · coords · place · distance (7 kinds, width ≤ 8) |
| Item link | span ↔ name bank of 1,628 (items + mobs + groups/sets/places). Bi-encoder + ColBERT late interaction handles partial matches like `철뚝`. NULL → ask back |
| Pairing | count ↔ target/tool (`철 3개랑 석탄 5개`, "3 iron and 5 coal") |
| Value | per-method log duration · success probability |

**Labels.** Per-question labels live in `schema.json` (stored in Korean).

| Question | Labels |
|---|---|
| act (11) | run goal, answer question, ask back, stop, resume, yes, no, small talk, abuse, danger warning, criticism/advice |
| prio (9) | continue, melee, flee running, flee by pillaring, dig in and hide, eat, resume paused task, swim up, tidy inventory |
| hint (5) | slow, wrong, short, danger, done_claim |
| tidy (3) | keep, drop, store in chest |

### Task types (TASK_TYPE)

Every work block gets its own type (no shared types). The model classifies a request into one of them and the bot runs the matching executor.

![Miya task types](task_type.webp)

### Planner (facts) vs model (choice)

The planner builds method options from these facts:

- recipe tree
- dig time (per tool tier)
- ore generation heights
- fuel efficiency
- crafting tables and furnaces already placed

For "철곡 만들어" (make an iron pickaxe), options look like `[via wood → stone pickaxe]`, `[via stone pickaxe, reuse furnace]`, `[logs as fuel]`.

The training data simulates **hidden truths** that differ from the estimates (no resource, slow, blocked). So the model learns not to trust estimates alone, and to read the QED experience text given with them.

## QED — Quasi-Evolutionary Diary

Actions and results accumulate in a DB and go into the next decision **as experience text**. Nothing is blocked by rule; the model reads it and decides.

**Record.** The bot sends each finished GOAL to `/qed`.

| Table | Contents |
|---|---|
| `goals` | request, goal, count, method (via), success, duration ms, failure reason, variables (tools, gear, time held) |
| `steps` | per step: type · target · cnt · tool · ms · success · failure reason |
| `deaths` | cause, killer, HP/hunger/night/armor/weapon, position, inventory and its value, GOAL in progress |
| `placed` | blocks the bot placed (reuse tables, furnaces, chests; tell its chests from others') |

**Injection.** The last 20 runs of the same goal with the same method path are summarized and appended to the option text (the text itself is Korean; below: est. 301 s, risk 40%, 5 runs, 80% success, avg 170 s, 1 recent failure):

```
direct | 원정 참나무 원목 1 → 벌목 참나무 원목 2 → 제작 참나무 판자 8 → … | 예상 301초 위험 40% | 경험 5회 성공 80% 평균 170초 최근실패 1회(no_ore)
```

![QED decision evidence example](qed_example.webp)

The web UI's decision panel in a real run. For `철곡 만들어` (make an iron pickaxe) each of the 7 planner options carries choice probability, estimate, predicted time, risk and QED experience (14 runs, 29% success, recent death); the model picked reusing the already placed crafting table and furnace at 83%.

**Attribution.** The choice is made once more without experience. If the result differs it is marked `changed` (experience changed the decision).

**Deaths and value.** Recent death causes go into the survival context. Item value (base value + acquisition difficulty) drives recovery: lose one dirt block and it doesn't go back; lose a full diamond set and it does.

**Loop guards.** The previous model looped "low HP → hunt → no animals → low HP" and flooded requests. Now:

- step retry ≤ 3, replan ≤ 5
- survival decisions are requested only when state changes
- repeated failures show up in QED, so the same method isn't repeated

## Evaluation

### Miya-0.3 vs 0.21

Same eval set (537 real utterances, 7.4k dev).

| Metric | 0.21 | 0.3 |
|---|---|---|
| intent (act) | 95.0% | **95.7%** |
| task type | 92.3% | **95.3%** |
| target item | 84.6% | **91.7%** |
| count | 89.3% | **98.2%** |
| survival priority (dev prio) | 74.6% | **97.0%** |
| method choice (dev plan) | 75.6% | **76.5%** |
| 10 fine judgments (dev) | 5–60% (untrained) | **96–100%** |
| slang holdout | 11/12 | **12/12** |
| latency p50 / p95 | 19.0 / 22.5 ms | **18.8 / 21.9 ms** |

In-game (Paper 26.1.2): all 10 fine judgments plus the night flee↔resume loop passed (11/11). A zombie now dies in ~2 s (0.21 never killed it because of an attack-cooldown reset bug).

### Miya-0.2 vs LAYA base

Compared with LAYA base, keeping planner, QED and bot identical and **swapping only the decisions**.

- Real utterances: 488 raw server chat lines, excluded from training
- dev: 5.8k (as of 0.2)
- In-game: 14 scenarios run in parallel on two local servers with the same seed

| | Miya-0.2 | LAYA base (zero-shot) |
|---|---|---|
| Real-utterance intent (act) | **94.5%** | 11.0% |
| Task type (type) | **89.7%** | 40.5% |
| Target item (target) | **87.3%** | 6.2% |
| Method choice (plan) | **73.6%** | 27.4% |
| Survival priority (prio) | **86.6%** | 11.5% |
| In-game, 14 scenarios | **13/14** | 0/14 |
| Model latency p50 / p95 | 17.8 / 19.7 ms | — |

## Examples (real serving output)

Real responses from `model/serve.py` (:8765). Probabilities and ms rounded, some fields omitted.

```bash
S='"state":{"hp":20,"food":20,"night":false,"inv":{"oak_log":4},"task":null}'
curl -s localhost:8765/turn -d "{\"utt\":\"철곡 만들어\",$S}"
```

| utterance | act | type | target · count | hint | ms |
|---|---|---|---|---|---|
| `철곡 만들어` (make iron pick) | run goal 1.00 | craft | `철곡` → iron_pickaxe (철 곡괭이) | short | 25 |
| `나무 5개 캐오셈` (go get 5 logs) | run goal 1.00 | log | `나무` → grp:log · `5개` → 5 | short | 21 |
| `철뚝 ㄱㄱ` (iron helmet, go) | run goal 1.00 | craft | `철뚝` → iron_helmet (철 투구) | slow | 22 |
| `그거론 한참걸리겠는데?` ("that'll take forever") | criticism/advice 1.00 | — | — | slow | 25 |

```bash
curl -s localhost:8765/plan -d '{"goal":"iron_pickaxe","cnt":1,"inv":{"oak_log":4},"placed":{},"near":{},"hp":20,"night":false,"armor":0}'
```
```json
{"detail": {"pick_ko": "나무 곡괭이 경유, 돌 곡괭이 경유", "qed_changed": false,
  "opts": [{"ko": "나무 곡괭이 경유, 돌 곡괭이 경유", "p": 0.58, "est_s": 321, "risk": 15,
             "qed": {"n": 20, "ok": 0.6, "avg_ms": 273603},
             "steps": ["제작 참나무 판자 12", "제작 제작대 1", "설치 제작대 1", "제작 막대기 4", "제작 나무 곡괭이 1",
                       "원정 돌 1", "채광 돌 11(나무 곡괭이)", "…", "화로 철 주괴 3", "제작 철 곡괭이 1"]},
           {"ko": "나무 곡괭이 경유, 돌 곡괭이 경유, 연료 석탄", "p": 0.25, "est_s": 446, "risk": 25}, …]}}
```

```bash
curl -s localhost:8765/prio -d '{"ctx":"체력 5/20 배고픔 18/20 | 밤 | 위협: 좀비 4칸"}'
# {"label":"달려서 도망","p":0.48,"ms":20.5}
```

## Usage

```bash
git clone https://github.com/snowman6-git/Miya miya && cd miya
hf download snowman6/Miya-0.3 --local-dir ckpt/miya-0.3
# game data (mc.db, mcx.db) is not included → extract locally with docs/extract.en.md
.venv/bin/python model/serve.py   # :8765 (SERVE_HOST=0.0.0.0 for bots on other machines)
curl -s localhost:8765/turn -d '{"utt":"철곡 만들어","state":{"hp":20,"food":20,"night":false,"inv":{},"task":null}}'
```

To run the bot too: `./run.sh host:port`. The server must be in **offline mode** (`online-mode=false`); for an online server use `MC_AUTH=microsoft ./run.sh host:port` to sign in with a Microsoft account (on first run, enter the code from bot.log at microsoft.com/link; the token is cached in `bot/.auth/`). All options: [GitHub README](https://github.com/snowman6-git/Miya/blob/main/README.en.md#server-and-login).

| API | Input → output |
|---|---|
| `/turn` | utterance + state → act, type, query, hint, spans, target item |
| `/plan` | goal + inventory/placed/surroundings → options, choice, probabilities, steps (QED injected) |
| `/prio` | state ctx → survival priority |
| `/qed` · `/death` | record results and deaths |
| `/tidy` · `/value` · `/placed` | inventory tidy, item value, placed blocks |
| `/food` · `/weapon` · `/target` | food, weapon/shield, combat target (0.3) |
| `/hunt` · `/explore` | hunt target/expedition, explore direction (0.3) |
| `/fail` · `/recover` · `/hintact` | failure handling, death recovery, advice → action (0.3) |

Three files:

- `model.safetensors`: weights
- `schema.json`: labels
- `config.json`: metadata (the file HF counts downloads by)

Model code (`model/miya.py`) is in the [GitHub repo](https://github.com/snowman6-git/Miya).

## Limitations · work in progress

> Still **unfinished**. These are known issues to be addressed in the next versions.

- **No autonomous mode**: commands like "자급자족해" (be self-sufficient) are classified but not executed. A survive-and-progress loop is planned.
- **Ask over-calibration**: over-asks for help when experience shows a middling success rate (not re-measured for 0.3).
- **Unseen item linking**: items missing from training goals (`선인장` cactus, `얼음` ice) are mislinked or asked back.
- **Survival weak spots**: still flees from mobs faster than the bot (spiders). Method choice (plan) plateaus at 76%.
- **Quantity phrasing**: `반만` (half) is not read as half yet; the model asks back.
- **Answer re-reading**: combining an answer with the original request is still done by the bot (to move into the model with multi-turn data).
- **Data bias**: most training data (370k) is synthetic, with little real chat. Korean only.
- **Fixed environment**: Minecraft 26.1.2 recipes; tasks mineflayer can't do (enchanting, trading, ranged, etc.) are not executed yet.
- **No compatibility**: weights and schema are not guaranteed compatible across versions.

## License

Apache-2.0 + [Miya Adopt Licence](https://huggingface.co/snowman6/Miya-0.3/blob/main/LICENSE-MIYA.md) (a non-binding request clause).

- Base: laya-multilingual (Apache-2.0) ← mmBERT-base (MIT)
- No Minecraft game data is included; generate it locally with `docs/extract.en.md` from the repo.
- Minecraft is a trademark of Mojang Studios; this project is not affiliated with Mojang.
