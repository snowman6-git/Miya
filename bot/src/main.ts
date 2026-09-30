// Miya 봇: 판단은 전부 서빙(model/serve.py), 여기선 상태 수집 + 원시 행동 실행만
import mineflayer, { Bot } from 'mineflayer'
import { pathfinder, Movements, goals } from 'mineflayer-pathfinder'
import { Vec3 } from 'vec3'
import { serveWeb, emit, hook } from './web'
import { viewer } from './viewer'
import { S, settings } from './settings'
import { readFileSync, statSync } from 'node:fs'
import path from 'node:path'

import { NAME, API, WEB, conn } from './cfg'  // WEB 8090=스펙·vite 프록시, 8091=Tauri 앱 기본 직결
const LOG = process.env.LOG === '1'

type Step = { type: string, target: string, cnt: number, tool?: string | null, item?: string, src?: string, fuel?: string, any?: boolean, y?: number, for?: Record<string, number> }  // for=이 스텝을 요구한 상위템·개수(planner)  // y=채광 목표높이(서빙 ore_gen)  // any=종 무관 원목/판자
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
const log = (...a: any[]) => console.log(new Date().toISOString().slice(11, 19), ...a)

const calls: [number, number][] = []  // [시각, ms] webui miya 지표용
let apiOk = true
async function api(path: string, body: any): Promise<any> {
  const t0 = Date.now()
  try {
    const r = await fetch(API + path, { method: 'POST', body: JSON.stringify(body) })
    const j = await r.json()
    if (j.error) throw new Error(path + ' ' + j.error)
    apiOk = true
    return j
  } catch (e) { apiOk = false; throw e } finally { calls.push([t0, Date.now() - t0]); if (calls.length > 200) calls.shift() }
}

const bot: Bot = mineflayer.createBot(conn(NAME))
bot.loadPlugin(pathfinder)
// mineflayer stateId 전역 1개 → Paper가 창 열린 중에도 인벤(0) set_slot 보냄 → 제작대 클릭에 인벤 stateId 실림 → 클릭 무시·재료 누락(craft_unsynced)
// 창별 stateId 추적해 window_click 보정 (-1 = syncWindow 의도적 값 유지)
// mineflayer 버그: 아무 엔티티(오징어·물고기)의 air_supply 도 bot.oxygenLevel 에 씀 → 자기 엔티티것만 반영
let air = 20
bot._client.on('entity_metadata', (d: any) => {
  if (d.entityId !== bot.entity?.id) return
  const k = (bot.registry as any).entitiesByName.player?.metadataKeys?.indexOf('air_supply') ?? 1
  const m = d.metadata.find((x: any) => x.key === k)
  if (m) air = Math.round(m.value / 15)
})
bot.on('spawn', () => { air = 20 })  // 익사 후 리스폰시 서버가 air 메타 재전송 안함 → -1 고착(물 위로 올라가기 오판·이동 방해)
const sid = new Map<number, number>()
let lastWin = 0  // 마지막 창 패킷 시각 → settle()
bot._client.on('window_items', (d: any) => { sid.set(d.windowId, d.stateId); lastWin = Date.now() })
bot._client.on('set_slot', (d: any) => { if (d.windowId >= 0) sid.set(d.windowId, d.stateId); lastWin = Date.now() })
const w0 = bot._client.write.bind(bot._client)
;(bot._client as any).write = (n: string, d: any) => w0(n, n === 'window_click' && d.stateId !== -1 && sid.has(d.windowId) ? { ...d, stateId: sid.get(d.windowId) } : d)
let mc: any

// ---- 상태 ----
let task: string | null = null, paused: { req: string, goal: string, cnt: number, ko?: string, type?: string, n?: number, noask?: boolean, base?: number, set?: string[] } | null = null
let botq: string | null = null
let askFor: { req: string, goal: string, n: number, ko: string, type?: string } | null = null  // goal.ask 대기중 GOAL → 답(혼자해/도와줄게·재명령)시 ask 빼고 재계획
let askQ: string | null = null  // ask.which/count 대기중 원요청 → 답을 앞에 붙여 재해석 (ponytail: hist 답변 학습 전 임시, 0.3 패치 데이터로 대체)
let job = 0  // 멈춤시 증가 → 진행중 작업 중단
let cur: { req: string, goal: string, cnt: number, ko: string, type?: string, noask?: boolean, base?: number, set?: string[] } | null = null  // 진행중 GOAL. base=시작 보유량, set=목표 아이템 묶음 → 재개·재계획시 남은 수량만
const placed: Record<string, Vec3> = {}
let own: { kind: string, x: number, y: number, z: number }[] = []  // 내가 설치한 블럭 → 남의 상자와 구분
let plan: { title: string, steps: { ko: string, state: 'done' | 'doing' | 'fail' | 'todo', why?: string, for?: string }[] } | null = null
const chat: { who: string, text: string, at: number }[] = []
const WOOD = ['oak', 'spruce', 'birch', 'jungle', 'acacia', 'cherry', 'dark_oak', 'pale_oak', 'mangrove', 'crimson', 'warped']
const LOGS = WOOD.map(w => /crimson|warped/.test(w) ? w + '_stem' : w + '_log'), PLANKS = WOOD.map(w => w + '_planks')
const fam = (n: string, any?: boolean) => any && n === 'oak_log' ? LOGS : any && n === 'oak_planks' ? PLANKS : [n]  // 종 무관 목재 묶음
const cntF = (ns: string[]) => { const i = inv(); return ns.reduce((a, n) => a + (i[n] ?? 0), 0) }
const NEAR = [...LOGS, 'stone', 'coal_ore', 'iron_ore', 'copper_ore', 'gold_ore', 'diamond_ore', 'sand', 'gravel', 'dirt', 'lava', 'water']

