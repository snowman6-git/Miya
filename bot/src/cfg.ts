// 접속 설정: CLI 인자 > env > 기본값. 예) tsx src/main.ts --server mc.example.com:25565 --name Miya --api http://gpu:8765
const argv = process.argv.slice(2)
const arg = (k: string) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : undefined }
if (argv.includes('-h') || argv.includes('--help')) {
  console.log('옵션(= env): --server host[:port] (MC_HOST/MC_PORT)  --name (NAME)  --api (API)  --version 26.1.2|auto (MC_VERSION)  --auth offline|microsoft (MC_AUTH, 정품서버)  MC_PROFILES=MS 토큰 캐시 폴더  --web 8090,8091 (WEB)')
  process.exit(0)
}
const [sh, sp] = (arg('server') ?? '').split(':')
export const HOST = sh || process.env.MC_HOST || 'localhost'
export const PORT = +(sp || process.env.MC_PORT || 25565)
export const NAME = arg('name') ?? process.env.NAME ?? 'Miya'
export const API = (arg('api') ?? process.env.API ?? 'http://127.0.0.1:8765').replace(/\/$/, '')
const ver = arg('version') ?? process.env.MC_VERSION ?? '26.1.2'
export const VERSION: string | false = ver === 'auto' ? false : ver  // auto=서버 버전 자동감지(미검증 버전은 레시피 어긋날 수 있음)
export const AUTH = (arg('auth') ?? process.env.MC_AUTH ?? 'offline') as 'offline' | 'microsoft'  // microsoft=정품 서버(첫 실행시 기기 로그인 코드 출력)
export const WEB = (arg('web') ?? process.env.WEB ?? '8090,8091').split(',').filter(Boolean).map(Number)
const PROFILES = process.env.MC_PROFILES ?? `${__dirname}/../.auth`  // MS 토큰 캐시(미공개, gitignore)
// microsoft: username=계정 식별용(이메일 권장), 실제 게임 닉은 계정 프로필. 첫 실행시 코드 출력 → microsoft.com/link 에서 로그인, 이후 캐시
export const conn = (username: string) => ({
  host: HOST, port: PORT, username, version: VERSION, auth: AUTH,
  ...(AUTH === 'microsoft' ? {
    profilesFolder: PROFILES,
    onMsaCode: (d: any) => console.log(`[MS 로그인] ${d.verification_uri} 에서 코드 ${d.user_code} 입력 (${Math.round(d.expires_in / 60)}분 내)`),
  } : {}),
})
