# Claude_DEVLOG

## 2026-09-29
- QED 스키마 초안. 이전모델 약점(조건분기 무한루프) 대응: fail_recent 뷰로 최근 반복 실패 선택지 차단
- mcx.db 파생: 가치 역산 버그 2건 수정 (다이아블록 자기드롭->다이아 1.87로 붕괴, 철골렘 드롭->철괴 1.25). 조합 가능 블록 자기드롭은 2단계, 플레이어 제작 몹 제외
- 봇로그 'ate' 이벤트 109,250건: 이전 봇 식사 루프 흔적(체력↔식사 무한반복 약점 실증). QED fail_recent 필요성 근거
- Laya-J 약점 분석: BIO 구간 F1 0.777 < 사전 기준선 0.885 (토큰 쪼개지는 줄임말 약함), 구 헤드 편향 승계 → 0.1a는 GLiNER식 구간-라벨 매칭 + 인코더만 승계
- 0.1a 구조 확정: 인코더만 승계, GLiNER2식 헤드 새로. planner.py 재귀 버그 2건(용암연료→양동이→철굽기→용암, 돌곡괭이 강제업글→조약돌→돌곡괭이) 수정

## 2026-09-29 학습 전처리 CPU 병목
- 문제: encode_row 단일프로세스 26만행 5분+ 동안 GPU 0%
- 원인: 행마다 tok() 개별 호출(보기 수십개 반복) + 파이썬 루프
- 개선: 문자열 캐시(_PC)+배치 pretok+6코어 Pool+pkl 캐시 → 8000행 6s. GPU 우선 규칙 AGENTS.md 추가

## 2026-09-29 Miya-0.1a 1차 학습 결과 (264.6k행, 2ep, 2h)
- 실발화 475: act .937 / type .899 / query .958 / hint .50(6) / tgt .892 / cnt .941, holdout 줄임말 12/12, 지연 p50 17ms
- dev(생성분포): turn .9997 plan .674 prio .871
- eval 버그 수정: parse_count "하나만" 실패, tgt가 장소 구간 먼저 집던 문제
- 오답 유형: 붙여쓴 동사(철캐와→철캐=헬멧, 나무캐, 고기구해와), "맞춰"=제작, 용암/물=bucket, 집합=come, 출발/그냥가=긍정, 단독 "줘/나줘/하나만 줘"=목표(ctx 대상), "상자 정리"=item_all
- 오답인데 확신도 1.00 → 신뢰도 기반 되묻기 불가, 보정(temperature/라벨스무딩) 필요
- plan .67: 방법 선택이 암산(시간 계산) 의존. 입력에 수치 보강 필요

## 2026-09-29 Paper 서버 봇 이동 불가
- 문제: mineflayer 봇이 스폰 지점에서 전혀 못 움직임, 매 틱 서버 position(teleport) 패킷으로 롤백(forcedMove 20/s), 로그엔 경고 없음
- 원인: prismarine-physics가 벽에 bbox 정확히 접촉(x=블럭-0.3)시키면 Paper가 블럭 진입으로 보고 조용히 되돌림. 바닐라 26.1.2 로컬 서버에선 정상 이동 확인
- 개선: bot.physics.playerHalfWidth = 0.301 → Paper에서 6칸 이동, forced 0

## 2026-09-29 Miya-0.1a 첫 인게임 실측 (Paper 26.1.2, 봇 Miya, 서빙 model/serve.py:8765)
- 구성: run.sh → serve.py(/turn /plan /prio /qed /ko, QED=data/qed.db) + bot/src/main.ts(mineflayer, 판단 없음) + tester.ts(Claude op, /tmp/cw/say.txt 줄 추가로 채팅)
- 지연: turn 18~25ms, plan ~45ms, prio ~20ms
- 성공: 이리와/따라와/멈춰/체력/주변/철곡 줘(give)/철뚝→철 투구/나무 5개(66s)/철곡 제작(원목→나무곡→돌 11→돌곡→철광 3→화로→굽기→제작, 여러 시도 후 완료)
- 봇 문제/수정:
  - Paper 이동 롤백 → halfWidth 0.301
  - craft 직후 인벤 미동기 → 증가 대기
  - 설치 no_space(풀) → 대체가능 블럭 허용+층 -1~1
  - Paper 창 stateId 어긋남 → craft 결과슬롯 안옴(updateSlot:0 timeout) → _syncWindow 후 재시도, 제작칸 회수
  - prio 도망 goal이 작업 goal과 매초 충돌 → 도망/전투시 작업 일시정지, '멈춘 작업 재개'로 복귀
  - 실패→멈춘작업→prio 재개 무한루프 위험 → 요청당 자동재개 2회 상한