const inv = () => { const o: Record<string, number> = {}; for (const i of bot.inventory.items()) o[i.name] = (o[i.name] ?? 0) + i.count; return o }
const cnt = (n: string) => inv()[n] ?? 0
const night = () => { const t = bot.time.timeOfDay; return t > 13000 && t < 23000 }
const dist = (p: Vec3) => Math.round(bot.entity.position.distanceTo(p))
const same = (a: { x: number, y: number, z: number }, b: { x: number, y: number, z: number }) => a.x === b.x && a.y === b.y && a.z === b.z
function forget(k: string, p: Vec3) {  // 설치물 사라짐(타인 파괴 등) → 기억·DB에서 삭제
  log('FORGET', k, p)
  if (placed[k] && same(placed[k], p)) delete placed[k]
  own = own.filter(o => !same(o, p)); api('/placed', { del: { x: p.x, y: p.y, z: p.z } }).catch(() => { })
}
function placedDist() {  // 종류별 가장 가까운 내 설치물, 청크 안 로드(먼곳)면 거리만 → 갈지 새로 만들지는 모델(plan)
  const o: Record<string, number> = {}
  for (const w of own) {
    const p = new Vec3(w.x, w.y, w.z), b = bot.blockAt(p)
    if (b && b.name !== w.kind) { forget(w.kind, p); continue }
    if (!(w.kind in o) || dist(p) < o[w.kind]) { placed[w.kind] = p; o[w.kind] = dist(p) }
  }
  for (const [k, p] of Object.entries(placed)) {
    if (k.includes(':') || k in o) continue  // place:death 등 장소
    const b = bot.blockAt(p)
    if (b && b.name !== k) { delete placed[k]; continue }  // 부서짐/회수
    o[k] = dist(p)
  }
  for (const k of ['crafting_table', 'furnace', 'chest']) if (!(k in o)) { const b = findBlock([k], 32); if (b) { placed[k] = b.position; o[k] = dist(b.position) } }
  return o
}
function state() {
  return { hp: Math.round(bot.health), food: bot.food, night: night(), inv: inv(), placed: placedDist(), task, paused: paused ? paused.req : null, botq }
}
// QED 변수: 같은 방법도 도구 티어·장비·시간따라 결과 다름
const TIER = ['wooden', 'stone', 'golden', 'iron', 'diamond', 'netherite']
// 방어점수 = 착용칸(5~8) 재질·부위 합 (armor 속성 키가 버전마다 달라 0으로 읽힘)
const APT: Record<string, number[]> = { leather: [1, 3, 2, 1], golden: [2, 5, 3, 1], chainmail: [2, 5, 4, 1], iron: [2, 6, 5, 2], diamond: [3, 8, 6, 3], netherite: [3, 8, 6, 3], turtle: [2, 0, 0, 0] }
const armorPts = () => bot.inventory.slots.slice(5, 9).reduce((a, it, k) => a + (it ? APT[it.name.split('_')[0]]?.[k] ?? 0 : 0), 0)
function vars() {
  const tools: Record<string, string> = {}
  for (const i of bot.inventory.items()) {
    const [t, k] = i.name.split('_'); if (!['pickaxe', 'axe', 'shovel', 'sword', 'hoe'].includes(k)) continue
    if (TIER.indexOf(t) > TIER.indexOf(tools[k] ?? '')) tools[k] = t
  }
  const p = bot.entity.position
  return { tools, armor: armorPts(), hp: Math.round(bot.health), food: bot.food,
    night: night(), held: bot.heldItem?.name ?? null, dim: bot.game.dimension, pos: [Math.round(p.x), Math.round(p.y), Math.round(p.z)] }
}
let nearIds: Map<number, string> | null = null
function nearMap() {  // 1회 스캔으로 종류별 최근접 (종류마다 findBlock 23회 → 1회)
  nearIds ??= new Map(NEAR.flatMap(n => [mc.blocksByName[n], mc.blocksByName['deepslate_' + n]].filter(Boolean).map((b: any) => [b.id, n] as [number, string])))
  const o: Record<string, number> = {}
  for (const p of bot.findBlocks({ matching: [...nearIds.keys()], maxDistance: 48, count: 4096 })) {
    const n = nearIds.get(bot.blockAt(p)!.type)!, d = dist(p)
    if (!(n in o) || d < o[n]) o[n] = d
  }
  return o
}
const bad = new Set<string>()  // 도달 실패 좌표 제외
function findBlock(names: string[], d = S.scan_r, reach = false) {
  const ids = names.flatMap(n => [mc.blocksByName[n]?.id, mc.blocksByName['deepslate_' + n]?.id]).filter(x => x !== undefined)
  if (!ids.length) return null
  if (!reach) return bot.findBlock({ matching: ids, maxDistance: d })
  // 채집용: 높이차 벌점(나무 꼭대기 회피) + 실패좌표 제외
  const me = bot.entity.position
  const ps = bot.findBlocks({ matching: ids, maxDistance: d, count: 64 }).filter(p => !bad.has(p.toString()))
  ps.sort((a, b) => a.distanceTo(me) + Math.abs(a.y - me.y) * 3 - b.distanceTo(me) - Math.abs(b.y - me.y) * 3)
  return ps.length ? bot.blockAt(ps[0]) : null
}
let lastSay = '', prevUser: [string, number] | null = null  // 직전대화: 생략 발화(구워, 줘) 해석은 모델이
const say = (m: string) => { if (S.talk) bot.chat(m); log('>>', m); emit({ type: 'say', text: m }); lastSay = m }
// 대답 문구: bot/replies.json (키=상황.TASK_TYPE → 없으면 상황 기본키, 배열이면 랜덤). mtime 바뀌면 다시 읽음 → 재시작 없이 수정
const RF = path.resolve(__dirname, '../replies.json')
let rp: Record<string, string | string[]> = {}, rpT = 0
function T(key: string, v: Record<string, any> = {}) {
  try { const m = statSync(RF).mtimeMs; if (m !== rpT) { rp = JSON.parse(readFileSync(RF, 'utf8')); rpT = m } } catch (e: any) { log('replies', e.message) }
  const a = rp[key] ?? rp[key.split('.')[0]] ?? key
  const t = Array.isArray(a) ? a[Math.floor(Math.random() * a.length)] : a
  return t.replace(/\{(\w+)\}(은|는|이|가|을|를)?/g, (_, k, j) => { const w = String(v[k] ?? ''); return w + (j ? josa(w, j) : '') })
}
// 조사 받침 맞춤 (철셋는 → 철셋은). 한글 아니면 템플릿 그대로
function josa(w: string, j: string) {
  const c = w.charCodeAt(w.length - 1) - 0xAC00
  if (c < 0 || c > 11171) return j
  const p = ({ 은: '는', 는: '는', 이: '가', 가: '가', 을: '를', 를: '를' } as any)[j]
  return c % 28 ? ({ 는: '은', 가: '이', 를: '을' } as any)[p] : p
}
const timeout = <T>(p: Promise<T>, ms: number) => Promise.race([p, sleep(ms).then(() => { throw new Error('timeout') })]) as Promise<T>
async function go(goal: any, ms = 60000) {  // stuck 1회 → 막는 블럭 캐고 재시도, 2회째 실패
  const end = Date.now() + ms
  try { return await go1(goal, ms) } catch (e: any) {
    if (!(e instanceof Fail) || e.message !== 'stuck' || !(await unstick())) throw e
  }
  return go1(goal, Math.max(1000, end - Date.now()))
}
// 머리위(점프 막힘 → Paper moved wrongly 롤백 루프)·앞(발/머리/머리위) 고체 블럭 캐기. 컨테이너·액체 인접은 제외
async function unstick() {
  if (!S.dig_path) return false
  const p = bot.entity.position.floored(), dx = Math.round(-Math.sin(bot.entity.yaw)), dz = Math.round(-Math.cos(bot.entity.yaw))
  const bs = [[0, 2, 0], [dx, 2, dz], [dx, 1, dz], [dx, 0, dz]].map(o => bot.blockAt(p.offset(o[0], o[1], o[2])))
    .filter((b: any) => b && b.boundingBox === 'block' && b.diggable && !/chest|barrel|shulker|furnace|smoker|crafting|bed|bedrock|spawner/.test(b.name)
      && !/lava|water/.test(bot.blockAt(b.position.offset(0, 1, 0))?.name ?? ''))
  if (!bs.length) return false
  bot.pathfinder.setGoal(null)
  for (const b of bs as any[]) {
    log('UNSTICK', b.name, b.position.toString())
    const t = bot.pathfinder.bestHarvestTool(b)
    if (t) await bot.equip(t, 'hand').catch(() => { })
    await timeout(bot.dig(b), 20000).catch((e: any) => { log('unstick', e.message); bot.stopDigging() })
  }
  return true
}
async function go1(goal: any, ms: number) {  // 제자리 12초(맨손 돌캐기 7.5초보다 길게, 서버 moved wrongly 롤백 반복 등) → stuck
  let last = bot.entity.position.clone(), at = Date.now()
  const w = setInterval(() => { if (bot.entity.position.distanceTo(last) > 1) { last = bot.entity.position.clone(); at = Date.now() } }, 500)
  let c: any
  const still = new Promise<never>((_, j) => { c = setInterval(() => { if (Date.now() - at > 12000) j(new Fail('stuck')) }, 1000) })
  try { await timeout(Promise.race([bot.pathfinder.goto(goal), still]), ms) } finally { clearInterval(w); clearInterval(c); if (bot.pathfinder.goal === goal) bot.pathfinder.setGoal(null) }  // 새 goal(다음 도망 등) 지우지 않음
}
// 수면 탈출: 머리 위 막힘(수중 채굴·동굴)이면 점프만으론 못나옴. pathfinder는 물속 경로 못찾음
// → 물·빈칸 BFS로 머리가 공기인 가장 가까운 칸 경로 → 직접 조향(바라보고 전진+점프=수영)
async function surface() {
  bot.pathfinder.setGoal(null)
  const open = (v: any) => bot.blockAt(v)?.boundingBox === 'empty', key = (v: any) => v.toString()
  const s0 = bot.entity.position.floored(), prev = new Map<string, any>([[key(s0), null]]), q = [s0]
  let end: any = null
  for (let n = 0; q.length && n < 2000 && !end; n++) {
    const c = q.shift()
    for (const d of [[0, 1, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1], [0, -1, 0]]) {
      const v = c.offset(d[0], d[1], d[2])
      if (prev.has(key(v)) || !open(v) || v.distanceTo(s0) > 16) continue
      prev.set(key(v), c); q.push(v)
      const h = bot.blockAt(v.offset(0, 1, 0))
      if (h?.boundingBox === 'empty' && h.name !== 'water' && !(h.getProperties?.() as any)?.waterlogged) { end = v; break }
    }
  }
  const path: any[] = []
  for (let v = end; v && key(v) !== key(s0); v = prev.get(key(v))) path.unshift(v)
  log('SURFACE', end ? `${end} ${path.length}칸` : '없음 → 점프')
  bot.setControlState('jump', true)
  for (let t = 0, k = 0; t < 80 && (air < 20 || bot.blockAt(bot.entity.position.offset(0, 1.6, 0))?.name === 'water'); t++) {
    while (k < path.length - 1 && bot.entity.position.xzDistanceTo(path[k].offset(0.5, 0, 0.5)) < 0.6 && path[k].y <= bot.entity.position.y + 1.5) k++  // 물에 뜬 높이·천장 → 수평거리 기준
    const w = path[k]
    if (w) { await bot.lookAt(w.offset(0.5, 0.5, 0.5), true); bot.setControlState('forward', bot.entity.position.xzDistanceTo(w.offset(0.5, 0, 0.5)) > 0.3) }
    await sleep(250)
  }
  bot.clearControlStates()
}
const player = (u: string) => bot.players[u]?.entity

// ---- 원시 행동 ----
class Fail extends Error {}
async function equipName(n?: string | null, dest: any = 'hand') {
  if (!n || n === 'hand') return
  const it = bot.inventory.items().find(i => i.name === n)
  if (it) await bot.equip(it, dest)
}
// 보유 방어구 > 착용중 → 착용 (제작 끝 착용 X: 유저용 제작일수도. 달라하면 벗어서 줌)
const ARM: Record<string, number> = { leather: 1, golden: 2, chainmail: 3, turtle: 3, iron: 4, diamond: 5, netherite: 6 }
const SLOTS = [['helmet', 'head', 5], ['chestplate', 'torso', 6], ['leggings', 'legs', 7], ['boots', 'feet', 8]] as const
const rank = (n?: string) => n ? ARM[n.split('_')[0]] ?? 1 : 0
let wearing = false, wearHold = 0
async function wearBest() {
  if (wearing || Date.now() < wearHold || bot.currentWindow) return
  wearing = true
  try {
    for (const [k, d, i] of SLOTS) {
      const w = bot.inventory.slots[i]?.name, b = bot.inventory.items().filter(x => x.name.endsWith('_' + k)).sort((x, y) => rank(y.name) - rank(x.name))[0]
      if (b && rank(b.name) > rank(w)) { await bot.equip(b, d); log('WEAR', b.name) }
    }
  } catch (x: any) { log('wear', x.message) } finally { wearing = false }
}
async function unwear(n: string) {  // 입은 템 달라/버려 → 벗기 (인벤 없고 착용중일때)
  const s = SLOTS.find(([, , i]) => bot.inventory.slots[i]?.name === n)
  if (s && !cnt(n)) { wearHold = Date.now() + 10000; await bot.unequip(s[1]) }
}
// 원정: 범위내 대상 없으면 48칸씩 이동하며 재탐색 (hops 상한 → 무한탐색 방지). 방향 = 모델(/explore: 8방위 지표 표본 + 방문 기억)
const visited: Vec3[] = []
const SURF: [RegExp, string][] = [[/_log$|_leaves$|_stem$/, '나무'], [/^(grass_block|short_grass|tall_grass|dirt|podzol|fern)$/, '풀'], [/^(sand|red_sand)$/, '모래'], [/^water$/, '물'],
  [/stone|andesite|diorite|granite|gravel|deepslate|tuff|ore$/, '돌']]
