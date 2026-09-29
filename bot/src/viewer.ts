// /viewer: prismarine-viewer(최대 1.21.4) 재사용, 26.1.2 청크/블록 stateId → 1.21.4 로 변환해 전송
import type { Server } from 'node:http'
import type { Bot } from 'mineflayer'
const express = require('express')
const { Server: IO } = require('socket.io')
const { WorldView } = require('prismarine-viewer/viewer/lib/worldView')
const { setupRoutes } = require('prismarine-viewer/lib/common')
const Chunk = require('prismarine-chunk')
const PBlock = require('prismarine-block')

const TV = '1.21.4'
export function viewer(bot: Bot, servers: Server[], dist = 6) {
  const B0 = PBlock(bot.version), B1 = PBlock(TV), C1 = Chunk(TV)
  const md0 = require('minecraft-data')(bot.version), md1 = require('minecraft-data')(TV)
  // stateId 매핑표: 이름+속성 일치 → 해당 상태, 이름만 → 기본상태, 없음 → 돌
  const map = new Uint32Array(md0.blocksArray.reduce((m: number, b: any) => Math.max(m, b.maxStateId), 0) + 1)
  const stone = md1.blocksByName.stone.defaultState
  for (const b of md0.blocksArray) {
    const t = md1.blocksByName[b.name]
    for (let s = b.minStateId; s <= b.maxStateId; s++) {
      if (!t) { map[s] = stone; continue }
      try { map[s] = B1.fromProperties(b.name, B0.fromStateId(s, 0).getProperties(), 0).stateId } catch { map[s] = t.defaultState }
    }
  }
  const bio = new Map<number, number>(md0.biomesArray.map((b: any) => [b.id, md1.biomesByName[b.name]?.id ?? md1.biomesByName.plains.id]))
  const conv = (col: any) => {
    const c = new C1({ minY: col.minY ?? -64, worldHeight: col.worldHeight ?? 384 })
    const p = { x: 0, y: 0, z: 0 } as any
    for (let y = col.minY ?? -64, top = y + (col.worldHeight ?? 384); y < top; y++) {
      const sec = col.sections?.[(y - (col.minY ?? -64)) >> 4]
      if (sec && sec.solidBlockCount === 0) { y |= 15; continue }  // 빈 섹션 건너뜀
      for (p.y = y, p.x = 0; p.x < 16; p.x++) for (p.z = 0; p.z < 16; p.z++) {
        const s = col.getBlockStateId(p)
        if (s) c.setBlockStateId(p, map[s] ?? stone)
        if (!((y | p.x | p.z) & 3)) c.setBiome(p, bio.get(col.getBiome(p)) ?? 0)  // 바이옴 4x4x4 단위 → 풀/잎 색
      }
    }
    return c
  }
  const world = { getColumnAt: async (pos: any) => { const col = bot.world.getColumnAt(pos); return col && conv(col) }, raycast: () => null }

  const app = express()
  app.get('/viewer/index.js', (_: any, res: any) => res.type('js').send(client()))
  app.get('/viewer/item/:id', (req: any, res: any) => res.json({ name: (bot.entities[req.params.id] as any)?.getDroppedItem?.()?.name ?? null }))  // 드롭템 이름(메타 늦게 옴 → 클라 재시도)
  setupRoutes(app, '/viewer')
  for (const srv of servers) {
    new IO(srv, { path: '/viewer/socket.io' }).on('connection', (sock: any) => {
      const first = /cam=first/.test(sock.handshake.headers.referer ?? '')
      const em = { emit: (ev: string, d: any) => sock.emit(ev, ev === 'blockUpdate' ? { ...d, stateId: map[d.stateId] ?? stone } : ev === 'entity' && bot.entities[d.id]?.name === 'item' ? { ...d, name: 'item' } : d), on: (ev: string, f: any) => sock.on(ev, f) }
      sock.emit('version', TV)
      const wv = new WorldView(world, dist, bot.entity.position, em)
      wv.init(bot.entity.position)
      const pos = () => { sock.emit('position', { pos: bot.entity.position, yaw: bot.entity.yaw, addMesh: true, ...(first ? { pitch: bot.entity.pitch } : {}) }); wv.updatePosition(bot.entity.position) }
      bot.on('move', pos)
      wv.listenToBot(bot)
      // 캐기 균열·팔 휘두르기: 자기 캐기는 서버가 안 알려줌 → targetDigBlock 폴링, 타인은 이벤트
      let tgt: any = null, t0 = 0, st = -1, sw = 0
      const dig = setInterval(() => {
        const b = (bot as any).targetDigBlock
        if (b !== tgt) { if (tgt && st >= 0) sock.emit('dig', { pos: tgt.position, stage: -1 }); tgt = b; t0 = Date.now(); st = -1 }
        if (!b) return
        const k = Math.min(9, Math.floor((Date.now() - t0) / Math.max(50, bot.digTime(b)) * 10))
        if (k !== st) sock.emit('dig', { pos: b.position, stage: st = k })
        if (Date.now() - sw > 250) { sw = Date.now(); sock.emit('swing', { self: true }) }
      }, 100)
      const obs = (b: any, stage: number) => sock.emit('dig', { pos: b.position, stage })
      const end = (b: any) => sock.emit('dig', { pos: b.position, stage: -1 })
      const swing = (e: any) => sock.emit('swing', { id: e.id })
      bot.on('blockBreakProgressObserved', obs); bot.on('blockBreakProgressEnd', end); bot.on('entitySwingArm', swing)
      sock.on('disconnect', () => {
        bot.removeListener('move', pos); wv.removeListenersFromBot(bot); clearInterval(dig)
        bot.removeListener('blockBreakProgressObserved', obs); bot.removeListener('blockBreakProgressEnd', end); bot.removeListener('entitySwingArm', swing)
      })
    })
  }
  return app  // http 핸들러: /viewer/* 정적파일
}

