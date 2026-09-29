# bench/

**한국어** | [English](README.en.md)

Miya-0.2와 LAYA base(제로샷)를 비교합니다. planner·QED·봇은 같고 판단만 바꿨습니다. 결과 요약: [RESULT.md](RESULT.md)

| 파일 | 내용 |
|---|---|
| `RESULT.md` | 오프라인 + 인게임 결과 요약 |
| `offline.md` | `eval/bench.py` 출력 (실발화·plan·prio·tidy 정확도, 지연) |
| `game.md`, `game_re.md` | `eval/bench_game.py` 출력 (14 시나리오, 1차·재측정) |
| `rcon.py` | `rcon.py <port> <cmd…>` 벤치 서버 명령 (stdlib) |

## 인게임 벤치 구성

같은 시드의 로컬 Paper 서버 2대에 봇을 하나씩 붙입니다.

| | 서버 | rcon | 서빙 | 봇 web |
|---|---|---|---|---|
| Miya | `bench/b` (:25581) | 25591 | :8767 | :8190 |
| LAYA | `bench/a` (:25582) | 25592 | :8766 | :8191 |

서버 폴더(`a/`, `b/`, `base/`=Paper 공용 libraries), 로그, `*.db`는 저장소에 포함되어 있지 않습니다. 두 서버는 `server.properties`에 같은 `level-seed`를 넣어 만듭니다.