function sector(i: number) {  // 북(-z)부터 시계 45°, 거리 12~36 표본 8칸 → 지표 블럭 종류 수 + 방문수
  const a = i * Math.PI / 4, p = bot.entity.position, f: Record<string, number> = {}
  for (const r of [12, 20, 28, 36]) for (const o of [-0.2, 0.2]) {
    const x = Math.floor(p.x + Math.sin(a + o) * r), z = Math.floor(p.z - Math.cos(a + o) * r)
    let k = '미로드'
    for (let y = Math.floor(p.y) + 16; y > p.y - 16; y--) {
      const b = bot.blockAt(new Vec3(x, y, z)); if (!b) break
      if (b.name === 'air' || b.name === 'cave_air' || b.name === 'snow') continue
      k = SURF.find(([re]) => re.test(b.name))?.[1] ?? '돌'; break
    }
    f[k] = (f[k] ?? 0) + 1
  }
  const v = visited.filter(q => { const d = q.minus(p); return Math.hypot(d.x, d.z) > 8 && Math.hypot(d.x, d.z) < 80 && Math.abs(((Math.atan2(d.x, -d.z) - a) % (2 * Math.PI) + 3 * Math.PI) % (2 * Math.PI) - Math.PI) < Math.PI / 8 }).length
  return { f, v }
}
async function explore(found: () => any, id: number, target = '', hops = S.explore_hops) {
  for (let h = 0; h < hops; h++) {
    if (id !== job) throw new Fail('stopped')
    const p = bot.entity.position
    visited.push(p.clone()); if (visited.length > 64) visited.shift()
    const r = await api('/explore', { target, y: Math.floor(p.y), night: night(), hop: h + 1, dirs: [0, 1, 2, 3, 4, 5, 6, 7].map(sector) }).catch(() => null)
    const a = r ? r.i * Math.PI / 4 : Math.random() * Math.PI * 2
    log('EXPLORE', h + 1, '/', hops, target, r ? `${r.dir} ${r.p}` : '랜덤(api 실패)')
    try { await go(new goals.GoalXZ(Math.round(p.x + Math.sin(a) * S.explore_dist), Math.round(p.z - Math.cos(a) * S.explore_dist)), 60000) } catch { }
    if (found()) return true
  }
  return false
}
// 인벤 재동기화: 제작 클릭들의 늦은 응답(커서에 재료 든 상태)이 sync 응답보다 먼저 와서 인벤 비어보임 → 창 패킷 잠잠해질때까지 반복
async function settle() {
  for (let k = 0; k < 5; k++) {
    await timeout((bot as any)._syncWindow(bot.inventory), 3000).catch(() => { })
    const t = Date.now(); await sleep(200)
    if (lastWin < t) return
  }
}
async function station(k: string) {  // 가까운것 우선, 없으면 기억된 곳(plan이 reuse 고름)으로 가서 확인
  const nb = findBlock([k], 48)
  const p = placed[k]
  if (!p || (nb && dist(nb.position) <= dist(p))) return nb
  if (!bot.blockAt(p)) await go(new goals.GoalNear(p.x, p.y, p.z, 3)).catch(() => { })
  const b = bot.blockAt(p)
  if (b?.name === k) return b
  if (b) forget(k, p)  // 가보니 없음
  return findBlock([k], 48)
}
const findMob = (mob: string) => bot.nearestEntity(e => e.name === mob && dist(e.position) < 48)
async function gather(s: Step, id: number) {
  const item = s.item ?? s.target, its = fam(item, s.any), bs = fam(s.target, s.any), want = cntF(its) + s.cnt
  let tries = 0, descended = false
  while (cntF(its) < want) {
    if (id !== job) throw new Fail('stopped')
    if (++tries > s.cnt * 4 + 10) throw new Fail('stuck')
    const b = findBlock(bs, S.scan_r, true)
    if (!b && S.mine_mode === 'stair' && !descended && s.y !== undefined && bot.entity.position.y > s.y + 4) { descended = true; await stair(s.y, id); continue }
    if (!b) { if (await explore(() => findBlock(bs, S.scan_r, true), id, s.target)) continue; throw new Fail('no_target') }
    if (s.tool && s.tool !== 'hand' && !bot.inventory.items().some(i => i.name === s.tool)) throw new Fail('no_tool')  // 도구 파손 → 맨손 채굴(드랍0) 방지, 재계획
    await equipName(s.tool)
    try { await go(new goals.GoalLookAtBlock(b.position, bot.world), 60000) } catch (e: any) {  // LookAt = 실월드 시야 판정 → 묻힌 블럭(흙 밑 돌)은 항상 No path → 인접 이동(파고 들어감)
      try { if (!/No path/.test(e.message)) throw e; await go(new goals.GoalGetToBlock(b.position.x, b.position.y, b.position.z), 60000) } catch (e2: any) { if (LOG) log('go', e2.message); bad.add(b.position.toString()); continue }
    }
    const bb = bot.blockAt(b.position)
    if (!bb || bb.name === 'air') continue
    await equipName(s.tool)
    try { await timeout(bot.dig(bb), 40000) } catch (e: any) { if (LOG) log('dig', e.message); bad.add(b.position.toString()); bot.stopDigging(); continue }
    try { await go(new goals.GoalBlock(b.position.x, b.position.y, b.position.z), 5000) } catch { }
    await sleep(250)
    if (LOG) log('got', item, cntF(its), '/', want)
  }
}
// 계단굴: 바라보는 방향(4방위)으로 1칸 전진·1칸 하강 반복, 폭 stair_w·높이 stair_h 로 파냄. 용암·물 만나면 중단, 바닥 없으면 막기
async function stair(toY: number, id: number) {
  const yaw = bot.entity.yaw, dx = Math.round(-Math.sin(yaw)), dz = dx ? 0 : Math.round(-Math.cos(yaw)) || 1
  const w = S.stair_w === '3' ? [-1, 0, 1] : [0], filler = () => bot.inventory.items().find(i => /^(cobblestone|cobbled_deepslate|dirt|stone|netherrack)$/.test(i.name))
  const pick = () => ['wooden', 'stone', 'golden', 'iron', 'diamond', 'netherite'].map(t => bot.inventory.items().find(i => i.name === t + '_pickaxe')).find(Boolean)  // 싼 곡괭이부터 소모(목표용 도구 보존)
  log('STAIR', 'to y', toY, 'dir', dx, dz)
  for (let n = 0; bot.entity.position.y > toY && n < 200; n++) {
    if (id !== job) throw new Fail('stopped')
    const nx = bot.entity.position.floored().offset(dx, -1, dz)
    for (const k of w) for (let h = S.stair_h - 1; h >= 0; h--) {  // 위부터 파야 모래·자갈 덜 막힘
      const q = nx.offset(k * dz, h, k * dx), b = bot.blockAt(q)
      if (!b) throw new Fail('stuck')
      for (const o of [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, -1]]) if (/lava|water/.test(bot.blockAt(q.offset(o[0], o[1], o[2]))?.name ?? '')) throw new Fail('liquid')
      if (b.boundingBox === 'block') { const t = pick(); if (!t) throw new Fail('no_tool'); await bot.equip(t, 'hand'); await timeout(bot.dig(b), 20000) }
    }
    const fl = bot.blockAt(nx.offset(0, -1, 0))
    if (fl && fl.boundingBox !== 'block') { const f = filler(); if (!f) throw new Fail('no_floor'); await bot.equip(f, 'hand'); await bot.placeBlock(bot.blockAt(nx.offset(-dx, -1, -dz))!, new Vec3(dx, 0, dz)).catch(() => { }) }
    await go(new goals.GoalBlock(nx.x, nx.y, nx.z), 8000)
  }
}
const DUR = () => Object.fromEntries(bot.inventory.items().filter(i => i.maxDurability).map(i => [i.name, Math.round(100 * (1 - (i.durabilityUsed ?? 0) / i.maxDurability))]))
async function arm(e: any, n = 1) {  // 무기·방패 선택 = 모델(/weapon: 처치시간·내구도·원거리·크리퍼)
  const r = await api('/weapon', { inv: inv(), dur: DUR(), mob: e.name, d: dist(e.position), n, hp: Math.round(bot.health), armor: armorPts() }).catch(() => null)
  if (!r) return
  log('WEAPON', e.name, r.item, r.shield ? '+방패' : '', r.p)
  if (r.item !== 'hand') await equipName(r.item)
  if (r.shield) await equipName('shield', 'off-hand')
}
async function hunt(s: Step, id: number) {
  const mob = s.target.replace('mob:', '')
  for (let k = 0; k < s.cnt; k++) {
    const e = findMob(mob) ?? (await explore(() => findMob(mob), id, s.target) ? findMob(mob) : null)
    if (!e) throw new Fail('no_target')
    if (s.type === 'combat') await arm(e); else await equipName(s.tool)
    const t0 = Date.now()
    while (e.isValid && Date.now() - t0 < 60000) {
      if (id !== job) throw new Fail('stopped')
      if (dist(e.position) > 3) bot.pathfinder.setGoal(new goals.GoalFollow(e, 1), true)
      else { bot.pathfinder.setGoal(null); await bot.lookAt(e.position.offset(0, e.height / 2, 0)); bot.attack(e) }
      await sleep(600)
    }
    bot.pathfinder.setGoal(null)
    if (e.isValid) throw new Fail('stuck')
    try { await go(new goals.GoalBlock(Math.floor(e.position.x), Math.floor(e.position.y), Math.floor(e.position.z)), 5000) } catch { }
  }
}
async function craft(s: Step) {
  if (s.any && s.target === 'oak_planks') {  // 가진 원목 종 판자로
    const i = inv(), k = LOGS.reduce((a, l) => (i[l] ?? 0) > (i[a] ?? 0) ? l : a, LOGS[0])
    s = { ...s, target: PLANKS[LOGS.indexOf(k)] }
  }
  const it = mc.itemsByName[s.target]
  let table: any = null
  let rs = bot.recipesFor(it.id, null, 1, null)
  if (!rs.length) {
    table = await station('crafting_table')
    if (!table) throw new Fail('no_table')
    await go(new goals.GoalNear(table.position.x, table.position.y, table.position.z, 3))
    rs = bot.recipesFor(it.id, null, 1, table)
  }
  if (!rs.length) throw new Fail('no_material')
  const want = cnt(s.target) + s.cnt
  // 1회씩 제작 + 매회 재동기화: mineflayer 다회 제작은 낙관적 슬롯상태 재사용 → Paper에서 어긋남
  for (let a = 0; cnt(s.target) < want; ) {
    if (bot.currentWindow) bot.closeWindow(bot.currentWindow)
    await settle()
    rs = bot.recipesFor(it.id, null, 1, table)
    if (!rs.length) { log('nomat', s.target, JSON.stringify(inv()), !!table); throw new Fail('no_material') }
    const h = cnt(s.target)
    try { await timeout(bot.craft(rs[0], 1, table ?? undefined), 8000) } catch (e: any) {
      log('craft', e.message)
      bot._client.write('close_window', { windowId: 0 })  // 2x2 제작칸 잔여물 인벤으로 회수
    }
    for (let t = 0; t < 20 && cnt(s.target) <= h; t++) await sleep(100)
    if (cnt(s.target) <= h && ++a > 2) throw new Fail('craft_desync')
  }
  for (let t = 0; t < 50 && cnt(s.target) < want; t++) await sleep(100)  // 인벤 동기화 대기
  if (cnt(s.target) < want) throw new Fail('craft_unsynced')
}
async function place(name: string) {
  const it = bot.inventory.items().find(i => i.name === name)
  if (!it) throw new Fail('no_material')
  const p = bot.entity.position.floored()
  for (const [dx, dy, dz] of [0, 1, -1].flatMap(dy => [[1, 0], [0, 1], [-1, 0], [0, -1], [1, 1], [-1, 1], [1, -1], [-1, -1], [2, 0], [0, 2], [-2, 0], [0, -2]].map(([x, z]) => [x, dy, z]))) {
    const at = p.offset(dx, dy, dz), below = bot.blockAt(at.offset(0, -1, 0)), cur = bot.blockAt(at)
    if (!cur || cur.boundingBox !== 'empty' || /water|lava/.test(cur.name) || !below || below.boundingBox !== 'block') continue
    await bot.equip(it, 'hand')
    try {
      if (cur.name !== 'air') await bot.dig(cur)  // 풀 등 치우기
      await bot.placeBlock(below, new Vec3(0, 1, 0))
    } catch (e: any) { if (LOG) log('place', e.message.slice(0, 80)) }  // 서버 거부(엔티티 겹침 등)
    await sleep(300)
    if (bot.blockAt(at)?.name !== name) continue  // 실제 설치 안됨 → 다음 자리
    placed[name] = at
    own = (await api('/placed', { add: { kind: name, x: at.x, y: at.y, z: at.z } }).catch(() => ({ list: own }))).list
    return
  }
  throw new Fail('no_space')
}
const FUEL: Record<string, number> = { coal: 8, charcoal: 8, lava_bucket: 100 }
async function smelt(s: Step, id: number) {
  const fb = await station('furnace')
  if (!fb) throw new Fail('no_furnace')
  await go(new goals.GoalNear(fb.position.x, fb.position.y, fb.position.z, 3))
  const f = await bot.openFurnace(fb)
  try {
    const fs = fam(s.fuel ?? 'coal', s.any), fuel = fs.find(n => cnt(n) > 0) ?? fs[0], src = s.src!
    if (!f.fuelItem()) await f.putFuel(mc.itemsByName[fuel].id, null, Math.max(1, Math.ceil(s.cnt / (FUEL[fuel] ?? 1.5))))
    await f.putInput(mc.itemsByName[src].id, null, s.cnt)
    const t0 = Date.now()
    while ((f.outputItem()?.count ?? 0) < s.cnt) {
      if (id !== job) throw new Fail('stopped')
      if (Date.now() - t0 > s.cnt * 10000 + 20000) throw new Fail('slow')
      if (!f.inputItem() && !f.outputItem()) throw new Fail('taken')  // 누가 빼감
      await sleep(1000)
    }
    await f.takeOutput()
  } finally { f.close() }
}
async function exec(s: Step, id: number) {
  switch (s.type) {
    case 'mine': case 'log': case 'dig': return gather(s, id)
    case 'hunt': case 'combat': return hunt(s, id)
    case 'craft': return craft(s)
    case 'place': return place(s.target)
    case 'furnace': return smelt(s, id)
    case 'expedition': {
      const f = s.target.startsWith('mob:') ? () => findMob(s.target.slice(4)) : () => findBlock(fam(s.target, s.any), 64)
      if (f() || await explore(f, id, s.target)) return
      throw new Fail('no_target')
    }
    default: throw new Fail('unsupported:' + s.type)
  }
}

