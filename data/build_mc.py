# 바닐라 26.1.2 원본 -> mcdata/mc.db (items/blocks/mobs/recipes/tags/loot/meta)
# 원본: mcdata/gen(서버jar 데이터생성기 --reports --server), lang/ko_kr·en_us, raw/blocks.json(minecraft-data 경도·수확도구)
# 몹 체력·공격력은 생성기에 없음 -> MOB 표(위키 기준 보통 난이도) 직접 기입
# 실행: python3 data/build_mc.py  (표준 라이브러리만)
import json, sqlite3
from pathlib import Path

MC = Path(__file__).resolve().parents[1] / 'mcdata'
D = MC / 'gen/data/minecraft'
COMP = MC / 'gen/reports/minecraft/components/item'
OUT = MC / 'mc.db'
nid = lambda s: s.removeprefix('minecraft:')
ko = json.load(open(MC / 'lang/ko_kr.json'))
en = json.load(open(MC / 'lang/en_us.json'))
name = lambda kind, i, lang: lang.get(f'{kind}.minecraft.{i}') or lang.get(f'block.minecraft.{i}') or lang.get(f'item.minecraft.{i}')

# ---------- tags (중첩 # 풀기) ----------
raw_tags = {}
for kind in ('block', 'item', 'entity_type'):
    for f in (D / 'tags' / kind).rglob('*.json'):
        raw_tags[(kind, f.relative_to(D / 'tags' / kind).with_suffix('').as_posix())] = [
            v if isinstance(v, str) else v['id'] for v in json.load(open(f))['values']]
def members(kind, tag, seen=None):
    seen = seen or set()
    out = set()
    for v in raw_tags.get((kind, tag), []):
        if v.startswith('#'):
            t = nid(v[1:])
            if t not in seen:
                seen.add(t); out |= members(kind, t, seen)
        else:
            out.add(nid(v))
    return out
tags = {k: members(*k) for k in raw_tags}

# ---------- items ----------
TIER = {'wooden': 'wooden', 'stone': 'stone', 'copper': 'copper', 'iron': 'iron', 'golden': 'gold', 'diamond': 'diamond', 'netherite': 'netherite'}
TOOLS = ('pickaxe', 'axe', 'shovel', 'hoe')
item_rows = []
for f in sorted(COMP.glob('*.json')):
    i = f.stem
    c = json.load(open(f))['components']
    atk = spd = mine = tier = None
    for m in c.get('minecraft:attribute_modifiers', []):
        if nid(m['type']) == 'attack_damage': atk = 1 + m['amount']
        if nid(m['type']) == 'attack_speed': spd = round(4 + m['amount'], 2)
    suf = i.rsplit('_', 1)[-1]
    tool = c.get('minecraft:tool')
    if suf in TOOLS and tool:
        kind = 'tool'
        mine = next((r['speed'] for r in tool['rules'] if r.get('speed')), None)
        tier = TIER.get(i.split('_', 1)[0])
    elif suf in ('sword', 'mace', 'trident', 'spear') or i in ('mace', 'trident'):
        kind = 'weapon'; tier = TIER.get(i.split('_', 1)[0])
    elif 'minecraft:equippable' in c and any(s in i for s in ('helmet', 'chestplate', 'leggings', 'boots')):
        kind = 'armor'; tier = TIER.get(i.split('_', 1)[0])
    elif 'minecraft:food' in c:
        kind = 'food'
    elif (D / 'loot_table/blocks' / f'{i}.json').exists():
        kind = 'block'
    else:
        kind = 'item'
    item_rows.append((i, name('item', i, ko), name('item', i, en), kind, atk, spd, tier, mine,
                      c.get('minecraft:rarity', 'common'), c.get('minecraft:max_stack_size', 64)))

# ---------- blocks ----------
mcd = {b['name']: b for b in json.load(open(MC / 'raw/blocks.json'))}
block_ids = [nid(k) for k in json.load(open(MC / 'gen/reports/blocks.json'))]
block_rows = []
for b in block_ids:
    m = mcd.get(b, {})
    tool = next((t for t in TOOLS if b in tags.get(('block', f'mineable/{t}'), ())), None)
    needs = next((t for t in ('diamond', 'iron', 'stone') if b in tags.get(('block', f'needs_{t}_tool'), ())), None)
    req = int(bool(m.get('harvestTools')))
    block_rows.append((b, name('block', b, ko), name('block', b, en), tool, needs, m.get('hardness'), req))

