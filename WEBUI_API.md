# WEBUI_API: 봇 GUI 상태 (2026-09-29)

봇은 데이터만 내보냄, 그리기는 webui 담당. 기존 `/state` 및 `/events`(event: state, 500ms) 페이로드에 포함

## 인벤토리 (기존)
| 필드 | 내용 |
|---|---|
| `inv[36]` | 인벤 슬롯 9~44 순서: [0..26]=메인 3줄, [27..35]=핫바 |
| `armor[4]` | 머리·가슴·다리·발 |
| `offhand` | 왼손 |
| `sel` | 핫바 선택 0~8 |

슬롯 값: `null` 또는 `{name:'minecraft:x', ko, count, dur:{left,max}|null, ench:[], custom}`
아이콘: `GET /icon/<name>` → `{kind:'flat',layers}|{kind:'block',up,north,east}|{kind:'chest',tex}`, 이미지 `GET /mc/<path>`

## 열린 창 `window` (신규)
닫혀있으면 `null`. 봇이 작업대·화로·상자 등을 여는 동안만 값 있음
```json
{ "id": 3, "type": "furnace", "title": "container.furnace", "slots": [ ...컨테이너 슬롯만 ], "props": { "0": 120, "1": 200, "2": 57, "3": 200 } }
```
- `type`: 창 종류 (crafting, furnace, blast_furnace, smoker, generic_9x3(상자), generic_9x6(큰상자), anvil 등)
- `title`: 번역키 또는 표시명
- `slots`: 컨테이너 부분만. 창 열린 동안의 플레이어 인벤은 위 `inv` 사용
- `props`: 창 속성 패킷 원값 (property → value), 창 열릴 때 초기화

슬롯 배치
| type | slots |
|---|---|
| crafting (작업대) | 0=결과, 1~9=3x3 격자 |
| furnace / blast_furnace / smoker | 0=재료, 1=연료, 2=결과 |
| generic_9x3 / 9x6 | 27 / 54칸, 행 우선 |

화로 props: 0=남은 연료 틱, 1=연료 최대, 2=굽기 진행, 3=굽기 총량 → 불꽃 `p0/p1`, 화살표 `p2/p3`

## 변경 위치
- bot/src/main.ts: `win()`, `winProps` (webState 에 `window` 추가)

## QED 발현 표기 (신규)
SSE `event: log` 의 `type:'decision'` (작업 시작·재계획마다)에 필드 추가
```json
{ "type": "decision", "text": "...", "goal": "철 검", "via": "바로 제작", "via_id": "direct", "attempt": 1, "prev": "돌 곡괭이 경유",
  "steps": ["log:oak_logx2", "craft:oak_planksx4", "..."], "qed": { "changed": true, "base": "바로 제작", "base_id": "direct", "ev": { "via:stone_pickaxe": { "n": 3, "ok": 0.67, "avg_ms": 52000, "recent_fail": 1, "fail": "no_material" } } } }
```
- `qed: null`: 해당 GOAL 경험 없음 (배지 없음)
- `changed:false`: 경험 참고했으나 판단 동일 (예: 회색 배지 "QED 참고")
- `changed:true`: 경험이 결정 바꿈, `base`=경험 없었으면 골랐을 방법 (예: 강조 배지 "QED: base → via")
- via·base·prev = 한글 표시명(예: "제작대 재사용, 화로 재사용, 연료 석탄"), 원 id는 via_id·base_id. ev 키는 원 id
- `ev`: 방법(via)별 과거 기록 n=횟수, ok=성공률, avg_ms=성공시 평균, recent_fail=최근 연속 실패, fail=마지막 실패 사유
- 판정법: 서빙이 경험 빼고 한번 더 선택(+~45ms)해 비교

## TASK 교체·진행 이벤트 (애니메이션용)
SSE `event: log` 순서: `decision` → `step`/`crafted`/`smelted` (단계 완료) … → 실패시 `step-fail` → 재계획 `decision`(attempt+1)
| type | 필드 | 의미 |
|---|---|---|
| decision | goal, via, attempt, prev, steps[], qed | attempt 0 = 새 GOAL, ≥1 = 재계획(TASK 교체, prev→via) |
| step / crafted / smelted | title, n, of, step | n/of 단계 완료 |
| step-fail | n, of, why, text | n단계 실패 (why: no_material, no_target, stopped 등) |
| decision (text '우선순위: …') / evade | text | 생존 선점 (전투·도망·먹기 등), 원 GOAL 은 state.paused 로 |
- 상태 스냅샷: `state.plan = {title, steps:[{ko, state:'todo'|'doing'|'done'|'fail', why?, for?}]}`, `state.task`, `state.paused`
- steps[] 문자열: `<type>:<target>x<cnt>` (type=log/mine/craft/place/furnace/hunt…, target=MC id)