// ---- 인벤 정리: 아이템별 유지/버리기/상자 보관은 모델(/tidy), 봇은 실행만 ----
function myChest() {
  const cs = own.filter(o => o.kind === 'chest').map(o => new Vec3(o.x, o.y, o.z))
  for (const c of cs) { const b = bot.blockAt(c); if (b && b.name !== 'chest') forget('chest', c) }
  return cs.filter(c => bot.blockAt(c)?.name === 'chest').sort((a, b) => dist(a) - dist(b))[0] ?? null
}
async function tidy(sit: string, goal?: string, n?: number) {
  const ch = myChest()
  const r = await api('/tidy', { inv: inv(), goal, cnt: n, free: bot.inventory.emptySlotCount(), chest_d: ch ? dist(ch) : null, sit })
  log('TIDY', sit, JSON.stringify(r.acts))
  const drop = r.acts.filter((a: any) => a.act === '버리기'), store = r.acts.filter((a: any) => a.act === '상자에 보관')
  for (const a of drop) await bot.toss(mc.itemsByName[a.item].id, null, cnt(a.item)).catch((e: any) => log('toss', e.message))
  if (store.length && ch) {
    try {
      await go(new goals.GoalNear(ch.x, ch.y, ch.z, 2), 60000)
      const c = await bot.openContainer(bot.blockAt(ch)!)
      for (const a of store) await c.deposit(mc.itemsByName[a.item].id, null, cnt(a.item)).catch((e: any) => log('deposit', e.message))
      c.close()
    } catch (e: any) { log('tidy', e.message) }
  }
  if (drop.length || store.length) say(T('done.tidy', { drop: drop.map((a: any) => a.ko).join(', ') || '-', store: store.map((a: any) => a.ko).join(', ') || '-' }))
}