# ---------- mobs ----------
# id: (체력, 근접공격력(보통)) 0=공격안함, None=특수(원거리/폭발 등 별도)
MOB = {'zombie': (20, 3), 'husk': (20, 3), 'drowned': (20, 3), 'zombie_villager': (20, 3), 'skeleton': (20, 4), 'stray': (20, 4),
       'bogged': (16, 4), 'creeper': (20, 43), 'spider': (16, 2), 'cave_spider': (12, 2), 'enderman': (40, 7), 'witch': (26, 6),
       'slime': (16, 4), 'magma_cube': (16, 6), 'phantom': (20, 3), 'pillager': (24, 4), 'vindicator': (24, 13), 'evoker': (24, 6),
       'ravager': (100, 12), 'blaze': (20, 6), 'ghast': (10, 17), 'wither_skeleton': (20, 8), 'piglin': (16, 8), 'piglin_brute': (50, 13),
       'zombified_piglin': (20, 8), 'hoglin': (40, 6), 'zoglin': (40, 6), 'guardian': (30, 6), 'elder_guardian': (80, 8), 'silverfish': (8, 1),
       'endermite': (8, 2), 'shulker': (30, 4), 'vex': (14, 9), 'breeze': (30, 1), 'warden': (500, 30), 'wither': (300, 8), 'ender_dragon': (200, 10),
       'creaking': (1, 3), 'parched': (16, 4),
       'cow': (10, 0), 'pig': (10, 0), 'chicken': (4, 0), 'sheep': (8, 0), 'rabbit': (3, 0), 'horse': (15, 0), 'donkey': (15, 0), 'mule': (15, 0),
       'llama': (15, 1), 'goat': (10, 2), 'mooshroom': (10, 0), 'wolf': (8, 4), 'cat': (10, 3), 'fox': (10, 2), 'polar_bear': (30, 6),
       'bee': (10, 2), 'panda': (20, 6), 'iron_golem': (100, 21), 'snow_golem': (4, 0), 'villager': (20, 0), 'wandering_trader': (20, 0),
       'squid': (10, 0), 'glow_squid': (10, 0), 'cod': (3, 0), 'salmon': (3, 0), 'turtle': (30, 0), 'dolphin': (10, 3), 'axolotl': (14, 2),
       'frog': (10, 0), 'camel': (32, 0), 'sniffer': (14, 0), 'armadillo': (12, 0), 'bat': (6, 0), 'parrot': (6, 0), 'allay': (20, 0),
       'strider': (20, 0), 'ocelot': (10, 0), 'happy_ghast': (20, 0), 'nautilus': (15, 3)}
mob_rows = []
for e in json.load(open(MC / 'raw/entities.json')):
    if e.get('type') not in ('hostile', 'passive', 'animal', 'water_creature', 'ambient', 'mob') and e['name'] not in MOB:
        continue
    i = e['name']
    h, a = MOB.get(i, (None, None))
    mob_rows.append((i, name('entity', i, ko), name('entity', i, en), h, a, e.get('category')))

# ---------- recipes ----------
STATION = {'smelting': 'furnace', 'blasting': 'blast_furnace', 'smoking': 'smoker', 'campfire_cooking': 'campfire', 'stonecutting': 'stonecutter'}
def alts(x):
    if isinstance(x, list):
        return sorted({a for y in x for a in alts(y)})
    if isinstance(x, dict):
        x = x.get('item') or ('#' + x['tag'] if 'tag' in x else None)
        if x is None: return []
    return sorted(members('item', nid(x[1:]))) if x.startswith('#') else [nid(x)]