## TASK 이유 (신규)
"왜 이 단계/방법인가" 표시용. 판단 = 모델, 이유 = planner 사실
- **단계 이유 `for`** (문자열, 한글): 이 단계 산출물을 요구한 상위템·개수. `목표 N` = 최종 GOAL 직접
  - 위치: `state.plan.steps[i].for`, SSE `step`/`crafted`/`smelted` 의 `for`
  - 예: `craft 막대기 ×4` → `for: "철 곡괭이 2, 나무 곡괭이 2"` / `craft 철 곡괭이 ×1` → `for: "목표 1"`
  - 없음(undefined) = 부수 단계(원정 등)
- **방법 이유 `alts`** (decision 이벤트): 모델이 본 방법 후보 상위 3 (확률 내림차순)
  - `[{opt, p, pick}]` · opt = `via | 단계 요약 | 예상 N초 위험 M% | 경험 …` (QED 경험 텍스트 포함, 모델 입력 그대로) · p = 모델 확률 · pick = 선택됨
  - `ask | 플레이어에게 도움 요청하고 대기 …` 후보가 뽑히면 봇이 도움 요청(`goal.ask`)
- **채팅 사유 `why`** (decision 이벤트, /plan 응답): 시작 채팅에 붙는 짧은 사유 사실. 말투 = `bot/replies.json` `why.<k>`
  - `[{k, ko, ...}]` k: `reuse`(설치물 재사용) · `fuel` · `fuel_fast`/`fuel_safe`/`fuel_exp`(+`alt` 차선 연료, `dt` 초 차이, `dr` 위험%p 차이) · `via`(중간 도구 경유) · `qed`/`qed_changed`(+`n` 경험수, `ok` 성공%, `base` 경험 없을때 고를 방법)
  - 채팅 예: "철 곡괭이 1개 만들게요! (8단계) 제작대, 화로는 있는거 쓸게요! 연료는 석탄 쓸게요, 원목보다 12초 빨라요."
- **모달 상세 `detail`** (decision 이벤트): 판단 근거 전부 → WEBUI 모달용
```json
{ "ctx": "GOAL: 철 곡괭이 1 | 체력 20/20 낮 … (모델 입력 상황 그대로)",
  "pick": "reuse:crafting_table,via:stone_axe", "pick_ko": "제작대 재사용, 돌 도끼 경유",
  "qed_changed": true, "qed_base": "제작대 재사용",            // 경험 빼고 골랐을 방법 (changed=false면 참고용)
  "opts": [ { "via": "reuse:crafting_table", "ko": "제작대 재사용", "p": 0.022, "pick": false,
              "est_s": 173, "risk": 5,                       // planner 추정 (사실)
              "val_s": 169, "val_ok": 34,                    // 모델 가치헤드 예측 (초, 성공%)
              "qed": { "n": 20, "ok": 0.25, "avg_ms": 21383, "recent_fail": 15, "fail": "no_target" } | null,
              "steps": ["원정 돌 1", "채광 돌 8(돌 곡괭이)", "…"] },
            …,
            { "via": "ask", "ko": "도움 요청", "p": 0.0, "pick": false, "est_s": 300, "risk": 0 } ] }
```
  - 모달 권장: 후보 표(p 막대·추정/예측 시간·위험·QED 경험) + 선택 행 강조 + qed_changed면 "경험으로 바꿈: base → pick" + 행 펼치면 steps
- 이유 표시 예: "막대기 4개 만들어요 (철 곡괭이 2, 나무 곡괭이 2에 필요)" / "돌 곡괭이 경유 선택 72% (경험 3회 성공 100%)"
```json
{ "type": "decision", "goal": "철 곡괭이", "via": "돌 곡괭이 경유", "alts": [
  { "opt": "via:stone_pickaxe | 벌목 참나무 원목 3 → … | 예상 180초 위험 10% | 경험 3회 성공 100% 평균 170초", "p": 0.72, "pick": true },
  { "opt": "direct | …", "p": 0.21, "pick": false } ] }
{ "type": "step", "title": "철 곡괭이 1개", "n": 3, "of": 9, "step": "craft 막대기 ×4", "for": "철 곡괭이 2, 나무 곡괭이 2" }
```

## 봇 설정 `/settings` (신규)

- `GET /settings` → `{fields:[{key,label,type,group,min?,max?,step?,note?,options?}], values:{key:값}}`
  - type: `bool` | `number` | `choice`(options = {값: 표시명}) | `text`
  - group: 모델 / 생존 / 채광 / 이동 / 행동 → 섹션 묶음용
- `POST /settings` body `{key:값,...}` (부분 전송 가능) → `{changed:[key...], values}`
  - 모르는 키 무시, number는 min~max clamp, choice는 options 외 값 무시
  - 즉시 반영 + `bot/settings.json` 저장(재시작 유지)
- 필드 목록은 GET 응답이 기준(하드코딩 말고 fields로 폼 렌더). 현재 키:
  prio_ms, prio_hold_ms, dist_bucket, hist, threat_r, hp_check, food_check, hp_eat, hp_flee, hostile_policy,
  resume_max, mine_mode(near|stair), stair_w('1'|'3'), stair_h, scan_r, explore_hops, explore_dist,
  dig_path, sprint, parkour, follow_dist, tidy_before, talk