// ---- GOAL 실행 + QED 기록 ----
// 끝난 plan 5초 표시후 비움 → 웹UI 유휴 전환 (그사이 새 job 시작시 유지)
const endPlan = (id: number) => setTimeout(() => { if (id === job && !task) plan = null }, 5000)
async function runGoal(req: string, goal: string, n: number, koName: string, type?: string, noask = false, from?: { base?: number, set?: string[] }) {
  const id = ++job
  cur = { req, goal, cnt: n, ko: koName, type, noask, base: from?.base, set: from?.set }
  const TRIES = 8  // 안전 상한(모델 /fail 이 보통 먼저 도움요청·포기)
  let prevVia: string | null = null, lastF = '', streak = 0, dec = 'replan'  // dec: 실패 대응 = 모델(/fail)  // 재계획시 이전 방법 → webui TASK 교체 표시
  for (let attempt = 0; attempt < TRIES; attempt++) {  // 실패시 재계획 (QED 최근실패 반영), 상한 → 무한루프 차단
    if (id !== job) return  // 다른 명령이 선점
    own = (await api('/placed', {}).catch(() => ({ list: own }))).list  // 외부 삭제 반영
    const st = state()
    const left = cur.set ? cur.base! + n - cntF(cur.set) : n  // 멈춤·실패 전 모은 분 제외 ("n개 더" 중복 방지)
    if (left <= 0) { cur = null; endPlan(id); say(T('done.' + type, { ko: koName, n })); return }
    const p = await api('/plan', { goal, type, cnt: left, inv: st.inv, placed: st.placed, near: nearMap(), hp: st.hp, night: st.night, armor: bot.inventory.slots.slice(5, 9).some(Boolean), req, y: Math.floor(bot.entity.position.y), noask })
    if (p.via === 'ask') { say(T('goal.ask', { ko: koName })); botq = `${koName} 도움`; askFor = { req, goal, n, ko: koName, type }; return }  // ask도 steps 비어있음 → 먼저
    if (!p.steps.length) { say(T('goal.unknown', { ko: koName })); botq = `${koName} 방법`; return }
    if (!cur.set && p.goal_set) { cur.set = (p.goal_set as string[]).flatMap(g => fam(g, p.steps.some((s: Step) => s.any))); cur.base = cntF(cur.set) }
    if (p.qed) log('QED', p.qed.changed ? `바꿈 ${p.qed.base_ko} → ${p.via_ko}` : '참고', JSON.stringify(p.qed.ev))
    log('PLAN', p.via, p.steps.map((s: Step) => `${s.type}:${s.target}x${s.cnt}`).join(' → '))
    if (attempt === 0) say([T('start.' + type, { ko: koName, n, steps: p.steps.length }), ...(p.why ?? []).map((w: any) => T('why.' + w.k, w))].join(' '))  // 방법 사유(설치물 재사용·경유·QED) 같이
    if (attempt === 0 && S.tidy_before) await tidy('작업 전', goal, n)  // 작업 필요칸 vs 빈칸 판단은 모델(/tidy)
    emit({ type: 'decision', text: `"${req}" → ${koName} ${n}개 [${p.via_ko}] ${p.steps.length}단계`, qed: p.qed && { ...p.qed, base: p.qed.base_ko, base_id: p.qed.base }, goal: koName, via: p.via_ko, via_id: p.via, attempt, prev: prevVia, steps: p.steps.map((x: Step) => `${x.type}:${x.target}x${x.cnt}`),
      why: p.why, detail: p.detail, alts: p.opts.map((o: string, i: number) => ({ opt: o, p: +p.p[i].toFixed(3), pick: i === p.pick })).sort((a: any, b: any) => b.p - a.p).slice(0, 3) }); prevVia = p.via_ko  // 표시용 한글, 원 id는 *_id
    const kn = await kos((p.steps as Step[]).flatMap(s => [s.target, ...Object.keys(s.for ?? {})]))
    const forKo = (f?: Record<string, number>) => f && Object.entries(f).map(([k, c]) => k === 'goal' ? `목표 ${c}` : `${kn[k] ?? k} ${c}`).join(', ')
    plan = { title: `${koName} ${n}개`, steps: (p.steps as Step[]).map(s => ({ ko: `${s.type} ${kn[s.target] ?? s.target} ×${s.cnt}`, state: 'todo' as const, for: forKo(s.for) })) }
    const rec: any[] = [], t0 = Date.now(), v0 = vars()
    let fail: string | null = null
    for (const [i, s] of (p.steps as Step[]).entries()) {
      if (id !== job || !plan) { fail = 'stopped'; break }  // 선점: 전역 plan은 새 작업 것 → 건드리지 않음
      task = `${koName} ${n}개 (${i + 1}/${p.steps.length})`
      plan.steps[i].state = 'doing'
      const t1 = Date.now()
      for (let k = 0; ; k++) {  // 일시적 실패(타임아웃·동기화·서버거부)는 같은 스텝 재시도
        fail = null
        if (id !== job) { fail = 'stopped'; break }
        try { await exec(s, id) } catch (e: any) { fail = e instanceof Fail ? e.message : 'err:' + String(e.message ?? e).slice(0, 60) }
        if (!fail || fail === 'stopped' || id !== job || k >= 6) break
        streak = fail === lastF ? streak + 1 : 1; lastF = fail
        const r = await api('/fail', { goal, step: { type: s.type, target: s.target }, reason: fail, tries: k + 1, replans: attempt, streak, hp: Math.round(bot.health), night: night(), player: Object.keys(bot.players).length > 1 })
          .catch(() => ({ act: k < 2 && /^(err:|craft_|stuck|slow|no_space)/.test(fail!) ? 'retry' : 'replan', label: 'api 실패 규칙' }))
        dec = r.act
        log('FAIL', s.type, s.target, fail, `시도${k + 1} 재계획${attempt} 연속${streak}`, '→', r.label, r.p ?? '')
        if (dec !== 'retry') break
        await sleep(1000)
      }
      rec.push({ ...s, ms: Date.now() - t1, ok: !fail, fail })
      log('STEP', i + 1, s.type, s.target, s.cnt, fail ?? 'ok', Date.now() - t1, 'ms')
      if (!plan || id !== job) { fail ??= 'stopped'; break }  // 멈춤·선점 → 새 plan 오염 금지(Object.assign null 크래시)
      Object.assign(plan!.steps[i], fail ? { state: 'fail', why: fail } : { state: 'done' })
      emit(fail ? { type: 'step-fail', text: `${plan!.steps[i].ko} 실패(${fail})`, n: i + 1, of: p.steps.length, why: fail } : { type: s.type === 'craft' ? 'crafted' : s.type === 'furnace' ? 'smelted' : 'step', title: plan!.title, n: i + 1, of: p.steps.length, step: plan!.steps[i].ko, for: plan!.steps[i].for })
      if (fail) break
    }
    await api('/qed', { req, goal, cnt: n, via: p.via, ok: !fail, ms: Date.now() - t0, fail, steps: rec, ctx: p.ctx, vars: v0 }).catch(e => log('qed', e.message))
    task = null
    if (!fail) {
      cur = null; endPlan(id); say(T('done.' + type, { ko: koName, n }))
      if ((p.steps as Step[]).some(s => s.type === 'expedition') && myChest()) await tidy('원정 복귀')
      return
    }
    if (fail === 'stopped') { if (cur?.req === req) cur = null; return }
    if (id !== job) return
    if (dec === 'help') { cur = null; endPlan(id); botq = `${koName} 도움`; askFor = { req, goal, n, ko: koName, type }; return say(T('fail.help', { ko: koName, why: fail })) }
    if (dec === 'giveup') break
    say(T('fail.step', { step: rec.at(-1).type, target: rec.at(-1).target, why: fail }) + (attempt < TRIES - 1 ? T('fail.retry') : ''))
  }
  const c0 = cur; cur = null; endPlan(id)
  paused = { req, goal, cnt: n, ko: koName, type, noask, n: (resumes.get(req) ?? 0), base: c0?.base, set: c0?.set }
  botq = `${koName} 실패`
  say(T('fail.giveup', { ko: koName }))
}

// ---- 질문 응답 ----
async function answer(q: string, user: string, t: any) {
  const iv = inv(), ks = Object.keys(iv)
  const ko = await kos(ks)
  const invs = ks.map(k => `${ko[k]} ${iv[k]}`).join(', ') || '비어있음'
  const p = bot.entity.position.floored()
  const g = t.goals[0]
  switch (q) {
    case 'inv': return say(T('answer.inv', { inv: invs }))
    case 'have': return say(g ? T('answer.have', { ko: g.ko, n: cnt(g.item) }) : T('answer.inv', { inv: invs }))
    case 'hp': return say(T('answer.hp', { hp: Math.round(bot.health) }))
    case 'food': return say(T('answer.food', { food: bot.food }))
    case 'pos': return say(T('answer.pos', p))
    case 'doing': case 'progress': return say(task ?? T('answer.idle'))
    case 'time': return say(T(night() ? 'answer.night' : 'answer.day'))
    case 'where_thing': {
      const w = g ?? t.spans.find((s: any) => s.label === '장소' && s.item), k = w?.item, b = k && (placed[k] ?? findBlock([k], 64)?.position)
      return say(b ? T('answer.where_thing', { ko: w.ko, x: b.x, y: b.y, z: b.z, d: dist(b) }) : w ? T('answer.where_none', { ko: w.ko }) : T('answer.unknown_thing'))
    }
    case 'where_player': { const e = player(user); return say(e ? T('answer.where_player', { d: dist(e.position) }) : T('answer.not_seen')) }
    case 'near': { const nm = nearMap(); const k2 = Object.keys(nm); const kk = await kos(k2); const near = k2.map(k => `${kk[k]} ${nm[k]}칸`).join(', '); return say(near ? T('answer.near', { near }) : T('answer.near_none')) }
    case 'recipe': case 'can_make': case 'can_do': {
      if (!g) return say(T('answer.unknown_thing'))
      const st = state(), pl = await api('/plan', { goal: g.item, cnt: g.count ?? 1, inv: st.inv, placed: st.placed, near: nearMap(), hp: st.hp, night: st.night })
      return say(pl.steps.length ? T('answer.recipe', { ko: g.ko, how: pl.opts[pl.pick].split(' | ').slice(1, 3).join(' ') }) : T('answer.recipe_none', { ko: g.ko }))
    }
    default: return say(T('answer.status', { hp: Math.round(bot.health), food: bot.food, inv: invs }))
  }
}

