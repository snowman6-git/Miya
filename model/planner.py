"""방법(VIA) 후보 생성기: 목표+상태 → 방법별 단계열·추정시간. 사실(레시피·채굴시간)만 씀, 선택은 모델
서빙에서도 같은 로직(TS/Rust 포팅 대상). 학습데이터 생성시엔 숨은 참값(true_ms, true_ok)도 만들어 정답 라벨로 씀
단계 = dict(type, target, cnt, tool, need[], done, at)
"""
import itertools, json, math, os, random, re, sqlite3
from functools import lru_cache

MCDB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../mcdata/mc.db")
MCX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data/mcx.db")
TIERS = ["hand", "wooden", "stone", "copper", "iron", "diamond", "netherite"]  # golden 제외(내구도)
TIER_RANK = {"hand": 0, None: 0, "wooden": 1, "golden": 1, "stone": 2, "copper": 2, "iron": 3, "diamond": 4, "netherite": 5}
WALK = 0.25  # s/칸
WOOD_SP = ["oak", "spruce", "birch", "jungle", "acacia", "cherry", "dark_oak", "pale_oak", "mangrove", "crimson", "warped"]
WOOD = {f"{s}_{k}": f"oak_{'planks' if k == 'planks' else 'log'}" for s in WOOD_SP for k in ("log", "stem", "planks")
        if (k == "stem") == (s in ("crimson", "warped"))}


def wood(d, keep=(), near=False):
    """목재 종 통합(판자·막대·작업대 레시피 종 무관) → oak_* 로 계산. inv=합, near=최소거리. keep=종 지정 GOAL"""
    o = {}
    for k, v in d.items():
        k2 = k if k in keep else WOOD.get(k, k)
        if near:
            o[k2] = v if o.get(k2) is None else (o[k2] if v is None else min(o[k2], v))
        else:
            o[k2] = o.get(k2, 0) + v
    return o
# 채집 원천: 아이템 → (블록/몹, 작업타입)
SRC = {"oak_log": ("oak_log", "log"), "cobblestone": ("stone", "mine"), "dirt": ("dirt", "dig"), "sand": ("sand", "dig"),
       "gravel": ("gravel", "dig"), "coal": ("coal_ore", "mine"), "raw_iron": ("iron_ore", "mine"), "raw_gold": ("gold_ore", "mine"),
       "raw_copper": ("copper_ore", "mine"), "diamond": ("diamond_ore", "mine"), "redstone": ("redstone_ore", "mine"),
       "lapis_lazuli": ("lapis_ore", "mine"), "obsidian": ("obsidian", "mine"), "flint": ("gravel", "dig"),
       "wheat_seeds": ("short_grass", "farm"), "sugar_cane": ("sugar_cane", "farm"), "wheat": ("wheat", "farm"),
       "beef": ("mob:cow", "hunt"), "porkchop": ("mob:pig", "hunt"), "chicken": ("mob:chicken", "hunt"), "mutton": ("mob:sheep", "hunt"),
       "leather": ("mob:cow", "hunt"), "white_wool": ("mob:sheep", "shear"), "string": ("mob:spider", "combat"), "bone": ("mob:skeleton", "combat"),
       "rotten_flesh": ("mob:zombie", "combat"), "andesite": ("andesite", "mine"), "clay_ball": ("clay", "dig")}
SRC.update({l: (l, "log") for l in WOOD if l.endswith(("_log", "_stem"))})
PREF = ["raw_iron", "raw_gold", "raw_copper", "beef", "oak_log", "oak_planks", "cobblestone", "iron_ingot", "stick", "coal", "white_wool", "sand", "gold_ingot", "copper_ingot"]
STATION_T = {"crafting_table": "craft", "inventory": "craft", "furnace": "furnace", "smoker": "smoker", "blast_furnace": "blast_furnace", "campfire": "campfire"}
FUEL = {"coal": 8, "charcoal": 8, "oak_log": 1.5, "oak_planks": 1.5, "stick": 0.5, "lava_bucket": 100}
MEATS = ["beef", "porkchop", "chicken", "mutton"]
COOK = {"beef": "cooked_beef", "porkchop": "cooked_porkchop", "chicken": "cooked_chicken", "mutton": "cooked_mutton"}