- 모델 오류(재학습 데이터 필요):
  - "그거론 한참걸리겠는데?" hint=wrong (정답 slow)
  - "나무캐" 대상 span 없음 → 되묻기 대신 "뭘 할까요?"
  - query/type 무관 헤드값(이리와 query=status 등)은 무시 가능
  - prio: 낮 스켈레톤 9칸 맨손 → 달려서 도망 (합리적), 좀비 12칸 도망/14칸 계속 진행 흔들림
- 미구현: expedition(원정 탐색) → 고기 요청시 소 없음 no_target 즉시 실패. 새 요청이 진행중 GOAL 조용히 덮어씀(알림 없음). lava/water ko 이름 없음
- flash-attn 2.8.3 빌드 실패(torch 2.14 헤더 C++20 필요, setup c++17) → 서빙/평가는 sdpa 폴백

## 2026-09-29 QED 기록 점검
- 문제: stopped(유저 멈춤·prio 선점)가 실패로 집계 → 멀쩡한 방법 회피 유도. avg_ms에 실패(0ms 즉사) 포함 → 시간 왜곡
- 문제: 이미 고친 봇 버그(Paper craft desync) 실패 7건이 경험으로 남아 판자 direct 등 오염
- 개선: qed_of에서 stopped 제외, avg_ms는 성공분만. 버그 기인 7행 삭제(백업 data/qed.db.bak-0929)
- 미비: 사망 원인·아이템 가치·변수(보유 도구 등) 미기록 → 다음 단계

## 2026-09-29 craft_unsynced (제작대 제작 실패)
- 문제: 제작대 제작 간헐 실패(craft_unsynced), 재시도시 성공
- 원인: mineflayer stateId 전역 1개. Paper가 창(1) 열린 중에도 인벤(0) set_slot 전송 → 창1 클릭에 인벤 stateId 실림 → 서버 클릭 무시, 재료 인벤 복귀
- 개선: main.ts 창별 stateId 추적 후 window_click 보정. 재현 테스트 2/4 → 8/8
## 2026-09-29 QED 사망/가치/변수
- deaths 테이블, /death /value /lesson, goals.vars. 봇: health마다 스냅샷, 사망메시지 파싱, prio ctx '최근 사망원인'
- 미비: mcx item_value 화강암 4.98 > 조약돌 0.5 (레시피 기반 과대평가)
## 2026-09-29 실측 문제 묶음
- 제작 중 no_material: 제작 클릭 늦은 응답이 _syncWindow 응답 뒤에 와서 인벤 비어보임 → settle(): 창 패킷 잠잠해질때까지 재sync. 상자2개(원목16) 재계획 없이 성공
- 타임아웃·포기 빠름: 경로 30→60s, 캐기 20→40s, 사냥 30→60s, 원정 4→6홉·48→64칸, 재계획 3→5, 스텝재시도 2→3(+no_target), stuck 상한 cnt*4+10
- 작업 끝나도 유휴 안됨: plan 안 비움 → 종료 5초후 비움, 멈춤/사망시 즉시
- 돌 캐 → 돌 굽기: 모델이 돌=stone 링크. serve 규칙(X, 판단은 모델) 대신 gen 캐기 문장 링크를 드롭템으로(MINE_DROP 돌→조약돌), 굽기 문장은 결과물로(SMELT_OUT 철→철괴)
- 철 5개 구워 → 원석만 캠: 굽기 링크가 재료(grp:iron). 위 SMELT_OUT 으로 해결 예정(재학습)
- 구워(단독, 직전 철 5개) → 뭘 할까요: 봇이 봇질문 없으면 hist 안보냄. 2분내 직전대화 전달 + gen 생략발화 행(대상=이전 발화) + 무관 hist 25%. 현 ckpt는 hist에 약해(real act .937→.816) HIST=0 으로 끔, 재학습후 켬
- 익사 판정: mineflayer 가 모든 엔티티 air_supply 를 bot.oxygenLevel 에 씀(오징어 등). 자기 entityId 만 반영. prio ctx 산소 + '물 위로 올라가기' 라벨(gen)
- 막대기 만들어(막대기 보유) → 모르겠어요: 플래너가 보유분을 목표 충족으로 봄 → serve.plan 목표템 보유분 제외(n개 더)
- 실발화 오분류(재학습 대상): 집합/집함→craft, 철캐와→hunt, 나가서 몹좀→come, 농사→되묻기, 경작지 만들어→craft. gen: 오타 증강(구간밖 1자), 붙여쓰기 동사, 대상없는 farm/combat

