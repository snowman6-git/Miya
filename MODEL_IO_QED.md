# Miya 출력 구조 · QED 조회

## 1. 흐름

```
플레이어 채팅 ─▶ 봇 ─POST JSON─▶ serve.py ─▶ 모델(인코더) ─▶ 보기 선택/구간/연결
                  ▲                    │
                  └──── JSON 결과 ◀────┘  봇은 실행만, 대답은 템플릿(replies.json)
```

- 모델은 문장을 생성하지 않음. 모든 판단 = **보기 중 1개 선택 + 확률**
- 서버: `model/serve.py` (stdlib http, 기본 포트 8765)

## 2. 엔드포인트

| 경로 | 입력 | 출력 | 모델 사용 |
|---|---|---|---|
| `/turn` | utt, ctx, hist? | act·type·query·hint + spans + goals | O |
| `/plan` | goal, cnt, inv, placed, near, hp, night | 방법 후보 중 선택 + steps | O (+QED) |
| `/prio` | ctx | 우선순위 라벨 | O |
| `/tidy` | inv, goal?, free, sit | 아이템별 보관/버림 | O |
| `/food` | 체력·배고픔·음식 보기 | 먹을 음식 | O |
| `/weapon` | 위협·보유 무기·방패 | 무기(+방패) | O |
| `/target` | 위협 목록·방어·무기 | 먼저 칠 대상 | O |
| `/hunt` | 요청·주변 동물 | 사냥 대상 / 원정 | O |
| `/explore` | 목표·방향별 지형 표본·방문수 | 탐색 방향 | O |
| `/fail` | 실패 사유·시도·재계획·연속 | 재시도/재계획/도움/포기 | O |
| `/recover` | 사망 아이템 가치·거리·소멸·위험·장비 | 회수/포기 | O |
| `/hintact` | 조언·현재 방법·대안 | 바꾸기/설명 후 계속 | O |
| `/turn` qty·pick | 수량 표현 / 묶음 대상+보유 | 수량 의미 / 실물·되묻기 | O |
| `/qed` | GOAL 실행 결과 | DB id | 기록 |
| `/death` | 사망 정보 | 인벤 가치, 상위 아이템 | 기록 |
| `/value` | inv | 아이템 가치 | DB |
| `/lesson` | - | 최근 1시간 최다 사망원인 | DB |
| `/placed` | add/del | 설치물 목록 | DB |
| `/ko` | ids | 아이템 한글명 | 사전 |

### `/turn` 발화 해석
```json
{"act":"목표 실행","act_p":0.99,"type":"craft","type_p":1.0,"query":"recipe","hint":"short",
 "spans":[{"text":"철뚝","label":"대상","item":"iron_helmet","ko":"철 투구","score":1.0},
          {"text":"두개","label":"개수","count":2}],
 "goals":[{"item":"iron_helmet","ko":"철 투구","count":2}]}
```
- `act`: 발화 종류(목표/질문/되묻기/멈춤/…), `*_p`: 확률 → 낮으면 되묻기 근거
- `type`/`query`/`hint`: act 에 따라 의미 있는 하위 문항
- `spans`: 문장 조각 → 라벨(대상/개수/장소/도구) → 아이템 ID 연결

### `/prio` 우선순위
```json
{"label":"먹기","p":0.51}
```
보기 9개: 계속 진행 / 근접 전투 / 달려서 도망 / 블럭 쌓아 도망 / 굴 파고 숨기 / 먹기 / 멈춘 작업 재개 / 물 위로 올라가기 / 인벤 정리

### `/plan` 방법 선택 (GOAL → TASK 목록)
1. `planner.py` 가 레시피·인벤·설치물·주변으로 **방법 후보(최대 6) + ask(도움요청)** 생성 (사실 계산)
2. 후보마다 QED 경험 요약을 텍스트로 붙임
3. 모델이 후보 중 1개 선택

모델이 보는 보기 텍스트:
```
direct | 원정 참나무 원목 1 → 벌목 참나무 원목 2 → 제작 참나무 판자 8 → … | 예상 301초 위험 40% | 경험 20회 성공 20% 평균 65초
fuel:coal | … | 예상 427초 위험 50% | 경험 20회 성공 20% 평균 65초
ask | 플레이어에게 도움 요청하고 대기 | 예상 300초 위험 0%
```
출력 주요 필드:
```json
{"pick":1,"p":[0.44,…],"via":"fuel:coal","via_ko":"연료 석탄",
 "steps":[{"type":"expedition","target":"oak_log","cnt":1},{"type":"log",…},{"type":"craft",…}],
 "val":[[204,0.30],…],
 "why":[{"k":"fuel_exp","ko":"석탄"},{"k":"qed","ko":"바로 제작","n":20,"ok":20}],
 "qed":{"changed":false,"base":"direct"}}
```
- `via`: 방법 키. `direct`=바로, `via:X`=X 경유(도구 업그레이드), `reuse:X`=설치물 재사용, `fuel:X`=연료
- `steps`: TASK 목록 → 봇이 순서대로 실행 (TASK_NOW = 현재 step, TASK_GOAL = goal)
- `val`: 가치헤드 예측 [예상 초, 성공확률]
- `why`: 대답 템플릿용 사유(설치물 재사용·연료·경험)
- `qed.changed`: 경험 빼고 다시 골랐을 때와 다르면 true = **경험이 판단을 바꿈**

