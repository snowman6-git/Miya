# bot/

[한국어](README.md) | **English**

The mineflayer bot is only an executor. It collects state, sends it to the model server (`model/serve.py`), and carries out primitive actions such as walking, digging, crafting and fighting. It contains no decision logic.

| File | Role |
|---|---|
| `src/main.ts` | chat → `/turn` → GOAL run (`/plan` → steps → `/qed` record, replans up to 5 times), survival loop (`/prio`), death records (`/death`), inventory tidy (`/tidy`) |
| `src/web.ts` | Web API on :8090 (state SSE, commands, icons, settings) → [../WEBUI_API.md](../WEBUI_API.md) (Korean) |
| `src/settings.ts` | Execution and call-rate settings, saved to `settings.json` |
| `src/viewer.ts` | `/viewer` 3D view (prismarine-viewer, remaps 26.1.2 → 1.21.4 state ids) |
| `src/tester.ts` | Test player: append a line to the `IN` file to send it as chat |
| `src/diag.ts` | Connection and inventory diagnostics |
| `replies.json` | Reply templates (`key: [sentences…]`, `{var}` substitution; Korean) |

## Run

```bash
npm install
npm start -- --server localhost:25565   # online server: --auth microsoft
# or ./run.sh from the repo root (server + bot, auto-reconnect)
```

| env | flag | default | purpose |
|---|---|---|---|
| `MC_HOST` / `MC_PORT` | `--server host[:port]` | localhost / 25565 | Minecraft server |
| `NAME` | `--name` | Miya | bot name (account email for microsoft) |
| `MC_AUTH` | `--auth` | offline | `offline` (online-mode=false server) · `microsoft` (online server) |
| `MC_PROFILES` | - | bot/.auth | Microsoft token cache (gitignored) |
| `MC_VERSION` | `--version` | 26.1.2 | `auto` = detect server version (untested) |
| `API` | `--api` | http://127.0.0.1:8765 | model server |
| `WEB` | `--web` | 8090,8091 | web UI ports (comma-separated) |
| `LOG` | - | - | set to `1` to print logs |
| `HIST` | - | settings | whether to use multi-turn history |

`npx tsx src/main.ts --help` lists the options. Precedence: flags > env.

Microsoft login: the first run with `--auth microsoft` prints `[MS 로그인] https://microsoft.com/link 에서 코드 XXXX 입력` (open the link, enter the code). Sign in with an account for the bot; the token is cached and later runs log in automatically.

Requirements: Node 24+ and a 26.1.2 server (offline mode, or Microsoft login). The bot handles all chat; no prefix is needed.
Web viewer textures (`assets/`) are not in the repo → [../docs/extract.en.md](../docs/extract.en.md)