## 2026-09-29 (오후) 인게임 멈춤·용어·설치물
- 멈춤1: 스켈레톤 14칸 → 달려서 도망 PAUSE → 위협 사라져도 prio가 '계속 진행'(재개 아님) → 영구대기. 봇: 멈춘작업 있고 위협없으면 '계속 진행'도 재개로 실행(RESUME). gen PAUSED_REQ 다양화로 모델도 교정(재학습)
- 멈춤2: 작업대로 go 중 서버 "moved wrongly" 롤백 반복 → go 60초×재시도4 = 3분 정지. go 워치독: 12초 제자리면 Fail('stuck')
- 멈춰 후 runGoal 크래시(plan null) → 스텝 루프 가드
- 철갑옷 = 흉갑(유저 정의), 풀셋/세트/풀장비 = set. catalog 별칭 분리, gen 제작/장착 풀에 흉갑·세트 대비 가중, eval 8건 재라벨 + 4건 추가
- 설치물: /placed del(좌표)|kind|all 삭제 API. 봇 own(DB) 기준 가장 가까운 설치물, 청크 미로드(먼곳)면 거리만 보고 plan이 reuse/new 판단(왕복 거리비용, gen 설치 거리 80~2000 30%). 가서 없으면(타인 파괴) forget → DB 삭제. 800칸이면 new 선택 확인
- 정리(tidy): 버리기는 작업 필요칸 > 빈칸일때만(작업 필요칸 = 방법 스텝 결과중 미보유 스택수), 판단은 모델. 봇 고정 임계(빈칸≤6) 제거, 매 작업전 /tidy. 미학습 ckpt(schema에 tidy 없음)면 serve가 빈 결과(쓰레기값 방지)
- 데이터 재생성 290k (tidy/space/먼 설치물/철갑옷/PAUSED_REQ). 재학습 대기
- 나무 캐와 → 아카시아 등 무시하고 멀리 감: 봇 NEAR·플래너가 oak_log 만 인지 → 주변 원목 없음 → 원정. 목재 종 통합: planner.wood()(inv 합·near 최소, 종 지정 GOAL만 구분), serve가 목재 스텝에 any 표시 → 봇 fam()으로 11종 원목/판자/연료 실행, 판자는 가진 원목 종으로. NEAR 전 종. gen plan ctx 종 다양화(60%)+먼 다른 종 방해, 종 지정 채집 대상 추가. 데이터 재생성
- 서버 "Miya moved wrongly" 시각(15:44:56, 15:45:57) = 봇 go 타임아웃 RETRY 시각 일치 → go 워치독(12초 제자리 stuck)으로 대응

