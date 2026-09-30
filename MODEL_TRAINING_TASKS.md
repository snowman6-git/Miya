# Miya 모델 학습 태스크

학습·검증·배포 표준 절차. 신규 데이터/모델 변경 시 이 순서대로 진행

## 0. 변경 규모 판단

| 규모 | 예 | 방식 |
|---|---|---|
| 소규모 | 표현 보강, 소량 데이터 추가, 오분류 수정 | 이전 Miya ckpt 이어학습(`INIT`) |
| 대규모 | 헤드·라벨·입력포맷·어휘 변경, 버전업 | 처음부터 학습 |

- 구 Laya 파인튜닝 모델·데이터셋 사용 금지. 자체 Miya ckpt 만 warm-start 허용
- 버전 규칙은 AGENTS.md「모델 버전」 따름

## 1. 파이프라인

1. **데이터 생성**: `data/gen.py` → `data/gen/{train,dev}.jsonl`. 이전 `.enc.pkl` 캐시 삭제
2. **스모크**: 이어학습 EP0.1 (또는 LoRA, §3) → eval 로 데이터 효과 방향 확인
3. **본학습**
   - 소규모: `INIT=<이전ckpt> EP=0.3~0.5 LR=2e-5 HLR=1e-4 BS=64 COMPILE=1`
   - 대규모: 처음부터, 기본 EP/LR
   - 로그 `ckpt/train-<ver>.log`
4. **평가**: `CK=<ckpt> python model/eval.py` → real / latency / holdout slang / dev / errors(`eval/last_errors.txt`). 이전 버전과 항목별 비교
5. **망각 점검**: 이전 대비 하락 항목 있으면 가중치 평균(§2 WiSE-FT) α 스윕 후 eval
6. **서빙**: 최적 ckpt 로 serve 재시작(PID 지정 kill 만)
7. **인게임 테스트**: 실서버 접속, 신규 기능·회귀 플로우 확인
8. **기록**: VERSION_NOTES.md(개선사항 + eval·인게임 실측), Claude_DEVLOG.md(문제·원인·개선)

## 2. 망각 완화 (적용 순)

1. **Replay**: 새 데이터 + 기존 전체 데이터 재생성 학습 (기본 적용)
2. **저 LR·짧은 EP**: 이어학습시 LR2e-5, EP≤0.5
3. **WiSE-FT 가중치 평균**: `A=<이전> B=<신규> ALPHA=α OUT=<dir> python model/soup.py`, α∈{0.3,0.5,0.7} eval 비교. 학습 없음, 수초
4. **KD**: 이전 모델 logit 을 soft target 으로 추가 손실
5. **L2-SP / EWC**: 이전 가중치에서 멀어지는 것 패널티
6. 최후: 처음부터 재학습

## 3. LoRA 용도

- 목적: 데이터셋 검증, A/B(어댑터 on/off), 후보 데이터 여러개 비교
- 원본 가중치 고정 → 부착 중 망각 없음. 개선폭은 본학습 개선의 대략적 하한 경향(보장 X)
- 이후 full 학습시 망각은 예측 못함 → 채택 데이터는 §1 본학습으로 반영
- 헤드는 full 학습. 구조 변경 간 이식 불가
- 자체 구현(peft 미사용), 후보 비교 필요 시점에 추가

## 4. 학습 최적화

| # | 항목 | 상태 |
|---|---|---|
| 1 | 옵션 네거티브 샘플링(GLiNER식): turn 행 ~506tok 중 옵션 ~420 → 정답+샘플 negative 만 | 예정 |
| 2 | TF32 matmul (fp32 4.9TF → tf32 28TF) | 코드 반영, 벤치 전 |
| 3 | bf16 stochastic rounding AdamW (torchao `_AdamW`) | 코드 반영, 벤치 전 |
| 4 | DataLoader collate prefetch + pin_memory (`NW`) | 코드 반영, 벤치 전 |
| 5 | `.item()` 동기화 제거, 옵션 CE 벡터화 | 코드 반영, 벤치 전 |
| 6 | 0.3 구조: 옵션 인코딩 캐시 + 소형 cross-attn (~5x) | 0.3 처음부터 학습시 |

- 기본: bf16 + `torch.compile`, BS64 (INT8 학습은 제외, 서빙 단계에서 재검토)
- 벤치: 600 step 구 로그 대비 ex/s, loss 곡선 동일성 확인

### 정밀도 정책

- 가중치 전부 bf16
- fp32 유지: 업데이트 누적(SR 로 대체), loss·softmax·norm, exp 스칼라(link_scale, col_scale)

## 5. 금지·주의

- 공개 파일에 IP·계정·토큰 기록 금지(`.env` 만)
- 프로세스 종료는 PID 지정만
- GPU 가능한 학습·전처리·평가는 GPU 로