// ---- 턴 처리 ----
const GOALS = new Set(['craft', 'mine', 'log', 'dig', 'furnace', 'hunt', 'farm', 'bucket', 'combat'])
async function onChat(user: string, msg: string) {
  const h = prevUser && (botq || S.hist && Date.now() - prevUser[1] < 120000) ? [prevUser[0], lastSay] : null  // HIST=0: hist 미학습 ckpt용
  prevUser = [msg, Date.now()]
  const aw = askQ; askQ = null
  if (aw) {  // 되묻기 답: "아카시아" + "나무 버려" → 모델이 한 문장으로 재해석, 여전히 되묻기면 원래 흐름
    const r = await api('/turn', { utt: `${msg} ${aw}`, state: { ...state(), botq: null }, hist: null })
    if (r.act === '목표 실행' && r.goals.length && !r.goals.some((x: any) => x.ask)) { log('ANSWER', msg, '+', aw, '→', JSON.stringify(r.goals)); botq = null; return doType(user, `${msg} ${aw}`, r) }
  }
  const t = await api('/turn', { utt: msg, state: state(), hist: h, task: { goal: cur?.goal ?? null, step: task, threat: threatText() } })
  emit({ type: 'miya', ms: Math.round(t.ms), doc: msg, a: { intent: [t.act, Math.round(t.act_p * 100)], skill: [t.type, Math.round(t.type_p * 100)], ask: [t.query ?? 'none'], goal: [t.goals.map((g: any) => g.ko + (g.count ? '×' + g.count : '')).join(',') || 'none'] }, spans: t.spans.map((s: any) => `${s.label}:${s.text}`) })
  log('TURN', msg, '|', t.act, t.type, t.query, JSON.stringify(t.goals), t.ms + 'ms')
  const g = t.goals[0], af = askFor
  botq = null; askFor = null
  if (af && (t.act === '긍정 대답' || t.act === '부정 대답' || t.act === '목표 실행' && g?.item === af.goal)) return runGoal(af.req, af.goal, af.n, af.ko, af.type, true)
  switch (t.act) {
    case '목표 실행': return doType(user, msg, t)
    case '질문 답하기': return answer(t.query, user, t)
    case '되묻기': {
      const s = t.spans.find((s: any) => !s.item && (s.label === '대상')) ?? t.spans[0]
      const q = s ? T('ask.what_is', { text: s.text }) : T('ask.unclear')
      botq = q; return say(q)
    }
    case '멈춤': job++; bot.pathfinder.setGoal(null); if (task) paused = null; task = null; plan = null; return say(T('act.stop'))
    case '재개': if (paused) { const p = paused; paused = null; return runGoal(p.req, p.goal, p.cnt, p.ko ?? p.goal, p.type, p.noask, p) } return say(T('act.no_resume'))
    case '긍정 대답': return say(T('act.yes'))
    case '부정 대답': return say(T('act.no'))
    case '위험 경고': return say(T('act.warn'))
    case '지적·조언': {  // 행동 변화 = 모델(/turn hact)
      const a = t.hact?.act ?? 'explain', c = cur
      log('HINT', t.hint, '→', t.hact?.label)
      if (a === 'danger') { lastSig = ''; return say(T('hint.danger')) }
      if (a === 'ask') { botq = T('hint.ask'); return say(botq) }
      if ((a === 'replan' || a === 'recheck') && c) { say(T('hint.' + a)); job++; return runGoal(c.req, c.goal, c.cnt, c.ko, c.type, c.noask, c) }
      return say(c ? T('hint.explain') : T('act.hint', { hint: t.hint }))
    }
    case '욕설': return say(T('act.swear'))
    default: return say(g ? T('act.echo', { ko: g.ko }) : T('act.chat'))
  }
}
async function pickMob(type: string, why: string): Promise<string | null> {
  const es = Object.values(bot.entities).filter(x => x.type === (type === 'combat' ? 'hostile' : 'animal') && dist(x.position) < 48).sort((a, b) => dist(a.position) - dist(b.position))
  if (type === 'combat') {
    if (!es.length) return null
    const ts = es.slice(0, 5).map(e => [e.name, dist(e.position)])
    const r = await api('/target', { threats: ts, hp: Math.round(bot.health), armor: armorPts(), why }).catch(() => ({ mob: ts[0][0] }))
    return r.mob
  }
  const by: Record<string, [string, number, number]> = {}
  for (const e of es) { const k = e.name!; by[k] = by[k] ? [k, by[k][1], by[k][2] + 1] : [k, dist(e.position), 1] }
  const r = await api('/hunt', { animals: Object.values(by).slice(0, 6), food: bot.food, has_food: bot.inventory.items().some(i => mc.foodsByName[i.name]), want: why }).catch(() => null)
  log('HUNT', JSON.stringify(Object.values(by)), '→', r?.mob ?? '원정')
  return r?.mob ?? null
}
async function doType(user: string, msg: string, t: any) {
  const g = t.goals[0], e = player(user)
  const aq = t.goals.find((x: any) => x.ask)  // 모델: 실물·개수 불확실 + 파괴적 행동 → 되묻기
  if (aq) { const q = aq.ask === 'which' ? T('ask.which', { cands: aq.cands.join(', ') }) : T('ask.count', { ko: aq.ko, held: aq.held }); botq = q; askQ = msg; return say(q) }
  if (GOALS.has(t.type)) {
    const m = !g && (t.type === 'combat' || t.type === 'hunt') ? await pickMob(t.type, msg) : null  // 대상없는 전투·사냥 → 무엇을 = 모델(/target·/hunt)
    if (m) return runGoal(msg, 'mob:' + m, 1, (await kos(['mob:' + m]))['mob:' + m] ?? '몹', t.type)
    if (!g && t.type === 'hunt') return runGoal(msg, 'grp:meat', 1, '고기', t.type)  // 모델: 주변 없음 → 고기 (원정은 plan)
    if (!g) { botq = '뭘요?'; return say(T('ask.what_do')) }
    for (const x of t.goals) await runGoal(msg, x.item, x.count ?? 1, x.ko, t.type)
    return
  }
  switch (t.type) {
    case 'come': case 'goto': case 'follow': {
      if (!e) return say(T('move.no_player'))
      if (t.type === 'follow') { task = '따라가는 중'; bot.pathfinder.setGoal(new goals.GoalFollow(e, S.follow_dist), true); return say(T('move.follow')) }
      say(T('move.go')); task = '가는 중'
      try { await go(new goals.GoalNear(e.position.x, e.position.y, e.position.z, 2)) } catch { say(T('move.no_path')) }
      task = null; return
    }
    case 'give': case 'drop': {
      if (!g) return say(T('ask.what_give'))
      for (const x of t.goals) await unwear(x.item).catch(() => { })
      const gs = t.goals.filter((x: any) => cnt(x.item))
      if (!gs.length) return say(T('none', { ko: g.ko }))
      if (t.type === 'give' && e) { try { await go(new goals.GoalNear(e.position.x, e.position.y, e.position.z, 2), 30000) } catch { } await bot.lookAt(e.position.offset(0, 1.6, 0)) }
      for (const x of gs) {
        const n = Math.min(cnt(x.item), x.count ?? cnt(x.item))
        await bot.toss(mc.itemsByName[x.item].id, null, n)
        say(T('done.' + t.type, { ko: x.ko, n }))
      }
      return
    }
    case 'equip': {
      if (!g || !cnt(g.item)) return say(g ? T('none', { ko: g.ko }) : T('ask.what'))
      const n = g.item as string
      const dest = /helmet/.test(n) ? 'head' : /chestplate|elytra/.test(n) ? 'torso' : /leggings/.test(n) ? 'legs' : /boots/.test(n) ? 'feet' : /shield/.test(n) ? 'off-hand' : 'hand'
      await equipName(n, dest); return say(T('done.equip', { ko: g.ko }))
    }
    case 'eat': return eat()
    case 'collect': await collectNear(); return say(T('done.collect'))
    case 'place': if (g) { try { await place(g.item); return say(T('done.place', { ko: g.ko })) } catch (x: any) { return say(T('fail.place', { why: x.message })) } } return say(T('ask.what_place'))
    case 'sleep': {
      const b = bot.findBlock({ matching: (b: any) => b.name.endsWith('_bed'), maxDistance: 32 })
      if (!b) return say(T('sleep.no_bed'))
      try { await go(new goals.GoalNear(b.position.x, b.position.y, b.position.z, 2)); await bot.sleep(b); return say(T('done.sleep')) } catch (x: any) { return say(T('fail.sleep', { why: x.message })) }
    }
    default: return say(T('unsupported', { type: t.type }))
  }
}
async function eat(fight = false) {  // 뭘 먹을지 = 모델(/food: 허기·포만·부작용·비상)
  const r = await api('/food', { inv: inv(), hp: Math.round(bot.health), food: bot.food, fight, task }).catch(() => null)
  const f = r ? bot.inventory.items().find(i => i.name === r.item) : bot.inventory.items().find(i => mc.foodsByName[i.name])
  if (r) log('FOOD', r.item, r.p)
  if (!f) return say(T('eat.none'))
  await bot.equip(f, 'hand'); await bot.consume(); say(T('done.eat'))
}