@lru_cache(1)
def db():
    c = sqlite3.connect(MCDB)
    rec = {}
    for rid, ty, res, cnt, st, ing in c.execute("select id,type,result,count,station,ingredients from recipes"):
        if ty in ("stonecutting", "smithing_transform") or not ing:
            continue
        rec.setdefault(res, []).append({"id": rid, "type": ty, "cnt": cnt or 1, "st": st, "ing": json.loads(ing)})
    blk = {b: (tool, needs or ("wooden" if req else None), hard) for b, tool, needs, hard, req in c.execute("select id,tool,needs,hardness,requires from blocks")}
    x = sqlite3.connect(MCX)
    mt = {}
    for b, tool, tier, ticks, drops in x.execute("select block,tool,tier,ticks,drops from mine_time"):
        mt.setdefault(b, []).append((tool, tier, ticks, drops))
    val = dict(x.execute("select item,v from item_value"))
    ko = dict(c.execute("select id,ko from items"))
    ko.update({f"mob:{i}": k for i, k in c.execute("select id,ko from mobs")})
    mob = {i: (h, a) for i, h, a in c.execute("select id,health,attack from mobs")}
    wpn = {i: (a or 1, s or 4) for i, a, s in c.execute("select id,attack,attack_speed from items where kind in ('weapon','tool')")}
    return {"rec": rec, "blk": blk, "mt": mt, "val": val, "ko": ko, "mob": mob, "wpn": wpn}


@lru_cache(1)
def ore_gen():
    x = sqlite3.connect(MCX)
    return x.execute("select block,count,rarity,size,air_discard,dist,y_min,y_max,y_peak from ore_gen where dim='overworld' and biomes is null").fetchall()


def ore_dens(block, y):
    """y 한 층의 기대 광석 수 (청크당, ore_gen 사실 기반). trapezoid=삼각(peak), uniform=균등"""
    d = 0.0
    for b, c, rar, size, air, dist, lo, hi, pk in ore_gen():
        if b != block or not lo <= y <= hi or hi <= lo:
            continue
        n = c / (rar or 1) * size * (1 - (air or 0) * 0.5)  # 공기 접한 광석 버림 → 굴 파기 기준 감소
        if dist == "trapezoid":
            pk = pk if pk is not None else (lo + hi) / 2
            n *= 2 / (hi - lo) * ((y - lo) / max(1, pk - lo) if y <= pk else (hi - y) / max(1, hi - pk))
        else:
            n /= hi - lo
        d += n
    return d


def ore_y(block, cur_y):
    """계단굴 목표 높이: 현재 높이 이하에서 밀도/거리 최적. 해당 광석 정보 없으면 None"""
    if not any(r[0] == block for r in ore_gen()):
        return None
    ys = range(-58, int(cur_y) + 1)  # -59 이하 기반암·용암호수
    return max(ys, key=lambda y: ore_dens(block, y) / (1 + (cur_y - y) / 64), default=None)


def ko(i):
    return db()["ko"].get(i, i)


def pick(any_list, inv):
    for a in any_list:
        if inv.get(a, 0) > 0:
            return a
    for p in PREF:
        if p in any_list:
            return p
    v = db()["val"]
    return min(any_list, key=lambda a: v.get(a, 1e9))


def best_tool(inv, kind):
    """kind: pickaxe/axe/shovel. 인벤 최고 티어"""
    best = "hand"
    for t in TIERS[1:]:
        if inv.get(f"{t}_{kind}", 0) > 0:
            best = t
    return best


def mine_ticks(block, tool_id):
    rows = db()["mt"].get(block, [])
    for tool, tier, ticks, drops in rows:
        if tool == tool_id:
            return ticks, drops
    for tool, tier, ticks, drops in rows:
        if tool == "hand":
            return ticks, drops
    return 20, 1