## 2026-09-29 Miya-0.2 학습 시작
- ColBERT 링크: 구간 토큰(≤8) vs 이름 토큰(≤32) 128차원 MaxSim 평균, bi 로짓 + exp(col_scale)·col. NULL=col_null. eval Runner 토큰 bank [1624,32,128]
- 어휘 가지치기: 256,000 → 29,252 토큰(데이터·실측·채팅·카탈로그 사용 + 한글/바이트/ASCII≤3), 313M → 139M. remap 버퍼로 토크나이저 그대로
- 데이터 284.2k/5.8k (0.1a 264.6k/5.4k). 75ex/s ≈ 2.1h
- 서버 재부팅 대응: run.sh 봇 루프(포트 열림 대기→재접속), k()는 setsid 그룹 kill. serve CK 기본 = 최신 ckpt 자동
- 리브랜딩 laya→miya: 봇 emit type/webState 필드 miya, build(base_init), gen BOTNAMES 미야 변형만(Laya/라야 제거, 0.3 데이터부터). webui 수신부 교체는 webui_replace.md
- 뷰어 끊김: prismarine-viewer 번들이 틱마다 50ms 트윈을 겹쳐 생성(구·신 트윈 충돌) + 1인칭 회전 즉시 스냅. viewer.ts가 /viewer/index.js 패치 서빙: 트윈 1개 유지(stop), VIEW_SMOOTH=120ms, 카메라 회전 최단각 트윈. 번들 바뀌면 원본 폴백(VIEWER patch miss 로그)
- craft furnace no_material (07:42): gather 중 ensure_tool(돌곡)이 모으던 조약돌 3 소모 → 화로 8 부족. planner gather: 도구 제작 소모분만큼 채집량 추가 (돌 캐기 2→5 확인). 0.3 데이터 재생성시 반영
- 전투↔도망 루프 (07:46~07:47, 로그 data/loops/2026-09-29_0746_fight_flee_skeleton.log): 스켈레톤 1, 체력 19 철검. 10·9칸 → 근접 전투(0.81/0.54), 7·8칸 → 달려서 도망(0.56) → 멀어지면 다시 전투 반복, 1초마다 PRIO.
  원인: gen prio 교사규칙은 거리 무관(danger만)인데 모델이 거리 경계를 가짜로 학습(확신도 0.5대), ctx에 현재 행동 없음 → 히스테리시스 없음. 스켈레톤(원거리)에 달려서 도망은 오히려 불리
  0.3 반영 예정: ctx에 '현재 행동: X (N초)' 추가 + 교사규칙 유지 편향(상황 급변 아니면 현재 행동 유지), 거리 변동만 다른 쌍 데이터(같은 라벨), 원거리몹은 근접 전투/엄폐 우선
- QED 발현 표기: /plan 이 경험 있을때 경험 뺀 옵션으로 재선택 → qed{changed,base,ev} 반환, 봇 로그 'QED 바꿈/참고' + decision 이벤트 qed 필드 (WEBUI_API.md). 07:42 화로 실패 후 direct 전환 재현: 같은 상황+실패기록에도 stone_pickaxe 유지(changed false) → 당시 전환은 QED 아니라 돌곡 이미 제작돼 인벤 변화로 방법 후보가 바뀐 것
- QED 발현 인게임 (08:02): 나무 5개 → 방법 1개라 '참고'. 상자 → 'QED 바꿈 direct → reuse:crafting_table', 27s 성공. 단 두 방법 ev 동일(n12 ok.33): core()가 reuse:/fuel: 제외해 같은 묶음 → 경험 차이 아닌 경험 텍스트 유무로 바뀐 것. 0.3: 비교 근거가 다를 때만 changed 인정 or core 에 reuse 포함 검토
- 봇 호출명: gen addr() 가 발화 25%에 BOTNAMES 접두 → 유저 결정: 호출명은 봇 PREFIX 로 처리. 0.3 gen 에서 addr 제거, 봇이 접두 떼고 모델에 전달

