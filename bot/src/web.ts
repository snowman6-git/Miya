// miya-stream-webui 연동 서버 (컨트랙트: miya-stream-webui/Orinthia_spec.md §3), stdlib http만 사용
import { createServer, IncomingMessage, ServerResponse } from 'node:http'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

const MC = path.resolve(__dirname, '../assets/assets/minecraft')  // 26.1.2 client.jar 추출본
type Log = { type: string, [k: string]: unknown }
export const hook: { viewer?: (req: IncomingMessage, res: ServerResponse) => void } = {}
const backlog: Log[] = [], sinks = new Set<ServerResponse>()

export function emit(e: Log) {
  const x = { ts: Date.now(), ...e }
  backlog.push(x); if (backlog.length > 200) backlog.shift()
  const m = `event: log\ndata: ${JSON.stringify(x)}\n\n`
  for (const r of sinks) r.write(m)
}

const readJson = (p: string) => { try { return JSON.parse(readFileSync(p, 'utf8')) } catch { return null } }
const strip = (s: string) => s.replace(/^minecraft:/, '')
// 모델 parent 체인 따라 textures 병합
function textures(model: string): Record<string, string> {
  const j = readJson(path.join(MC, 'models', strip(model) + '.json'))
  if (!j) return {}
  const t = { ...(j.parent ? textures(j.parent) : {}), ...(j.textures ?? {}) }
  for (const k in t) while (t[k]?.startsWith('#')) t[k] = t[t[k].slice(1)]
  return t
}
const png = (t?: string) => t ? `textures/${strip(t)}.png` : ''
// ponytail: 잔디·잎 틴트 미적용, 필요시 tint 추가
function icon(name: string) {
  const n = strip(name)
  if (n === 'chest') return { kind: 'chest', tex: 'textures/entity/chest/normal.png' }
  const m = readJson(path.join(MC, 'items', n + '.json'))?.model?.model ?? 'item/' + n
  const t = textures(m)
  if (strip(m).startsWith('block/')) {
    const side = t.side ?? t.all ?? t.north ?? t.front ?? t.particle
    return { kind: 'block', up: png(t.top ?? t.end ?? t.up ?? t.all ?? side), north: png(t.front ?? t.north ?? side), east: png(t.east ?? side) }
  }
  const layers = Object.keys(t).filter(k => k.startsWith('layer')).sort().map(k => png(t[k]))
  return { kind: 'flat', layers: layers.length ? layers : [`textures/item/${n}.png`] }
}

export function serveWeb(ports: number[], getState: () => any, onCmd: (text: string, as?: string) => void, settings: { fields: any[], values: Record<string, unknown>, set: (b: Record<string, unknown>) => string[] }) {
  const h = async (req: IncomingMessage, res: ServerResponse) => {
    const u = new URL(req.url ?? '/', 'http://x'), p = decodeURIComponent(u.pathname)
    res.setHeader('access-control-allow-origin', '*')  // Tauri 앱 LAN 직결
    res.setHeader('access-control-allow-headers', 'content-type')
    const json = (v: unknown, s = 200) => { res.writeHead(s, { 'content-type': 'application/json' }); res.end(JSON.stringify(v)) }
    const body = async () => { let b = ''; for await (const c of req) b += c; return b ? JSON.parse(b) : {} }
    try {
      if (req.method === 'OPTIONS') { res.writeHead(204); return res.end() }
      if (p === '/state') return json(getState())
      if (p === '/events') {
        res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive' })
        res.write(`event: backlog\ndata: ${JSON.stringify(backlog)}\n\n`)
        sinks.add(res)
        const t = setInterval(() => res.write(`event: state\ndata: ${JSON.stringify(getState())}\n\n`), 500)
        req.on('close', () => { clearInterval(t); sinks.delete(res) })
        return
      }
      if (p === '/cmd' && req.method === 'POST') { const b = await body(); if (!b.text?.trim()) return json({ ok: false }, 400); onCmd(b.text.trim(), b.as); return json({ ok: true }) }
      if (p === '/settings') {
        if (req.method !== 'POST') return json(settings)
        return json({ changed: settings.set(await body()), values: settings.values })
      }
      if (p.startsWith('/icon/')) return json(icon(p.slice(6)))
      if (p.startsWith('/skin/')) return json({ path: 'textures/entity/player/wide/steve.png', slim: false })  // 오프라인 서버: 기본 스킨
      if (p.startsWith('/mc/')) {
        const f = path.normalize(path.join(MC, p.slice(4).replace(/^\/*(assets\/minecraft\/)?/, '')))
        if (!f.startsWith(MC) || !existsSync(f)) { res.writeHead(404); return res.end() }
        res.writeHead(200, { 'content-type': f.endsWith('.png') ? 'image/png' : 'application/json', 'cache-control': 'public, max-age=86400' })
        return res.end(readFileSync(f))
      }
      if (p.startsWith('/viewer') && hook.viewer) return hook.viewer(req, res)
      if (p.startsWith('/viewer')) {  // 스폰 전
        res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' })
        return res.end('<body style="margin:0;background:#000;color:#8794a6;display:grid;place-items:center;height:100vh;font:14px sans-serif">봇 접속 대기중</body>')
      }
      res.writeHead(404); res.end()
    } catch (e: any) { if (!res.headersSent) json({ error: e.message }, 500); else res.end() }
  }
  return ports.map(p => createServer(h).listen(p, '0.0.0.0'))
}
