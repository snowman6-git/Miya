// 봇 설정: webui /settings 컨트랙트 {fields, values}, bot/settings.json 저장(재시작 유지). 판단은 모델, 여기는 실행 방식·호출 빈도·유저 강제 규칙만
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'

type Field = { key: string, label: string, type: 'bool' | 'number' | 'choice' | 'text', group: string, def: unknown, min?: number, max?: number, step?: number, note?: string, options?: Record<string, string> }
const fields: Field[] = [
  { key: 'prio_ms', label: '생존판단 호출 간격', type: 'number', group: '모델', def: 1000, min: 250, max: 10000, step: 250, note: 'ms, 상태 바뀔때만 호출' },
  { key: 'prio_hold_ms', label: '전투·도망 유지 시간', type: 'number', group: '모델', def: 3000, min: 0, max: 20000, step: 500, note: 'ms, 그동안 재판단 안함(체력 감소시 즉시). 전투↔도망 루프 방지' },
  { key: 'dist_bucket', label: '위협 거리 단위', type: 'number', group: '모델', def: 4, min: 1, max: 8, step: 1, note: '칸, 이 단위로 거리 변해야 재판단' },
  { key: 'hist', label: '직전 대화 맥락 사용', type: 'bool', group: '모델', def: process.env.HIST !== '0' },
  { key: 'threat_r', label: '위협 감지 반경', type: 'number', group: '생존', def: 16, min: 4, max: 32, step: 1, note: '칸' },
  { key: 'hp_check', label: '체력 이하시 생존판단', type: 'number', group: '생존', def: 10, min: 1, max: 20, step: 1 },
  { key: 'food_check', label: '배고픔 이하시 생존판단', type: 'number', group: '생존', def: 6, min: 0, max: 20, step: 1 },
  { key: 'hp_eat', label: '체력 이하시 무조건 먹기', type: 'number', group: '생존', def: 0, min: 0, max: 20, step: 1, note: '0=모델에 맡김' },
  { key: 'hp_flee', label: '체력 이하시 무조건 도망', type: 'number', group: '생존', def: 0, min: 0, max: 20, step: 1, note: '0=모델에 맡김' },
  { key: 'hostile_policy', label: '적대몹 대응', type: 'choice', group: '생존', def: 'auto', options: { auto: '모델 판단', fight: '항상 교전', avoid: '항상 회피' } },
  { key: 'resume_max', label: '자동 재개 상한', type: 'number', group: '생존', def: 2, min: 0, max: 10, step: 1, note: '실패-재개 루프 차단' },
  { key: 'mine_mode', label: '채광 방식', type: 'choice', group: '채광', def: 'near', options: { near: '보이는 광석', stair: '계단굴 (광석 높이로 하강)' } },
  { key: 'stair_w', label: '계단굴 폭', type: 'choice', group: '채광', def: '1', options: { '1': '1칸 (블럭 적게)', '3': '3칸 (넓게, 광석 노출↑)' } },
  { key: 'stair_h', label: '계단굴 높이', type: 'number', group: '채광', def: 3, min: 2, max: 4, step: 1, note: '칸, 2=최소, 3=점프 여유' },
  { key: 'scan_r', label: '블럭 탐색 반경', type: 'number', group: '채광', def: 64, min: 16, max: 128, step: 8, note: '칸, 클수록 느림' },
  { key: 'explore_hops', label: '원정 이동 횟수', type: 'number', group: '채광', def: 6, min: 1, max: 20, step: 1 },
  { key: 'explore_dist', label: '원정 1회 거리', type: 'number', group: '채광', def: 64, min: 16, max: 256, step: 16, note: '칸' },
  { key: 'dig_path', label: '이동중 블럭 파기', type: 'bool', group: '이동', def: true },
  { key: 'sprint', label: '달리기', type: 'bool', group: '이동', def: true },
  { key: 'parkour', label: '파쿠르(점프 건너기)', type: 'bool', group: '이동', def: true },
  { key: 'follow_dist', label: '따라갈 거리', type: 'number', group: '이동', def: 2, min: 1, max: 16, step: 1, note: '칸' },
  { key: 'tidy_before', label: '작업전 인벤 정리', type: 'bool', group: '행동', def: true },
  { key: 'talk', label: '채팅 말하기', type: 'bool', group: '행동', def: true, note: '끄면 로그·webui만' },
]
const FILE = path.resolve(__dirname, '../settings.json')
const hooks: ((changed: string[]) => void)[] = []
const values: Record<string, any> = Object.fromEntries(fields.map(f => [f.key, f.def]))
try { set(JSON.parse(readFileSync(FILE, 'utf8'))) } catch { }

// 신뢰경계: 모르는 키 무시, 타입 강제·범위 clamp
function set(b: Record<string, unknown>) {
  const changed: string[] = []
  for (const f of fields) {
    if (!(f.key in b)) continue
    let v: any = b[f.key]
    if (f.type === 'number') { v = Number(v); if (!Number.isFinite(v)) continue; v = Math.min(f.max ?? v, Math.max(f.min ?? v, v)) }
    else if (f.type === 'bool') v = v === true || v === 'true'
    else if (f.type === 'choice') { v = String(v); if (!(v in f.options!)) continue }
    else v = String(v).slice(0, 500)
    if (values[f.key] !== v) { values[f.key] = v; changed.push(f.key) }
  }
  if (changed.length) { try { writeFileSync(FILE, JSON.stringify(values, null, 1)) } catch { } for (const h of hooks) h(changed) }
  return changed
}
export const S = values
export const settings = { fields: fields.map(({ def, ...f }) => f), values, set, onChange: (h: (c: string[]) => void) => hooks.push(h) }