## 2026-09-29 계단굴(mine_mode=stair) 실측
- 문제: 금 2개 → 3칸폭 계단굴이 목표용 철곡괭이 내구도 소진(파괴) → 맨손 금 채굴 드랍0 ×8 루프, 맨손 딥슬레이트 dig 20s timeout(err:timeout RETRY)
- 원인: stair가 스텝 tool(철곡괭이)로 모든 블럭 팜, gather가 도구 소실 체크 안함
- 개선: stair는 싼 곡괭이부터(나무→돌→…) 소모, 없으면 no_tool / gather도 도구 없으면 no_tool → 재계획(곡괭이 재제작)
- 결과: 재시도 성공. 돌곡괭이로 y11→-16 계단(≈8s/칸), 철곡괭이로 금 2개, 스텝 325s
- 광석 높이: ore_gen(mcx.db) 밀도로 serve가 mine 스텝에 y 부여(P.ore_y). 모델은 방법 선택만
- via/base 한글 표기(serve via_ko, decision via·base 한글·*_id 원본) — 2026-09-29

## 2026-09-29 익사 후 정지·재사망
- 문제: 익사 리스폰 후 봇 제자리(go stuck 6분), 땅 위에서 '물 위로 올라가기' 반복 → 스켈레톤에 사망. 실익사 4건(철곡·고기·철투구·철셋 채광중)
- 원인1: 리스폰시 서버가 air_supply 메타 재전송 안함 → air -1 고착 → prio 매 틱 호출·오판. 수정: spawn 이벤트에 air=20
- 원인2: '물 위로'가 점프만 → 머리 위 막힘(수중 채굴)이면 탈출 불가. pathfinder는 물속 공중칸 "No path". 수정: surface() — 물·빈칸 BFS로 머리 공기인 최근접칸 경로 → lookAt+전진+점프 조향. 웨이포인트 진행은 수평거리(뜬 높이·천장 때문)
- 실측: 유리천장 수조(구석 1칸만 개방) 산소 5→19 탈출 성공. /kill 리스폰은 재현 안됨(익사만)
- 모델 측(0.3): 산소 7·체력 5에서야 '물 위로' 선택, 산소 -1에 '재개' 선택 → 데이터 보강 노트
- 테스트 사망 기록(수조·/kill·낙하·연쇄 화살) QED deaths에서 삭제 (유저 승인)

## 2026-09-29 끼임/정지 조사
- 증상: 이동 로그 없이 제자리 정지, 작업 PAUSE 반복(철곡 16회·나무 9회 "goal was changed")
- 원인1: 위협 인지에 시야 없음 → 지하 y62 채굴중 지상 y71 스켈레톤(돌 9칸 너머) 11칸 → 도망 0.97 무한, 멈춘작업 재개 안됨. 수정: raycast seen(), 4칸 이내 or 보이는 몹만 위협
- 원인2: 도망 GoalInvert(GoalFollow) 굴·좁은길서 경로 못찾고 조용히 정지(끼임감지 없음). 수정: 반대방향 16칸 고정점 GoalNearXZ + go()(12s 끼임·15s 상한), 실패시 hold 해제
- 원인3: go() finally setGoal(null)이 다음 호출의 새 goal 지움(prio 틱마다 도망 재발행 → 즉시 취소). 수정: 자기 goal일때만 해제
- 검증: 터널 좀비(저항 부여) → 9칸 파며 도망, 15s 후 재판단. 첫 시험은 저항 없이 해서 Miya 사망(드랍 tp 회수, deaths에 좀비 1건 기록됨)
- 사망 직후 빈 인벤 "철곡 만들어" → "만드는 법 모르겠어요": 모델 via=ask(0.2 ask 라벨 버그, gen.py 수정됨·재학습 대기) + 봇이 steps 비었으면 unknown 먼저 출력. 수정: ask 먼저 검사
- 기타: 스폰 직후 health 미수신 → prio ctx 체력 NaN → ?? 20