class Plan:
    def __init__(self, inv, world, opt, bulk=None):
        self.inv = dict(inv)
        self.bulk = dict(bulk or {})  # 1차 총수요: 첫 채집·제작때 한꺼번에
        self.demand = {}
        self.use = {}  # 방법 전체에서 쓰는 템(보유분 포함) → 인벤 정리시 필요템 판단
        self.w = world
        self.o = opt  # tool_up, fuel, station
        self.steps = []
        self.ms = 0.0
        self.risk = 0.0
        self.via = []
        self.making = set()
        self.why, self.par = {}, []  # why[item][요구한 상위템] = 개수 → 스텝 이유 표기용

    def add(self, typ, target, cnt, ms, tool=None, need=(), at=None, **kw):  # kw: 봇 실행용(item=채집 드롭, src/fuel=화로)
        if self.steps and self.steps[-1]["type"] == typ and self.steps[-1]["target"] == target and typ not in ("craft",):
            s = self.steps[-1]
            s["cnt"] += cnt
            s["done"] = f"inv[{target}]>={self.inv.get(target, 0)}"
        else:
            self.steps.append({"type": typ, "target": target, "cnt": cnt, "tool": tool, "need": list(need), "at": at,
                               "done": f"inv[{target}]>={self.inv.get(target, 0)}", **kw})
        self.ms += ms

    def station(self, st):
        """작업대/화로 확보. 설치된것(거리) vs 인벤 vs 제작"""
        if st in ("inventory", None):
            return None
        placed = self.w["placed"].get(st)
        if st in self.w.setdefault("mine", set()):
            return "방금 설치"
        if placed is not None and self.o.get("station") != "new":
            self.ms += placed * WALK * 2000  # 왕복: 멀면(원정중) 새로 만드는게 나음
            if "reuse" not in self.via:
                self.via.append(f"reuse:{st}")
            return f"설치됨 {placed}칸"
        if self.inv.get(st, 0) > 0:
            self.add("place", st, 1, 1000)
            self.w["mine"].add(st)
            self.inv[st] -= 1
            return "인벤→설치"
        self.obtain(st, 1)
        self.add("place", st, 1, 1000)
        self.w["mine"].add(st)
        self.inv[st] -= 1
        return "새로 제작"

    def ensure_tool(self, kind, need_tier):
        have = best_tool(self.inv, kind)
        want = need_tier
        if self.o.get("tool_up") == "stone" and TIER_RANK[want] < 2 and kind in ("pickaxe", "axe"):
            want = "stone"
        if self.o.get("tool_up") == "none" and need_tier in ("hand", None):
            return have
        if TIER_RANK[have] >= TIER_RANK[want]:
            return have
        if want == "hand":
            return have
        tid = f"{want}_{kind}"
        if tid in self.making:  # 만드는 중인 도구 재료 채집 → 필요최소로
            if TIER_RANK[have] >= TIER_RANK[need_tier or "hand"]:
                return have
            self.ms += 1e6
            return have
        self.making.add(tid)
        self.obtain(tid, 1)
        self.making.discard(tid)
        self.via.append(f"via:{tid}")
        return want

    def gather(self, item, n):
        b, typ = SRC.get(item) or (item, "combat" if db()["mob"].get(item[4:], (0, 0))[1] else "hunt")  # mob:X GOAL = n마리 처치
        if b.startswith("mob:"):
            m = b[4:]
            hp, atk = db()["mob"].get(m, (10, 0))
            wt = best_tool(self.inv, "sword")
            dmg = db()["wpn"].get(f"{wt}_sword", (1, 4))[0] if wt != "hand" else 1
            dist = self.w["near"].get(b)
            kills = n if item == b else math.ceil(n / 1.5)
            per = (dist if dist else 0) * WALK * 1000 + math.ceil(hp / dmg) * 700 + 3000
            if dist is None:
                self.add("expedition", b, 1, 90000)
                self.risk += 0.35
            self.add(typ, b, kills, kills * per, tool=f"{wt}_sword" if wt != "hand" else "hand", item=item)
            self.risk += 0.02 * kills + (0.1 if atk and atk > 0 else 0)
            self.inv[item] = self.inv.get(item, 0) + n
            return
        tool, needs, hard = db()["blk"].get(b, ("pickaxe", None, 1.5))
        kind = tool if tool in ("pickaxe", "axe", "shovel") else None
        tier = "hand"
        if kind:
            h0 = self.inv.get(item, 0)
            tier = self.ensure_tool(kind, needs or "hand")
            n += max(0, h0 - self.inv.get(item, 0))  # 도구 제작이 같은 재료 소모(조약돌 6 → 돌곡 3) → 그만큼 더 캠
        tid = f"{tier}_{kind}" if kind and tier != "hand" else "hand"
        ticks, _ = mine_ticks(b, tid)
        dist = self.w["near"].get(b)
        if dist is None:  # 안보임: 광석(ore_gen)은 계단굴로 찾음 → 저위험(깊을수록↑), 돌·흙은 발밑, 지상 자원(원목·모래 등)만 원정 고위험
            self.add("expedition", b, 1, 120000)
            oy = ore_y(b, 64)
            self.risk += 0.05 if b in ("stone", "dirt", "deepslate") else (0.1 if oy >= 0 else 0.2) if oy is not None else 0.3
            dist = 12
        per = ticks * 50 + 600 + min(dist, 40) * WALK * 1000 / max(1, n) * 1.5
        self.add(typ, b, n, n * per, tool=tid, need=[f"도구:{tid}"] if tid != "hand" else [], item=item)
        self.inv[item] = self.inv.get(item, 0) + n

    def fuel_for(self, k):
        need_units = k
        order = {"coal": ["coal", "charcoal"], "plank": ["oak_planks"], "log": ["oak_log"], "lava": ["lava_bucket"]}[self.o.get("fuel", "coal")]
        for f in list(FUEL):
            if self.inv.get(f, 0) * FUEL[f] >= need_units and (f in order or self.o.get("fuel") == "any"):
                self.inv[f] -= math.ceil(need_units / FUEL[f])
                return f
        f = order[0]
        c = math.ceil(need_units / FUEL[f])
        if f == "lava_bucket":
            if self.w["near"].get("lava") is None:
                self.add("expedition", "lava", 1, 150000)
                self.risk += 0.3
            if self.inv.get("bucket", 0) == 0:
                sv, self.o = self.o, dict(self.o, fuel="coal")  # 양동이용 철 굽기는 석탄 (재귀 차단)
                self.obtain("bucket", 1)
                self.o = sv
            self.add("bucket", "lava", 1, 3000 + (self.w["near"].get("lava") or 20) * WALK * 1000)
            self.risk += 0.1
            self.via.append("fuel:lava")
            return f
        self.obtain(f, c)
        self.inv[f] -= c
        self.via.append(f"fuel:{f}")
        return f

    def obtain(self, item, n, depth=0):
        w = self.why.setdefault(item, {})
        w[self.par[-1] if self.par else None] = w.get(self.par[-1] if self.par else None, 0) + n
        self.par.append(item)
        try:
            self._obtain(item, n, depth)
        finally:
            self.par.pop()

    def _obtain(self, item, n, depth=0):
        self.use[item] = self.use.get(item, 0) + n
        have = self.inv.get(item, 0)
        if have >= n:
            return
        need = n - have
        self.demand[item] = self.demand.get(item, 0) + need
        if self.bulk.get(item, 0) > need:
            need = self.bulk.pop(item)
        else:
            self.bulk.pop(item, None)
        if depth > 8:
            self.ms += 1e6
            return
        rs = db()["rec"].get(item, [])
        crafts = [r for r in rs if r["type"].startswith("crafting")]
        smelts = [r for r in rs if r["type"] == "smelting"]
        if item in SRC and not (item in ("oak_planks",)) or item.startswith("mob:"):
            self.gather(item, need)
            return
        if smelts and item not in ("charcoal",) and (not crafts or item in ("iron_ingot", "gold_ingot", "copper_ingot", "glass", "stone") or item in COOK.values()):
            r = smelts[0]
            if item in COOK.values():
                raw = [m for m in MEATS if COOK[m] == item][0]
                src = raw
            else:
                pool = [a for r2 in smelts for a in r2["ing"][0]["any"]]
                src = next((a for a in pool if self.inv.get(a, 0) >= need), None) or next((a for a in pool if a in SRC), None) or pick(pool, self.inv)
            at = self.station("furnace")
            self.obtain(src, need, depth + 1)
            f = self.fuel_for(need)
            self.inv[src] = self.inv.get(src, 0) - need
            self.add("furnace", item, need, need * 10000 + 2000, need=[f"재료:{ko(src)} {need}", f"연료:{ko(f)}"], at=at, src=src, fuel=f)
            self.inv[item] = self.inv.get(item, 0) + need
            return
        if crafts:
            r = min(crafts, key=lambda r: 0 if all(any(self.inv.get(a, 0) > 0 for a in g["any"]) for g in r["ing"]) else 1)
            times = math.ceil(need / r["cnt"])
            at = self.station(r["st"])  # 작업대 먼저: 나중에 만들면 모아둔 재료(판자) 소모 → 부족
            used = []
            for g in r["ing"]:  # 확보 즉시 차감(예약): 뒤 재료(막대기)가 같은 판자 이중계산 → 판자 부족 no_material 버그
                a = pick(g["any"], self.inv)
                self.obtain(a, g["n"] * times, depth + 1)
                self.inv[a] = self.inv.get(a, 0) - g["n"] * times
                used.append((a, g["n"] * times))
            self.add("craft", item, times * r["cnt"], 800 * times + 500, need=[f"재료:{ko(a)} {k}" for a, k in used] + ([f"작업대"] if r["st"] == "crafting_table" else []), at=at)
            self.inv[item] = self.inv.get(item, 0) + times * r["cnt"]
            return
        self.ms += 1e6  # 못얻음
        self.inv[item] = n


