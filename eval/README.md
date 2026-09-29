# eval/

**한국어** | [English](README.en.md)

| 파일 | 역할 |
|---|---|
| `real.jsonl` | 실발화 평가셋 (서버 채팅 원문 + 라벨, 학습에서 제외) |
| `real_labels.txt` | 라벨 작성 원본 |
| `bench.py` | 오프라인 A/B: 같은 셋을 두 서빙(HTTP)에 보내 정확도·지연 비교표 생성 |
| `bench_game.py` | 인게임 A/B: 같은 시드의 로컬 Paper 2대에서 Miya·LAYA 봇으로 같은 시나리오 병렬 실행 |
| `laya_serve.py` | 비교용 LAYA 베이스(제로샷) 서빙. API는 `serve.py`와 같고 판단만 교체 |

모델 자체 평가는 `model/eval.py`로 합니다.

```bash
PORT=8767 .venv/bin/python model/serve.py &          # Miya
.venv/bin/python eval/laya_serve.py &                # LAYA :8766
.venv/bin/python eval/bench.py 8767 8766 > bench/offline.md
.venv/bin/python eval/bench_game.py > bench/game.md  # 서버·봇은 먼저 기동 (../bench/README.md)
```