## 2026-09-29 stuck 언스틱 · 좀비 명령
- stuck(.36 로그: 화로 스텝 중 "Miya moved wrongly!" ~13초 반복, 유저 "위에 있는 돌 캐"로 해결): 점프 경로에 머리위 돌 → Paper 이동 거부 → pathfinder 루프. go() 첫 stuck시 unstick(): 머리위(0,2,0)·앞 발/머리/머리위 고체 블럭을 최적 도구로 캐고 남은 시간 재시도, 2회째 stuck만 실패. 컨테이너·작업대·침대·기반암·액체 아래 블럭 제외, dig_path=false면 안함
- "좀비 죽여/좀비사냥해 → 좀비 만드는 법을 모르겠어요": 모델 분류(combat mob:zombie)는 정상, prod serve가 planner mob GOAL 수정(11:12) 전 11:10 기동 → 옛 planner 빈 계획. serve 재시작으로 해결(전투 좀비 1 계획 확인)
- "좀비처리해 → enchant": 붙여쓰기 전투 발화 오분류. gen combat 동사 30% 붙여쓰기 + E_KILL 보강(처치해·없애·해치워 등), eval/real.jsonl 실발화 3건 추가. 다음 재생성·재학습 반영

## 2026-09-29 벤치 Miya-0.2 vs LAYA base → bench/RESULT.md
- 오프라인: act 94.5 vs 11.0%, 대상 87.3 vs 6.2%, plan 73.6 vs 27.4%, prio 86.6 vs 11.5%. 인게임 13/14 vs 0/14
- LAYA 서빙 16초/턴 → 재시작 후 0.3초 (첫 서빙 프로세스 이상, 재현 안됨)
- 봇 버그: 흙 밑 돌 채굴 "No path" 반복 → no_target. GoalLookAtBlock 은 실월드 시야판정이라 묻힌 블럭 불가 → No path 시 GoalGetToBlock 폴백
- "철곡 만들어 → 혼자 하기 어려워요": 주변에 철·석탄 안보임 → 원정 위험 +0.3씩 누적 90% → ask. 광석(ore_gen)은 계단굴로 찾으니 저위험(y≥0 0.1, 깊으면 0.2), 돌·흙 0.05
- QED "A → A" 표기: 같은 via(단계수만 다름) 후보 index 비교. planner 같은 via 중복 제거 + changed 를 core 경로 비교로
- 채팅 사유(why): 재사용·연료(차선 대비 시간/위험)·경유·QED → 시작 채팅에 붙임. detail(후보 전부 p·추정·가치·QED·steps) decision 이벤트 → 모달용, WEBUI_API 기재

## 2026-09-29 공개 문서
- 폴더별 README(ko/en), 루트 README 재작성, IP→.env, 인포그래픽 docs/miya_infographic.svg, TASK_TYPE 이미지(docs/task_type.webp, hf/task_type.webp) README·HF 카드에 추가
- 인포그래픽 영문판(docs/miya_infographic.en.svg) + 생성기 docs/infographic.py, miya_arch.svg/png 삭제·대체

## 2026-09-29 배포용 접속 설정
- bot/src/cfg.ts: CLI 인자 > env > 기본값 (--server/--name/--api/--version/--auth/--web), main·diag·tester 공용
- MS 로그인: --auth microsoft → prismarine-auth 기기코드, 토큰 bot/.auth (gitignore). 미설정시 offline(online-mode=false 서버 필요)
- run.sh: `./run.sh host:port`, .env 는 기존 env 우선, API 원격이면 로컬 서빙 생략. serve.py SERVE_HOST 바인드
- .env.example 공개용 추가, README(ko/en)·bot README·HF 카드에 오프라인 모드/MS 로그인 안내
- 미검증: 실제 정품 서버 MS 로그인 (계정 없음)
- 2026-09-29 README·HF: QED 판단근거 예시(docs/qed_example.webp) 추가, GitHub README 실험적(WIP) 경고·한계 섹션
- 2026-09-29 README 4종 실서빙 예시(turn/plan/prio), serve ctx:"" 허용, HF config.json(다운로드 집계)