GOAL_SETS = {"set:iron_armor": ["iron_helmet", "iron_chestplate", "iron_leggings", "iron_boots"],
             "set:diamond_armor": ["diamond_helmet", "diamond_chestplate", "diamond_leggings", "diamond_boots"],
             "set:golden_armor": ["golden_helmet", "golden_chestplate", "golden_leggings", "golden_boots"],
             "set:leather_armor": ["leather_helmet", "leather_chestplate", "leather_leggings", "leather_boots"],
             "set:stone_tools": ["stone_pickaxe", "stone_axe", "stone_sword", "stone_shovel"],
             "set:iron_tools": ["iron_pickaxe", "iron_axe", "iron_sword", "iron_shovel"],
             "set:wooden_tools": ["wooden_pickaxe", "wooden_axe", "wooden_sword", "wooden_shovel"],
             "set:diamond_tools": ["diamond_pickaxe", "diamond_axe", "diamond_sword", "diamond_shovel"],
             "grp:log": ["oak_log"], "grp:planks": ["oak_planks"], "grp:iron": ["raw_iron"], "grp:gold": ["raw_gold"], "grp:copper": ["raw_copper"],
             "grp:meat": ["cooked_beef"], "grp:food": ["cooked_beef"]}

OPTS = [{"tool_up": tu, "fuel": f, "station": s} for tu, f, s in itertools.product(["min", "stone"], ["coal", "log", "plank", "lava"], ["reuse", "new"])]