## 3. QED DB (`data/qed.db`, SQLite)

| 테이블 | 내용 |
|---|---|
| goals | 요청, goal, cnt, via, ok, ms, fail, ctx, vars(도구 티어·장비 등 변수) |
| steps | goal_id, 순번, type, target, cnt, tool, ms, ok, fail |
| deaths | cause, killer, hp, food, night, armor, weapon, pos, inv, inv_value, vars |
| placed | 내가 설치한 블럭 kind, x, y, z |

현재(2026-09-30): goals 218 / steps 658 / deaths 32, goal 종류 24

### 기록 (`/qed`)
GOAL 종료시 봇이 전송 → goals 1행 + steps n행

### 조회 (`qed_of(goal, via)`, `/plan` 에서 자동)
```sql
select g.ok, g.ms, (사망이면 'death' else g.fail), g.via
from goals g left join deaths d on d.goal_id = g.id
where g.goal = ?
  and not (fail='stopped' and 사망 아님)   -- 유저 멈춤은 성패 아님
  and fail != 'craft_unsynced'            -- 봇 버그 기록 제외
order by g.id desc limit 60
```
→ 같은 경로(`core(via)`)만 최근 20건 → 요약
```json
{"n":20,"ok":0.2,"avg_ms":65604,"recent_fail":3,"fail":"death"}
```
- `avg_ms`: 성공분만 평균
- `recent_fail`: 최근 연속 실패 수
- 이 요약이 보기 텍스트 `경험 20회 성공 20% 평균 65초` 로 모델 입력에 들어감

### 그 외 활용
- `/value`: 아이템 기본가치 + (성공 평균 소요 분당 +1) → 사망시 회수 판단
- `/lesson`: 최근 1시간 최다 사망원인 → prio ctx `최근 사망원인: 익사`

## 4. 확인된 문제

- `core(via)` 가 `fuel:`·`reuse:` 를 빼고 묶음 → direct / fuel:coal / fuel:coal,fuel:lava 가 **같은 경험 요약**을 받음. 연료 선택은 경험으로 구분 불가
- 경험 조회는 goal 단위뿐. vars(조건) 는 기록만 되고 조회에 미사용 → "돌곡괭이 있을 때 vs 없을 때" 구분 X

## 5. steps 실행 방식 (`bot/src/main.ts` runGoal)

- steps 는 봇이 **순서대로 실제 실행**하는 TASK 목록 (API 표시용 아님)
- 목록 생성 = `planner.py`(레시피 계산), **어떤 목록으로 갈지 선택 = 모델**
- 흐름
  1. `/plan` → steps 받음 → step 1부터 `exec` (TASK_NOW = i/전체)
  2. 일시 실패(타임아웃·동기화·stuck 등)는 같은 step 최대 3회 재시도
  3. 실패 확정 → 중단 → `/qed` 기록 → **재계획**(`/plan` 다시, 최근 실패가 경험으로 반영) 최대 5회 → 포기
  4. 전부 성공 → `/qed` 기록 → 완료 대답
  5. 새 명령 오면 선점(stopped), prio 판단으로 중단·재개
- 한계: step 사이에 상태 재확인 없음. 중간에 누가 석탄 빼가도 해당 step 실패해야 재계획됨(핵심기능 6 즉각 반응 미흡)

### step 완료 인지
- 모델 호출은 **GOAL 시도당 `/plan` 1회**. step 마다 모델에 묻지 않음, 남은 step 재입력도 없음
- 완료 판정 = 봇 실행함수 정상 반환
  - gather(채광·벌목): 시작 보유량 + cnt 도달까지 반복, 과다 시도시 `stuck` 실패
  - craft/smelt/place: 동작 성공시 반환, 아니면 `Fail` throw
- 실패시에만 `/plan` 재호출 → planner 가 **현재 인벤** 기준으로 다시 계산 → 이미 모은 재료만큼 step 자연 감소
- planner 가 step 마다 `done: "inv[X]>=n"` 조건 생성하지만 **봇 미사용**

### step 성공 기준 (현재)
| type | 성공 | 판정 대상 |
|---|---|---|
| mine/log/dig | 인벤 수량 ≥ 시작+cnt | 인벤 |
| craft | 인벤 수량 ≥ 시작+cnt (1회씩 재동기화) | 인벤 |
| place | 해당 좌표 블럭 = target | 월드 |
| furnace | 결과칸 ≥ cnt → 꺼냄 | 화로 칸 (인벤 수령 미확인) |
| expedition | 64칸 내 대상 발견 | 발견 여부 |
| hunt | 몹 엔티티 소멸 | 엔티티 (디스폰도 성공, 드랍 미확인) |
