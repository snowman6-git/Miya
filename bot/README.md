# bot/

**한국어** | [English](README.en.md)

mineflayer 봇은 실행기 역할만 합니다. 상태를 모아 서빙(`model/serve.py`)에 보내고, 받은 결정대로 걷기·캐기·제작·전투 같은 원시 행동을 수행합니다. 판단 로직은 없습니다.

| 파일 | 역할 |
|---|---|
| `src/main.ts` | 채팅 → `/turn` → GOAL 실행(`/plan` → 단계 실행 → `/qed` 기록, 실패시 재계획 최대 5회), 생존 우선순위 루프(`/prio`), 사망 기록(`/death`), 인벤 정리(`/tidy`) |
| `src/web.ts` | webui API :8090 (상태 SSE, 명령, 아이콘, 설정) → [../WEBUI_API.md](../WEBUI_API.md) |
| `src/settings.ts` | 실행 방식·호출 빈도 설정, `settings.json`에 저장 |
| `src/viewer.ts` | `/viewer` 3D 뷰 (prismarine-viewer, 26.1.2 → 1.21.4 stateId 변환) |
| `src/tester.ts` | 테스트 플레이어: `IN` 파일에 줄 추가 → 채팅 전송 |
| `src/diag.ts` | 접속·인벤 진단 |
| `replies.json` | 말투 템플릿 (`키: [문장…]`, `{변수}` 치환) |

## 실행

```bash
npm install
npm start -- --server localhost:25565   # 정품 서버: --auth microsoft
# 또는 루트에서 ./run.sh (서빙+봇, 자동 재접속)
```

| env | 인자 | 기본 | 용도 |
|---|---|---|---|
| `MC_HOST` / `MC_PORT` | `--server host[:port]` | localhost / 25565 | 서버 |
| `NAME` | `--name` | Miya | 봇 이름 (microsoft면 계정 이메일) |
| `MC_AUTH` | `--auth` | offline | `offline` (online-mode=false 서버) · `microsoft` (정품 서버) |
| `MC_PROFILES` | - | bot/.auth | MS 토큰 캐시 (gitignore) |
| `MC_VERSION` | `--version` | 26.1.2 | `auto` = 서버 버전 자동 (미검증) |
| `API` | `--api` | http://127.0.0.1:8765 | 서빙 주소 |
| `WEB` | `--web` | 8090,8091 | webui 포트 (쉼표로 여러 개) |
| `LOG` | - | - | `1`이면 로그 출력 |
| `HIST` | - | settings | 멀티턴 hist 사용 여부 |

`npx tsx src/main.ts --help` 로 옵션 확인. 우선순위: 인자 > env.

MS 로그인: `--auth microsoft` 로 첫 실행시 `[MS 로그인] https://microsoft.com/link 에서 코드 XXXX 입력` 이 출력됩니다. 봇 전용 계정으로 로그인하면 토큰이 캐시되어 다음부터 자동입니다.

요구: Node 24+, 서버 26.1.2 (오프라인 모드 또는 MS 로그인). 채팅은 접두어 없이 전부 봇이 처리합니다.
웹 뷰어 텍스처(`assets/`)는 저장소에 포함되어 있지 않습니다 → [../docs/extract.md](../docs/extract.md)