def methods(goal, n, inv, world, k=6):
    """→ [{via, steps, est_ms, risk}] 중복 제거. 서빙·학습 공용"""
    items = GOAL_SETS.get(goal, [goal])
    out, seen = [], set()
    for o in OPTS:
        bulk = None
        for _ in range(2):
            w = {"placed": dict(world.get("placed", {})), "near": world.get("near", {})}
            p = Plan(inv, w, o, bulk)
            for it in items:
                p.obtain(it, n if len(items) == 1 else 1)
            bulk = {k: v for k, v in p.demand.items() if not k.endswith(("_pickaxe", "_axe", "_shovel", "_sword", "crafting_table", "furnace"))}
        if p.ms >= 1e6:
            continue
        key = tuple((s["type"], s["target"], s["cnt"]) for s in p.steps)
        if key in seen:
            continue
        seen.add(key)
        via = ",".join(dict.fromkeys(p.via)) or "direct"
        for s in p.steps:  # 이유: 이 템을 요구한 상위템·개수 (None=최종 목표)
            s["for"] = {k or "goal": v for k, v in p.why.get(s.get("item") or s["target"], {}).items()}
        out.append({"via": via, "steps": p.steps, "est_ms": int(p.ms), "risk": round(min(0.9, p.risk), 3), "use": p.use})
    out.sort(key=lambda m: m["est_ms"] * (1 + m["risk"]))
    vs = set()  # 같은 via(단계 수만 다름) = 싼 것 1개 → 보기 중복·QED 같은방법 "바꿈" 오표기 방지
    return [m for m in out if not (m["via"] in vs or vs.add(m["via"]))][:k]


