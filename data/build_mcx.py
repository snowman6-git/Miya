# mc.db(원본, 읽기만) + raw worldgen -> mcx.db(파생)
# 표: ore_gen, spawn, mine_time, item_value
# 실행: python3 data/build_mcx.py  (표준 라이브러리만)
import json, math, sqlite3, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MC = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / 'mcdata'
WG = MC / 'gen/data/minecraft/worldgen'
OUT = HERE / 'mcx.db'

src = sqlite3.connect(f'file:{MC / "mc.db"}?mode=ro', uri=True)
q = lambda s, *a: src.execute(s, a).fetchall()
nid = lambda s: s.removeprefix('minecraft:')

MIN_Y, TOP_Y = -64, 320                     # overworld noise_settings
NETHER = {'nether_wastes', 'soul_sand_valley', 'crimson_forest', 'warped_forest', 'basalt_deltas'}
def dim_of(b):
    if b in NETHER: return 'nether'
    if b.startswith('end_') or b in ('the_end', 'small_end_islands'): return 'end'
    return 'overworld'

# ---------- biome: 스폰 + 피처 목록 ----------
biome_feat, spawn_rows = {}, []
for f in sorted((WG / 'biome').glob('*.json')):
    b = f.stem
    if b == 'the_void': continue
    d = json.loads(f.read_text())
    biome_feat[b] = {nid(x) for step in d.get('features', []) for x in step}
    for cat, lst in d.get('spawners', {}).items():
        for s in lst:
            spawn_rows.append((b, dim_of(b), cat, nid(s['type']), s['weight'], s['minCount'], s['maxCount']))

# ---------- ore_gen ----------
def anchor(a, dim):
    lo, hi = (MIN_Y, TOP_Y) if dim == 'overworld' else (0, 256)   # nether 0~256 (bedrock 0/127 천장 무시)
    if 'absolute' in a: return a['absolute']
    if 'above_bottom' in a: return lo + a['above_bottom']
    if 'below_top' in a: return hi - 1 - a['below_top']
    raise ValueError(a)

def ore_blocks(cf):
    d = json.loads((WG / 'configured_feature' / f'{cf}.json').read_text())
    c = d.get('config', {})
    return [nid(t['state']['Name']) for t in c.get('targets', [])], c.get('size'), c.get('discard_chance_on_air_exposure', 0.0)

ore_rows = []
for f in sorted((WG / 'placed_feature').glob('ore_*.json')):
    pf = f.stem
    d = json.loads(f.read_text())
    feat = d['feature']
    if not isinstance(feat, str): continue
    blocks, size, air = ore_blocks(nid(feat))
    biomes = sorted(b for b, fs in biome_feat.items() if pf in fs)
    if not biomes or not blocks: continue
    dims = {dim_of(b) for b in biomes}
    dim = dims.pop() if len(dims) == 1 else 'mixed'
    count, rarity, lo, hi, dist = 1.0, None, None, None, None
    for p in d['placement']:
        t = nid(p['type'])
        if t == 'count':
            c = p['count']
            count = float(c) if not isinstance(c, dict) else (c.get('min_inclusive', 0) + c.get('max_inclusive', 0)) / 2
        elif t == 'rarity_filter':
            rarity = p['chance']
        elif t == 'height_range':
            h = p['height']
            dist = nid(h.get('type', 'uniform'))
            lo, hi = anchor(h['min_inclusive'], dim), anchor(h['max_inclusive'], dim)
    peak = (lo + hi) // 2 if dist == 'trapezoid' else None   # 클램프 전 기준
    if dim == 'overworld': lo, hi = max(lo, MIN_Y), min(hi, TOP_Y - 1)
    all_ow = dim == 'overworld' and len(biomes) >= sum(dim_of(b) == 'overworld' for b in biome_feat) - 2
    for blk in blocks:
        ore_rows.append((pf, blk, dim, count, rarity, size, air, dist, lo, hi, peak,
                         None if all_ow else json.dumps(biomes)))