// ---- 우선순위(위협/생존) 루프: 상태 바뀔때만 요청 → 과부하 방지 ----
const DMG: Record<string, number> = { wooden: 4, golden: 4, stone: 5, iron: 6, diamond: 7, netherite: 8 }
let lastSig = '', busyPrio = false, hold = 0, holdHp = 20, fightT: any, fightE = -1, curAct = ''  // hold: 전투·도망 유지 끝 시각 (체력 줄면 해제)
const RESUME = ['멈춘 작업 재개', '계속 진행']  // 멈춘작업 있고 위협없을때 계속=재개
const resumes = new Map<string, number>()  // 자동재개 횟수 상한 → 실패-재개 무한루프 차단
// 인지: 벽·땅 너머 몹은 위협 아님(지하 채굴중 지상 스켈레톤 11칸 → 무한 도망·작업 정지 원인)
function seen(e: any) {
  const a = bot.entity.position.offset(0, bot.entity.height * 0.9, 0), b = e.position.offset(0, e.height * 0.85, 0), d = b.minus(a), n = d.norm()
  const h = (bot.world as any).raycast(a, d.scaled(1 / n), n)
  return !h || h.position.distanceTo(b.floored()) < 1
}
let hidden = false
const FILL = () => bot.inventory.items().find(i => /^(cobblestone|cobbled_deepslate|dirt|stone|netherrack|andesite|diorite|granite|tuff)$/.test(i.name))
async function shelter() {  // 굴: 발밑 3칸 파고 머리위 막기
  bot.pathfinder.setGoal(null)
  for (let k = 0; k < 3; k++) {
    const b = bot.blockAt(bot.entity.position.floored().offset(0, -1, 0))
    if (!b || b.boundingBox !== 'block' || /lava|water|bedrock/.test(b.name)) break
    const t = bot.pathfinder.bestHarvestTool(b); if (t) await bot.equip(t, 'hand').catch(() => { })
    await timeout(bot.dig(b), 15000).catch(() => bot.stopDigging()); await sleep(400)
  }
  const f = FILL(), p = bot.entity.position.floored()
  if (f) {
    await bot.equip(f, 'hand').catch(() => { })
    for (const o of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const ref = bot.blockAt(p.offset(o[0], 2, o[1]))
      if (ref?.boundingBox === 'block') { await bot.placeBlock(ref, new Vec3(-o[0], 0, -o[1])).catch((x: any) => log('shelter', x.message)); break }
    }
  }
  hidden = true; log('SHELTER', bot.entity.position.floored().toString())
}
async function pillar(n = 3) {  // 기둥: 점프+발밑 설치 n회
  bot.pathfinder.setGoal(null)
  for (let k = 0; k < n; k++) {
    const f = FILL(); if (!f) break
    await bot.equip(f, 'hand').catch(() => { })
    await bot.look(bot.entity.yaw, -Math.PI / 2, true)
    bot.setControlState('jump', true); await sleep(350); bot.setControlState('jump', false)
    const b = bot.blockAt(bot.entity.position.floored().offset(0, -2, 0))
    if (b) await bot.placeBlock(b, new Vec3(0, 1, 0)).catch((x: any) => log('pillar', x.message))
    await sleep(300)
  }
}
const threatText = () => Object.values(bot.entities).filter(e => e.type === 'hostile' && dist(e.position) < 16).slice(0, 3).map(e => `${ko('mob:' + e.name)} ${dist(e.position)}칸`).join(', ') || null
async function prioTick() {
  if (busyPrio || !bot.entity) return
  wearBest()
  const threats = Object.values(bot.entities).filter(e => e.type === 'hostile' && dist(e.position) < S.threat_r && (dist(e.position) <= 4 || seen(e))).sort((a, b) => dist(a.position) - dist(b.position)).slice(0, 3)
  const hp = Math.round(bot.health ?? 20)  // 스폰 직후 health 미수신 → NaN
  const free = bot.inventory.emptySlotCount()
  const food = bot.inventory.items().find(i => mc.foodsByName[i.name])
  if (S.hp_eat && hp <= S.hp_eat && bot.food < 20 && food) { busyPrio = true; try { log('PRIO 강제 먹기'); await eat() } finally { busyPrio = false } return }  // 유저 강제 규칙
  if (!threats.length && curAct !== '굴 파고 숨기') curAct = ''
  if (hidden && night()) return  // 숨는 중: 아침까지 대기 (숨기 행동의 일부)
  hidden = false
  if (Date.now() < hold && hp >= holdHp && threats.length) return  // 전투·도망 유지 (전투↔도망 루프 방지)
  const sig = `${hp}|${bot.food}|${air}|${free}|${night()}|${task ? 1 : 0}|${paused && !task ? Math.floor(Date.now() / 15000) : ''}|${threats.map(e => (e.name ?? "") + Math.round(dist(e.position) / S.dist_bucket)).join(',')}`
  if (sig === lastSig) return
  lastSig = sig
  busyPrio = true
  try {
    const sw = bot.inventory.items().map(i => i.name).filter(n => n.endsWith('_sword')).sort((a, b) => DMG[b.split('_')[0]] - DMG[a.split('_')[0]])[0]
    const kw = await kos([...(sw ? [sw] : []), ...threats.map(e => 'mob:' + e.name)])
    const armor = armorPts()
    const ctx = `체력 ${hp}/20 배고픔 ${bot.food}/20 빈칸 ${free}/36${air < 20 ? ` 산소 ${air}/20` : ''} ${night() ? '밤' : '낮'} 방어 ${armor} 무기 ${sw ? kw[sw] : '맨손'} 공격력 ${sw ? DMG[sw.split('_')[0]] : 1}` +
      ` | 음식 ${food ? '있음' : '없음'} | 작업: ${task ?? '없음'}` + (paused ? ' | 멈춘작업: ' + paused.req : '') +
      (curAct ? ' | 현재: ' + curAct : '') + ' | 위협: ' + (threats.map(e => `${kw['mob:' + e.name]} ${dist(e.position)}칸`).join(', ') || '없음') +
      (lastDeath ? ' | 최근 사망원인: ' + lastDeath : '')
    const r = await api('/prio', { ctx })
    let e = threats[0]
    if (threats.length > 1 && r.label === '근접 전투') {  // 누구부터 = 모델(/target)
      const tr = await api('/target', { threats: threats.map(x => [x.name, dist(x.position)]), hp, weapon: sw ? kw[sw] : '맨손', armor }).catch(() => null)
      if (tr) { e = threats[tr.i] ?? e; log('TARGET', tr.mob, tr.p) }
    }
    const forced = !e ? null : S.hp_flee && hp <= S.hp_flee ? '달려서 도망' : r.label === '근접 전투' || /도망/.test(r.label) ? (S.hostile_policy === 'fight' ? '근접 전투' : S.hostile_policy === 'avoid' ? '달려서 도망' : null) : null
    if (forced && forced !== r.label) { log('PRIO 설정 강제', r.label, '→', forced); r.label = forced; r.forced = true }
    log('PRIO', ctx, '→', r.label, r.p.toFixed(2))
    if (['근접 전투', '달려서 도망', '블럭 쌓아 도망'].includes(r.label)) { hold = Date.now() + S.prio_hold_ms; holdHp = hp }
    curAct = ['근접 전투', '달려서 도망', '굴 파고 숨기'].includes(r.label) ? r.label : ''
    if (r.label !== '근접 전투' || fightE !== e?.id) { clearInterval(fightT); fightE = -1 }  // 행동·대상 바뀌면 교전 타이머 정리
    if (r.label !== '계속') emit({ type: /도망/.test(r.label) ? 'evade' : 'decision', text: `우선순위: ${r.label} (${Math.round(r.p * 100)}%)`, forced: !!r.forced })
    if ((['근접 전투', '달려서 도망', '블럭 쌓아 도망'].includes(r.label) && e || r.label === '굴 파고 숨기') && cur) { paused = { ...cur }; cur = null; job++; task = null; log('PAUSE', paused.req) }
    if (r.label === '물 위로 올라가기') await surface()
    else if (r.label === '먹기') await eat(!!e)
    else if (r.label === '굴 파고 숨기') { say(T('prio.hide')); await shelter() }
    else if (r.label === '블럭 쌓아 도망') { say(T('prio.pillar')); await pillar(); hold = Date.now() + S.prio_hold_ms }
    else if (r.label === '인벤 정리' && !task) await tidy('인벤 가득', cur?.goal, cur?.cnt)
    else if (r.label === '근접 전투' && e) {  // 유지시간 동안 공격 반복 (prio 틱 없이도 계속 때림)
      if (fightE === e.id) return  // 같은 대상 교전중 → 재장착·타이머 재시작 X (장착마다 공격 쿨다운 초기화)
      fightE = e.id; await arm(e, threats.length); bot.pathfinder.setGoal(new goals.GoalFollow(e, 1), true)
      clearInterval(fightT); fightT = setInterval(() => { if (!e.isValid || Date.now() > hold) { fightE = -1; return clearInterval(fightT) } if (dist(e.position) <= 3) bot.lookAt(e.position.offset(0, e.height / 2, 0)).then(() => bot.attack(e)).catch(() => { }) }, 600)
    }
    else if (r.label === '달려서 도망' && e) {  // GoalInvert(Follow)는 굴·좁은길서 경로 못찾고 조용히 정지 → 반대방향 고정점 + go() 끼임감지
      const p = bot.entity.position, v = p.minus(e.position), k = 16 / (Math.hypot(v.x, v.z) || 1)
      go(new goals.GoalNearXZ(p.x + v.x * k, p.z + v.z * k, 3), 15000).catch((x: any) => { log('flee', x.message); hold = 0 })
    }
    else if (RESUME.includes(r.label) && paused && !task && !e && (resumes.get(paused.req) ?? 0) >= S.resume_max) { say(T('fail.paused', { req: paused.req })); resumes.delete(paused.req); paused = null }  // 상한: 조용히 무시하면 영구대기
    else if (RESUME.includes(r.label) && paused && !task && !e) { const p = paused; resumes.set(p.req, (resumes.get(p.req) ?? 0) + 1); paused = null; bot.pathfinder.setGoal(null); runGoal(p.req, p.goal, p.cnt, p.ko ?? p.goal, p.type, p.noask, p).catch(x => log('ERR', x)) }
  } catch (x: any) { log('prio', x.message) } finally { busyPrio = false }
}