TYPE_KO = {"mine": "채광", "log": "벌목", "dig": "삽질", "farm": "농사", "craft": "제작", "furnace": "화로", "place": "설치", "hunt": "사냥",
           "combat": "전투", "expedition": "원정", "bucket": "양동이", "shear": "가위", "smoker": "훈연기", "campfire": "모닥불"}


def step_text(s):
    t = f"{TYPE_KO.get(s['type'], s['type'])} {ko(s['target'])} {s['cnt']}"
    if s.get("tool") and s["tool"] != "hand":
        t += f"({ko(s['tool'])})"
    if s.get("at"):
        t += f"[{s['at']}]"
    return t


def method_text(m, qed=None, maxstep=5):
    st = [step_text(s) for s in m["steps"]]
    body = " → ".join(st[:maxstep]) + (f" …+{len(st) - maxstep}" if len(st) > maxstep else "")
    t = f"{m['via']} | {body} | 예상 {m['est_ms'] // 1000}초 위험 {int(m['risk'] * 100)}%"
    if qed:
        t += f" | 경험 {qed['n']}회 성공 {int(qed['ok'] * 100)}% 평균 {qed['avg_ms'] // 1000}초"
        if qed.get("recent_fail"):
            t += f" 최근실패 {qed['recent_fail']}회({qed.get('fail', '')})"
    else:
        t += " | 경험 없음"
    return t


# ---------- 인벤 정리 (tidy): 문맥 문장 학습·서빙 공용. 판단(유지/버리기/보관)은 모델 ----------
TIDY_SIT = ["인벤 가득", "작업 전", "원정 복귀"]
_KIND = [("도구", r"_(pickaxe|axe|shovel|hoe|sword)$|^(shears|bucket|water_bucket|lava_bucket|fishing_rod|flint_and_steel|bow|crossbow|shield)$"),
         ("갑옷", r"_(helmet|chestplate|leggings|boots)$|^elytra$"),
         ("음식", r"(beef|porkchop|chicken|mutton|rabbit|cod|salmon|bread|apple|carrot|potato|melon_slice|cookie|pie|stew|berries)$"),
         ("블럭", r"^(cobblestone|dirt|stone|granite|diorite|andesite|cobbled_deepslate|deepslate|tuff|gravel|sand|netherrack|calcite|grass_block)$|_(planks|log)$")]
FILLER = r"^(cobblestone|dirt|granite|diorite|andesite|cobbled_deepslate|tuff|netherrack|stone)$"


def kind_of(item):
    return next((k for k, rx in _KIND if re.search(rx, item)), "재료")


def space_of(steps, inv):
    """작업중 새로 생길 템 칸수: 얻는 스텝 대상 중 인벤에 없는 것 (스택 64 기준)"""
    got = {}
    for s in steps:
        if s["type"] not in ("place", "expedition"):
            got[s["target"]] = got.get(s["target"], 0) + s["cnt"]
    return sum(math.ceil(c / 64) for t, c in got.items() if t not in inv)


def tidy_ctx(item, n, v, need, goal_ko, free, chest_d, sit, filler, space):
    """v=개당 가치, need=현재 GOAL에 쓸 개수, chest_d=내 상자 거리(None=없음), filler=쌓기용 블럭 총수, space=작업 필요칸"""
    return (f"아이템: {ko(item)} {n}개 | 종류: {kind_of(item)} | 가치 개당 {v:.1f} 합 {v * n:.0f} | GOAL: " + (f"{goal_ko} 필요 {need}개" if goal_ko else "없음") +
            f" | 빈칸 {free}/36 작업 필요칸 {space} | 내 상자: " + (f"{chest_d}칸" if chest_d is not None else "없음") + f" | 쌓기용 블럭 {filler}개 | 상황: {sit}")