// 클라 번들 보간 패치: 50ms 트윈 겹침(구 트윈이 새 트윈과 싸움) + 1인칭 회전 즉시 스냅 → 끊김
// 트윈 1개만 유지(이전 stop) + SMOOTH ms, 카메라 회전도 최단각 트윈. 서버 move 간격 지터 흡수
const SMOOTH = Number(process.env.VIEW_SMOOTH ?? 120)
let js = ''
function client() {
  if (js) return js
  const f = require.resolve('prismarine-viewer/public/index.js')
  let s: string = require('node:fs').readFileSync(f, 'utf8'), n = 0
  s = s.replace(/new (\w)\.Tween\(([\w.]+)\)\.to\((\{[^}]*\}),50\)\.start\(\)/g, (_m, T, o, t) => (n++, `(${o}._tw&&${o}._tw.stop(),${o}._tw=new ${T}.Tween(${o}).to(${t},${SMOOTH}).start())`))
  // [원본, 교체]: 카메라 회전 트윈 / 뼈 이름 / 미지 엔티티 훅 / THREE·viewer 노출 / 소켓 노출 / 봇 메시 노출
  const P: [string, string][] = [
    ['this.camera.rotation.set(i,e,0,"ZYX")', `{const c=this.camera.rotation,T=r.Tween;c.order="ZYX";let d=(e-c.y)%(2*Math.PI);d=2*d%(2*Math.PI)-d;c._tw&&c._tw.stop(),c._tw=new T(c).to({x:i,y:c.y+d},${SMOOTH}).start()}`],
    ['i[t.name]=r,t.cubes)', 'i[t.name]=r,r.name=t.name,t.cubes)'],
    ['const i=new n.BoxGeometry(t.width,t.height,t.width);', 'if(window.__mesh){const m=window.__mesh(n,t);if(m)return m}const i=new n.BoxGeometry(t.width,t.height,t.width);'],
    ['this.playerHeight=1.6,', 'this.playerHeight=1.6,window.__T=n,window.__V=this,'],
    ['o.on("position",', 'window.__S=o,o.on("position",'],
    ['u.scene.add(e))', 'u.scene.add(e),window.__B=e)'],
  ]
  const miss = P.filter(([a]) => s.split(a).length !== 2)
  if (n !== 5 || miss.length) { console.log('VIEWER patch miss', n, miss.map(x => x[0])); return js = s }  // 번들 바뀜 → 원본
  for (const [a, b] of P) s = s.replace(a, () => b)
  return js = s + EXTRA
}

// 클라 추가분: 드롭템 스프라이트(둥실), 캐기 균열(destroy_stage), 오른팔 휘두르기
const EXTRA = `;(()=>{
const tex={},L=(T,p)=>tex[p]||(tex[p]=new T.TextureLoader().load('/mc/'+p,x=>{x.magFilter=x.minFilter=T.NearestFilter})),items=new Set();let crack
window.__mesh=(T,t)=>{if(t.name!=='item')return null
 const g=new T.Group(),s=new T.Sprite(new T.SpriteMaterial({transparent:true,alphaTest:.1}));s.scale.set(.4,.4,.4);g.add(s);g.userData.ph=Math.random()*6;items.add(g)
 const get=k=>fetch('/viewer/item/'+t.id).then(r=>r.json()).then(j=>j.name?fetch('/icon/'+j.name).then(r=>r.json()).then(i=>{const p=i.kind==='flat'?i.layers[0]:i.kind==='block'?i.north:i.tex;if(p){s.material.map=L(T,p);s.material.needsUpdate=true}}):k<5&&setTimeout(()=>get(k+1),300))
 get(0);return g}
function tick(){requestAnimationFrame(tick);const now=performance.now()/1000
 for(const g of items){if(!g.parent){items.delete(g);continue}g.children[0].position.y=.25+Math.sin(now*2+g.userData.ph)*.06}
 const S=window.__S;if(!S||S.__hk)return;S.__hk=1
 S.on('dig',d=>{const T=window.__T,V=window.__V;if(!T||!V)return
  if(!crack){crack=new T.Mesh(new T.BoxGeometry(1.004,1.004,1.004),new T.MeshBasicMaterial({transparent:true,depthWrite:false,polygonOffset:true,polygonOffsetFactor:-1}));V.scene.add(crack)}
  if(d.stage<0){crack.visible=false;return}
  crack.visible=true;crack.position.set(d.pos.x+.5,d.pos.y+.5,d.pos.z+.5);crack.material.map=L(T,'textures/block/destroy_stage_'+d.stage+'.png');crack.material.needsUpdate=true})
 S.on('swing',d=>{const V=window.__V,m=d.self?window.__B:V&&V.entities.entities[d.id],a=m&&m.getObjectByName('rightArm');if(!a||a.__sw)return
  const x0=a.rotation.x,t0=performance.now();a.__sw=1
  const f=()=>{const k=(performance.now()-t0)/250;if(k>=1){a.rotation.x=x0;a.__sw=0;return}a.rotation.x=x0-Math.sin(k*Math.PI)*1.2;requestAnimationFrame(f)};f()})}
tick()})();`