bot.once('spawn', () => {
  mc = require('minecraft-data')(bot.version)
  ;(bot as any).physics.playerHalfWidth = 0.301  // Paper: 벽에 딱 붙은(0.3) 이동 조용히 롤백 → 여유 0.001
  const mv = new Movements(bot)
  const apply = () => { mv.canDig = S.dig_path; mv.allowSprinting = S.sprint; mv.allowParkour = S.parkour }
  apply(); settings.onChange(apply)
  bot.pathfinder.setMovements(mv)
  log('SPAWN', bot.entity.position, bot.game.gameMode)
  api('/placed', {}).then(r => { own = r.list }).catch(() => { })
  const tick = () => prioTick().finally(() => setTimeout(tick, S.prio_ms)); tick()
})
bot.on('chat', (user, msg) => {
  chat.push({ who: user, text: msg, at: Date.now() }); if (chat.length > 100) chat.shift()
  if (user === bot.username) return
  log('<<', user, msg)
  onChat(user, msg).catch(e => { log('ERR', e.stack ?? e); say(T('error', { why: String(e.message).slice(0, 50) })) })
})
// ---- 사망 QED: 인벤은 사망시 비워지므로 체력변화마다 스냅샷, 서버 사망메시지로 원인 ----
let snap: any = null, dmsg = '', lastDeath: string | null = null
bot.on('health', () => { if (bot.health > 0) snap = { ...vars(), inv: inv(), weapon: bot.heldItem?.name ?? null, task, req: cur?.req ?? null } })
// 사망메시지 = 번역키 컴포넌트(death.attack.<원인>[.player|.item], with=[피해자, 가해자, 무기]) → 정규식 없이 키로 원인·가해자
bot.on('message', (m: any) => {
  if (!m.translate?.startsWith('death.') || String(m.with?.[0] ?? '') !== bot.username) return
  const k = m.translate as string, w = m.with?.[1]
  dmsg = JSON.stringify({ cause: k.startsWith('death.fell') ? 'fall' : k.split('.')[2], killer: !w ? null : w.translate?.startsWith('entity.minecraft.') ? w.translate.slice(17) : 'player' })
})
let lost: { pos: Vec3, t: number, inv: Record<string, number>, cause: string } | null = null
async function collectNear(r = 16) {
  for (const it of Object.values(bot.entities).filter(x => x.name === 'item' && dist(x.position) < r)) {
    try { await go(new goals.GoalBlock(Math.floor(it.position.x), Math.floor(it.position.y), Math.floor(it.position.z)), 8000) } catch { }
  }
}
async function recover() {  // 회수 여부 = 모델(/recover: 잃은 가치·거리·소멸시간·원인 위험)
  const l = lost; lost = null
  if (!l || !Object.keys(l.inv).length) return
  const w = bot.inventory.items().map(i => i.name).find(n => /_(sword|axe)$/.test(n)) ?? 'hand'
  const r = await api('/recover', { inv: l.inv, d: dist(l.pos), el: Math.round((Date.now() - l.t) / 1000), cause: l.cause, night: night(), armor: armorPts(), weapon: w, hp: Math.round(bot.health) }).catch(() => null)
  log('RECOVER', r?.go, r?.value, r?.p)
  if (!r) return
  if (!r.go) return say(T('death.skip', { v: Math.round(r.value) }))
  say(T('death.recover', { d: dist(l.pos) }))
  const id = ++job; task = '사망 회수'
  try { await go(new goals.GoalNear(l.pos.x, l.pos.y, l.pos.z, 2), 180000); await collectNear() } catch (x: any) { log('recover', x.message) }
  if (id === job) task = null
}
bot.on('spawn', () => { if (lost) setTimeout(recover, 1500) })
bot.on('death', () => {
  log('DEATH'); job++; task = null; plan = null
  placed['place:death'] = bot.entity.position.floored()
  const s = snap
  setTimeout(async () => {  // 사망메시지 death 이벤트보다 늦게 올 수 있음
    const d = dmsg ? JSON.parse(dmsg) : { cause: 'other', killer: null }; dmsg = ''
    try {
      const r = await api('/death', { ...s, ...d, msg: undefined })
      if (d.killer && d.killer !== 'player') lastDeath = (await kos(['mob:' + d.killer]))['mob:' + d.killer]
      else if (d.cause === 'drown') lastDeath = '익사'
      log('DEATH', d.cause, d.killer, 'inv_value', r.inv_value, JSON.stringify(r.top))
      emit({ type: 'death', text: `사망: ${d.killer ?? d.cause} (잃은 가치 ${r.inv_value})` })
      lost = { pos: placed['place:death'], t: Date.now(), inv: s?.inv ?? {}, cause: d.killer && d.killer !== 'player' ? d.killer : d.cause }
      if (bot.health > 0) recover()
    } catch (e: any) { log('death', e.message) }
  }, 500)
})
bot.on('kicked', r => { log('KICK', r); emit({ type: 'kicked', text: String(r).slice(0, 100) }) })
bot.on('error', e => log('ERR', e))
bot.on('end', r => { log('END', r); process.exit(1) })

// ---- webui (miya-stream-webui) ----
const startedAt = Date.now(), koC = new Map<string, string>(), koWant = new Set<string>()
const ko = (id: string) => { const v = koC.get(id); if (v === undefined && !koC.has(id)) koWant.add(id); return v ?? id.replace(/^mob:/, '') }
setInterval(() => { if (!koWant.size) return; const ids = [...koWant]; koWant.clear(); ids.forEach(i => koC.set(i, i.replace(/^mob:/, ''))); api('/ko', { ids }).then(r => { for (const i of ids) if (r[i]) koC.set(i, r[i]) }).catch(() => { }) }, 1000)
async function kos(ids: string[]) {  // /ko 캐시 (prio 틱마다 API 호출 방지)
  const miss = [...new Set(ids)].filter(i => !koC.has(i) || koC.get(i) === i.replace(/^mob:/, ''))
  if (miss.length) { const r = await api('/ko', { ids: miss }).catch(() => ({})); for (const i of miss) koC.set(i, r[i] ?? i.replace(/^mob:/, '')) }
  return Object.fromEntries(ids.map(i => [i, koC.get(i)!]))
}
const item = (i: any) => i ? { name: 'minecraft:' + i.name, ko: ko(i.name), count: i.count, dur: i.maxDurability ? { left: i.maxDurability - (i.durabilityUsed ?? 0), max: i.maxDurability } : null, ench: [], custom: i.customName ?? null } : null
// 열린 창(작업대·화로·상자 등) → webui GUI 오버레이용. props=화로 진행도 등 창 속성 패킷 원값
const winProps: Record<number, number> = {}
bot._client.on('craft_progress_bar', (p: any) => { if (p.windowId === bot.currentWindow?.id) winProps[p.property] = p.value })
bot.on('windowOpen', () => { for (const k in winProps) delete winProps[k] })
const win = () => { const w: any = bot.currentWindow; if (!w) return null
  let title = w.title; try { const j = JSON.parse(title); title = j.translate ?? j.text ?? title } catch { }
  return { id: w.id, type: String(w.type).replace(/^minecraft:/, ''), title, slots: w.slots.slice(0, w.inventoryStart).map(item), props: { ...winProps } } }
function webState() {
  if (!bot.entity) return { online: false, startedAt, name: NAME, chat }
  const s = bot.inventory.slots, me = bot.entity.position, now = Date.now()
  const recent = calls.filter(c => now - c[0] < 60000)
  return {
    online: true, startedAt, name: bot.username, hp: Math.round(bot.health), food: bot.food, air,
    level: bot.experience.level, xp: bot.experience.progress, armorPts: armorPts(),
    pos: { x: Math.floor(me.x), y: Math.floor(me.y), z: Math.floor(me.z) }, dim: String(bot.game.dimension).replace(/^minecraft:/, ''),
    day: !night(), tod: bot.time.timeOfDay / 24000, task: task ?? 'idle', progress: plan ? `${plan.steps.filter(x => x.state === 'done').length}/${plan.steps.length}` : '',
    held: bot.heldItem ? 'minecraft:' + bot.heldItem.name : null, inv: [...s.slice(9, 45)].map(item), armor: [8, 7, 6, 5].map(k => item(s[k])), offhand: item(s[45]), sel: bot.quickBarSlot, window: win(),
    near: Object.values(bot.entities).filter(e => e !== bot.entity && e.type !== 'object' && e.name !== 'item' && me.distanceTo(e.position) < 32)
      .map(e => ({ name: e.type === 'player' ? e.username! : ko('mob:' + e.name), type: e.type === 'player' ? 'player' : e.type === 'hostile' ? 'hostile' : 'mob', d: Math.round(me.distanceTo(e.position)) })).sort((a, b) => a.d - b.d).slice(0, 12),
    players: Object.keys(bot.players).filter(n => n !== bot.username), plan, paused: paused ? [{ label: paused.req }] : [], chat,
    miya: { ok: apiOk, ms: calls.at(-1)?.[1] ?? 0, perMin: recent.length, avgMs: Math.round(recent.reduce((a, c) => a + c[1], 0) / Math.max(1, recent.length)), level: apiOk ? 'ok' : 'down' },
  }
}
const srvs = serveWeb(WEB, webState, (text, as) => {
  const who = as ?? 'web'
  chat.push({ who, text, at: Date.now() }); log('<<', who, '(web)', text)
  onChat(who, text).catch(e => { log('ERR', e.stack ?? e); say(T('error', { why: String(e.message).slice(0, 50) })) })
}, settings)
bot.once('spawn', () => { try { hook.viewer = viewer(bot, srvs) } catch (e: any) { log('viewer', e.message) } })