# ---------- mine_time ----------
# 틱 = ceil(1 / (속도/경도/(수확가능?30:100))), 1틱 이내면 0(즉시). 효율·성급함·물속·공중 보정 없음
TIERS = ['wooden', 'gold', 'stone', 'copper', 'iron', 'diamond', 'netherite']
tag_members = lambda t: {r[0] for r in q("SELECT member FROM tags WHERE kind='block' AND tag=?", t)}
mineable = {k: tag_members(f'mineable/{k}') for k in ('pickaxe', 'axe', 'shovel', 'hoe')}
incorrect = {t: tag_members(f'incorrect_for_{t}_tool') for t in TIERS}
tools = []                                   # (item, 종류, 등급, 속도)
for iid, tier, spd in q("SELECT id, tool_tier, mine_speed FROM items WHERE kind='tool' AND mine_speed IS NOT NULL"):
    kind = iid.rsplit('_', 1)[-1]
    if kind in mineable and tier in TIERS: tools.append((iid, kind, tier, spd))

def ticks(speed, hard, ok):
    if hard == 0: return 0
    dmg = speed / hard / (30 if ok else 100)
    return 0 if dmg >= 1 else math.ceil(1 / dmg)

mine_rows = []
for bid, hard, req in q('SELECT id, hardness, requires FROM blocks WHERE hardness >= 0'):
    ok = not req
    mine_rows.append((bid, 'hand', None, ticks(1.0, hard, ok), int(ok)))
    for iid, kind, tier, spd in tools:
        if bid not in mineable[kind]: continue
        ok = bid not in incorrect[tier]
        mine_rows.append((bid, iid, tier, ticks(spd, hard, ok), int(ok)))

# ---------- item_value ----------
# 원자재 = 수확 난이도 x 희소도, 조합품 = 최저 재료비 x 1.05 (고정점 반복)
NEED_V = {None: 1.0, 'stone': 4.0, 'iron': 16.0, 'diamond': 64.0}
RARITY_V = {'common': 1.0, 'uncommon': 8.0, 'rare': 32.0, 'epic': 128.0}
blk = {b: (h, r, n) for b, h, r, n in q('SELECT id, hardness, requires, needs FROM blocks')}
ore_cnt = {}
for r in ore_rows:
    if r[2] == 'overworld' or r[2] == 'nether':
        ore_cnt[r[1]] = ore_cnt.get(r[1], 0) + r[3] / (r[4] or 1)
mob_hp = {m: (hp, cat) for m, hp, cat in q('SELECT id, health, category FROM mobs')}

def block_v(b):
    h, req, need = blk.get(b, (1.0, 0, None))
    if h is None or h < 0: return None
    v = NEED_V.get(need, 1.0) if req else (0.25 if h < 1 else 0.5)
    if b in ore_cnt and (b.endswith('_ore') or b == 'ancient_debris'):  # 광맥 적을수록 +. 채움돌(화강암·응회암 등)은 흔함 → 제외
        v *= 1 + math.log2(max(1.0, 100 / max(ore_cnt[b], 1e-6)))
    return v

INF = float('inf')
item_ids = {r[0] for r in q('SELECT id FROM items')}
# 저장블록 풀기(블록1 -> 9개)는 원가 산정 제외: 다이아블록->다이아 역산으로 값 붕괴 방지
unpack = lambda ing, cnt: cnt == 9 and len(ing) == 1 and ing[0].get('n', 1) == 1
crafted = {r for r, ing, cnt in q('SELECT result, ingredients, count FROM recipes WHERE ingredients IS NOT NULL')
           if not unpack(json.loads(ing), cnt)}
val, why = {}, {}
def offer(item, v, w):
    if v < val.get(item, INF): val[item], why[item] = v, w

BUILT_MOBS = {'iron_golem', 'snow_golem'}    # 플레이어가 만드는 몹 -> 드롭 원가 아님
self_drop = {}                               # 조합 가능한 블록의 자기드롭 -> 2단계에서만 사용
for s, item, mn, mx, cond in q('SELECT source, item, min, max, cond FROM loot'):
    cond = cond or ''
    avg = max((float(mn or 0) + float(mx or 0)) / 2, 0.5)
    chance = 10.0 if ('random_chance' in cond or 'table_bonus' in cond) else 1.0
    if s.startswith('blocks/'):
        b = s[7:]
        if item == b and 'silk_touch' in cond: continue
        if b not in item_ids: continue           # 설치형 전용 블록(redstone_wire 등) 드롭 -> 원가 아님
        v = block_v(b)
        if v is None: continue
        if item == b and item in crafted and b not in ore_cnt: self_drop[item] = v / avg; continue  # 자연생성(ore_gen) 블록은 채굴 원가 바로 사용
        offer(item, v * chance / avg, f'block:{b}')
    elif s.startswith('entities/'):
        m = s[9:]
        if m in BUILT_MOBS: continue
        hp, cat = mob_hp.get(m, (10.0, ''))
        v = max(0.5, (hp or 10) / 20) * (2 if cat == 'Hostile mobs' else 1)
        offer(item, v * chance / avg, f'mob:{m}')

