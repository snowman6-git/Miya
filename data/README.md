# data/

**한국어** | [English](README.en.md)

| 파일 | 역할 |
|---|---|
| `gen.py` | 합성 학습데이터 생성 → `gen/{train,dev}.jsonl` |
| `build_mc.py` | 바닐라 데이터생성기 출력 → `mcdata/mc.db` (아이템·블럭·몹·레시피·태그·루트) |
| `build_mcx.py` | `mc.db` + worldgen → `mcx.db` (광석 높이·스폰·채굴시간·아이템 가치) |
| `extract_chat.py` | 서버로그 + 봇로그 → `chat_raw.jsonl`(사람 발화), `events_raw.jsonl`(사망·피격 등) |

## gen.py 행 종류

| kind | 내용 | 개수 env (기본) |
|---|---|---|
| turn | 발화 이해: act/type/query/hint + 구간 + 아이템 링크 | `NT` 200000 |
| plan | 방법 선택: planner 후보 + 숨은 참값 시뮬 + QED 경험 노출, 가치 타깃 | `NP` 40000 |
| prio | 위협·상태 → 생존 우선순위 | `NR` 30000 |
| tidy | 인벤 정리 (유지/버리기/보관) | `NTD` 20000 |

`SEED`로 시드를 고정합니다. 실발화 원문(`chat_raw.jsonl`)은 평가 전용이며, 정확히 일치하는 문장은 학습에서 뺍니다.

```bash
.venv/bin/python data/gen.py
```

## 포함하지 않는 것

아래 파일은 저장소에 없습니다.

- Mojang 데이터(`mcdata/`, `mcx.db`): 로컬에서 추출 → [../docs/extract.md](../docs/extract.md)
- 채팅·봇 로그(`srvlog/`, `botlog/`, `chat_raw.jsonl`, `events_raw.jsonl`)
- 생성물(`gen/`)
- QED DB(`qed.db`): 스키마만 공개 → [../qed/schema.sql](../qed/schema.sql)
