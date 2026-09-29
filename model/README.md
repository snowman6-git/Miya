# model/

**한국어** | [English](README.en.md)

판단은 전부 모델이 하고, planner·DB는 사실만 계산합니다.

| 파일 | 역할 |
|---|---|
| `miya.py` | 모델 정의: mmBERT 인코더 + GLiNER2식 스키마 입력 헤드 (보기 점수 · 구간 추출 · 아이템 링크(bi + ColBERT) · 가치). 어휘 가지치기는 remap 버퍼로 처리 |
| `catalog.py` | 아이템·몹·그룹 목록(링크 bank), 학습용 줄임말·구어 표현 생성 |
| `planner.py` | 목표+상태 → 방법(via) 후보·단계열·추정 시간·위험. 레시피·채굴시간 사실만 사용 |
| `serve.py` | HTTP 서빙 (stdlib). API 목록은 파일 상단 docstring 참고 |
| `train.py` | 학습 `data/gen/{train,dev}.jsonl` → `ckpt/miya-0.2` |
| `eval.py` | 실발화(`eval/real.jsonl`) · 줄임말 holdout · dev · 지연 평가 → `eval/last_errors.txt` |

## 입력 형식

```
[CLS] 발화 [SEP] 상태·QED [SEP] ([MASK]라벨)×n [SEP] (문항: [MASK]보기…[SEP])×m
```

문항별로 softmax를 취하고, 되묻기(ask)도 보기 하나로 학습합니다.

## 실행

```bash
.venv/bin/python model/serve.py                      # :8765
.venv/bin/python model/train.py                      # 학습
.venv/bin/python model/eval.py                       # 평가
```

| env | 기본 | 용도 |
|---|---|---|
| `CK` | `ckpt/miya-0.2` | 서빙·평가 ckpt |
| `QED` | `data/qed.db` | 경험 DB |
| `PORT` | 8765 | 서빙 포트 |
| `SNAP` | hf_cache 스냅샷 | 베이스 토크나이저·인코더 경로 (없으면 HF에서 받음) |
| `OUT` | `ckpt/miya-0.2` | 학습 출력 |
| `EP` / `BS` / `LR` | 2 / 32 / 3e-5 | 학습 하이퍼파라미터 |
| `PRUNE` | 1 | 어휘 가지치기 |

필요 파일: `mcdata/mc.db`, `data/mcx.db` → [../docs/extract.md](../docs/extract.md)