recipes = [(r, ing, cnt, typ) for r, ing, cnt, typ in
           ((r, json.loads(i), c, t) for r, i, c, t in
            q('SELECT result, ingredients, count, type FROM recipes WHERE ingredients IS NOT NULL'))
           ]                                  # 풀기 레시피는 여기선 허용 (자기드롭 루프만 끊으면 됨)
def relax():
    for _ in range(50):
        changed = False
        for res, ing, cnt, typ in recipes:
            cost = 0.1 if typ in ('smelting', 'blasting', 'smoking', 'campfire_cooking') else 0.0
            for slot in ing:
                c = min((val.get(a, INF) for a in slot['any']), default=INF)
                cost += slot.get('n', 1) * c
                if cost == INF: break
            v = cost * 1.05 / (cnt or 1)
            if v < val.get(res, INF) - 1e-9:
                val[res], why[res] = v, f'recipe:{typ}'
                changed = True
        if not changed: break
relax()
for item, v in self_drop.items():            # 조합으로 값 못 얻은 것만 (밀·원목류 등)
    if item not in val: offer(item, v, f'block:{item}')
relax()

for iid, rar in q('SELECT id, rarity FROM items'):
    if iid not in val: offer(iid, RARITY_V.get(rar, 1.0), f'rarity:{rar}')

# ---------- 저장 ----------
OUT.unlink(missing_ok=True)
db = sqlite3.connect(OUT)
db.executescript('''
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE ore_gen (feature TEXT, block TEXT, dim TEXT, count REAL, rarity INTEGER, size INTEGER,
  air_discard REAL, dist TEXT, y_min INTEGER, y_max INTEGER, y_peak INTEGER, biomes TEXT);
CREATE TABLE spawn (biome TEXT, dim TEXT, category TEXT, mob TEXT, weight INTEGER, min INTEGER, max INTEGER);
CREATE TABLE mine_time (block TEXT, tool TEXT, tier TEXT, ticks INTEGER, drops INTEGER);
CREATE TABLE item_value (item TEXT PRIMARY KEY, v REAL, src TEXT);
CREATE INDEX ix_ore_block ON ore_gen(block);
CREATE INDEX ix_spawn_mob ON spawn(mob);
CREATE INDEX ix_spawn_biome ON spawn(biome, category);
CREATE INDEX ix_mine ON mine_time(block, ticks);
''')
db.executemany('INSERT INTO ore_gen VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', ore_rows)
db.executemany('INSERT INTO spawn VALUES (?,?,?,?,?,?,?)', spawn_rows)
db.executemany('INSERT INTO mine_time VALUES (?,?,?,?,?)', mine_rows)
db.executemany('INSERT INTO item_value VALUES (?,?,?)', [(k, round(v, 3), why[k]) for k, v in val.items()])
db.executemany('INSERT INTO meta VALUES (?,?)', [
    ('src', str(MC / 'mc.db')), ('version', q("SELECT v FROM meta WHERE k='version'")[0][0]),
    ('mine_time', 'ticks=20/s, 효율·성급함·물속·공중 보정 없음, 0=즉시'),
    ('ore_gen', 'biomes NULL=오버월드 전체, y_peak=trapezoid 최다 높이, rarity=1/N 청크'),
    ('spawn_rule', '적대몹: 블록빛 0에서 스폰(오버월드), 낮 하늘빛 높으면 안 생김. 수동몹: 풀블록+빛 9 이상'),
    ('item_value', '원자재=수확등급 x 희소도, 조합=최저 재료비 x1.05, 출처 없으면 rarity'),
])
db.commit()
print(f'ore_gen {len(ore_rows)}, spawn {len(spawn_rows)}, mine_time {len(mine_rows)}, item_value {len(val)} -> {OUT}')