rec_rows = []
for f in sorted((D / 'recipe').glob('*.json')):
    r = json.load(open(f))
    ty = nid(r['type'])
    res = r.get('result')
    if not isinstance(res, dict): continue
    ing = None
    if ty == 'crafting_shaped':
        cnt = {}
        for row in r['pattern']:
            for ch in row:
                if ch != ' ': cnt[ch] = cnt.get(ch, 0) + 1
        ing = [{'any': alts(r['key'][k]), 'n': n} for k, n in cnt.items()]
        big = len(r['pattern']) > 2 or max(len(x) for x in r['pattern']) > 2
        st = 'crafting_table' if big else 'inventory'
    elif ty == 'crafting_shapeless':
        g = {}
        for x in r['ingredients']:
            k = tuple(alts(x)); g[k] = g.get(k, 0) + 1
        ing = [{'any': list(k), 'n': n} for k, n in g.items()]
        st = 'crafting_table' if len(r['ingredients']) > 4 else 'inventory'
    elif ty in STATION:
        ing = [{'any': alts(r['ingredient']), 'n': 1}]
        st = STATION[ty]
    elif ty == 'smithing_transform':
        ing = [{'any': alts(r[k]), 'n': 1} for k in ('template', 'base', 'addition') if k in r]
        st = 'smithing_table'
    else:
        continue
    if any(not s['any'] for s in ing): continue
    rec_rows.append((f.stem, ty, nid(res['id']), res.get('count', 1), st, json.dumps(ing)))

# ---------- loot (블록·몹 드롭 평탄화) ----------
def walk(e, cond):
    t = nid(e.get('type', ''))
    c = cond + [nid(x.get('condition', '')) + (':' + json.dumps(x) if 'silk_touch' in json.dumps(x) else '') for x in e.get('conditions', [])]
    if t == 'item':
        mn = mx = 1
        for fn in e.get('functions', []):
            if nid(fn.get('function', '')) == 'set_count':
                n = fn['count']
                mn, mx = (n, n) if isinstance(n, (int, float)) else (n.get('min', 1), n.get('max', 1))
        yield nid(e['name']), mn, mx, ' '.join(c)
    for ch in e.get('children', []):
        yield from walk(ch, c)
loot_rows = []
for sub in ('blocks', 'entities'):
    for f in sorted((D / 'loot_table' / sub).glob('*.json')):
        d = json.load(open(f))
        for p in d.get('pools', []):
            pc = [nid(x.get('condition', '')) for x in p.get('conditions', [])]
            for e in p.get('entries', []):
                for it, mn, mx, c in walk(e, pc):
                    loot_rows.append((f'{sub}/{f.stem}', it, mn, mx, c))

# ---------- 저장 ----------
OUT.unlink(missing_ok=True)
db = sqlite3.connect(OUT)
db.executescript('''
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE items (id TEXT PRIMARY KEY, ko TEXT, en TEXT, kind TEXT, attack REAL, attack_speed REAL, tool_tier TEXT, mine_speed REAL, rarity TEXT, stack INTEGER);
CREATE TABLE blocks (id TEXT PRIMARY KEY, ko TEXT, en TEXT, tool TEXT, needs TEXT, hardness REAL, requires INTEGER);
CREATE TABLE mobs (id TEXT PRIMARY KEY, ko TEXT, en TEXT, health REAL, attack REAL, category TEXT);
CREATE TABLE recipes (id TEXT PRIMARY KEY, type TEXT, result TEXT, count INTEGER, station TEXT, ingredients TEXT);
CREATE TABLE tags (kind TEXT, tag TEXT, member TEXT);
CREATE TABLE loot (source TEXT, item TEXT, min REAL, max REAL, cond TEXT);
CREATE INDEX ix_rec ON recipes(result);
CREATE INDEX ix_tag ON tags(kind, tag);
''')
db.executemany('INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?)', item_rows)
db.executemany('INSERT INTO blocks VALUES (?,?,?,?,?,?,?)', block_rows)
db.executemany('INSERT INTO mobs VALUES (?,?,?,?,?,?)', mob_rows)
db.executemany('INSERT INTO recipes VALUES (?,?,?,?,?,?)', rec_rows)
db.executemany('INSERT INTO tags VALUES (?,?,?)', [(k if k != 'block' else 'block', t, m) for (k, t), ms in tags.items() for m in sorted(ms)])
db.executemany('INSERT INTO loot VALUES (?,?,?,?,?)', loot_rows)
db.executemany('INSERT INTO meta VALUES (?,?)', [('version', '26.1.2'), ('src', 'vanilla server.jar datagen + ko_kr/en_us + minecraft-data blocks'),
                                                 ('mobs', '체력·공격력 수기(위키, 보통 난이도)')])
db.commit()
print(f'items {len(item_rows)} blocks {len(block_rows)} mobs {len(mob_rows)} recipes {len(rec_rows)} loot {len(loot_rows)} -> {OUT}')
