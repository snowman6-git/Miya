"""Miya-0.1a 학습데이터 생성 (구 데이터셋 미사용). 실발화(chat_raw) 원문은 평가셋 전용 → 학습에서 정확일치 제외
kind=turn: 발화 이해 (act/type/query/hint + 구간 + 링크)
kind=plan: 방법 선택 (숨은 참값 시뮬 + QED 기록 노출) + 가치 타깃
kind=prio: 위협·상태 이벤트 → 우선순위
"""
import json, math, os, random, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model"))
import catalog as C  # noqa: E402
import planner as P  # noqa: E402

H = os.path.dirname(os.path.abspath(__file__))

ACTS = ["목표 실행", "질문 답하기", "되묻기", "멈춤", "재개", "긍정 대답", "부정 대답", "잡담", "욕설", "위험 경고", "지적·조언"]
TYPES = {"craft": "제작", "mine": "채광", "log": "벌목", "dig": "삽질", "farm": "농사", "furnace": "굽기(화로)", "hunt": "사냥", "combat": "전투",
         "bucket": "양동이", "store": "상자에 넣기·정리", "retrieve": "꺼내오기", "give": "주기", "drop": "버리기", "equip": "들기·입기",
         "unequip": "벗기", "eat": "먹기", "place": "설치", "break": "설치물 부수기·회수", "come": "오기", "follow": "따라가기", "goto": "이동",
         "collect": "떨어진 템 줍기", "shelter": "숨기", "sleep": "자기", "flee": "도망", "pillar": "블럭 쌓기", "tunnel": "굴 파기",
         "guard": "지키기", "auto": "자율모드", "build": "건축", "enchant": "마법부여", "fish": "낚시", "trade": "거래", "ranged": "원거리 공격",
         "boat": "보트", "minecart": "마인카트", "check": "화로·상자 확인", "move": "상대 이동(앞·위·아래·점프·달리기)", "mark": "장소 지정(여기가 집 등)"}
TYPE_KEYS = list(TYPES)
QUERIES = {"inv": "인벤 내용", "have": "특정 템 보유·개수", "hp": "체력", "food": "배고픔", "status": "상태 전체", "pos": "내 위치", "doing": "하는 일",
           "recipe": "만드는 법", "can_make": "만들 수 있는지", "can_do": "할 수 있는지·가능여부", "near": "주변 탐색", "time": "시간·낮밤",
           "chest": "상자 내용", "furnace": "화로 내용·진행", "abilities": "할 수 있는 것", "where_player": "말한 사람 위치", "where_thing": "물건·장소 위치",
           "progress": "작업 진행"}
Q_KEYS = list(QUERIES)
HINTS = {"slow": "느림(더 빠른 도구·방법)", "wrong": "대상·방법이 틀림", "short": "개수·재료 부족", "danger": "위험함", "done_claim": "했다더니 안됨"}
H_KEYS = list(HINTS)
LABELS = ["대상", "개수", "도구", "사람", "좌표", "장소", "거리"]
LI = {l: i for i, l in enumerate(LABELS)}
PLAYERS = ["player1", "player2", "Claude", "orinthia", "steve", "민수", "지훈", "Notch", "dog_1004", "kimchi77"]

# 아이템 풀
CRAFT_T = ["iron_pickaxe", "stone_pickaxe", "wooden_pickaxe", "diamond_pickaxe", "iron_sword", "stone_sword", "diamond_sword", "wooden_sword",
           "iron_axe", "stone_axe", "wooden_axe", "diamond_axe", "iron_shovel", "stone_shovel", "iron_hoe", "iron_helmet", "iron_chestplate",
           "iron_leggings", "iron_boots", "diamond_helmet", "diamond_chestplate", "diamond_leggings", "diamond_boots", "golden_helmet",
           "golden_pickaxe", "golden_sword", "leather_helmet", "copper_pickaxe", "copper_sword", "netherite_pickaxe", "netherite_sword",
           "crafting_table", "furnace", "chest", "torch", "stick", "oak_planks", "bucket", "shield", "bread", "white_bed", "ladder", "oak_door",
           "bow", "arrow", "blast_furnace", "smoker", "campfire", "oak_boat", "minecart", "rail", "glass_pane", "stone_bricks", "iron_bars",
           "set:iron_armor", "set:diamond_armor", "set:golden_armor", "set:leather_armor", "set:iron_tools", "set:stone_tools", "set:diamond_tools",
           "golden_boots", "diamond_shovel", "stone_hoe", "wooden_shovel", "barrel", "composter", "anvil", "shears", "flint_and_steel", "compass",
           "clock", "fishing_rod", "lantern", "cake", "paper", "book", "enchanting_table"] + ["iron_chestplate", "set:iron_armor", "diamond_chestplate", "set:diamond_armor", "golden_chestplate"] * 3  # 갑옷(흉갑) vs 풀셋 대비
GATHER_T = {"grp:log": "log", "oak_log": "log", "birch_log": "log", "spruce_log": "log", "acacia_log": "log", "jungle_log": "log", "cherry_log": "log", "dark_oak_log": "log", "mangrove_log": "log", "cobblestone": "mine", "stone": "mine", "coal": "mine",
            "raw_iron": "mine", "grp:iron": "mine", "iron_ore": "mine", "diamond": "mine", "grp:gold": "mine", "raw_gold": "mine", "redstone": "mine",
            "lapis_lazuli": "mine", "obsidian": "mine", "grp:copper": "mine", "andesite": "mine", "deepslate": "mine", "emerald": "mine",
            "dirt": "dig", "sand": "dig", "gravel": "dig", "clay_ball": "dig", "grass_block": "dig", "wheat_seeds": "farm", "wheat": "farm",
            "sugar_cane": "farm", "carrot": "farm", "potato": "farm", "bamboo": "farm"}
HUNT_T = ["mob:cow", "mob:pig", "mob:chicken", "mob:sheep", "mob:rabbit"] * 3 + ["mob:salmon", "mob:cod", "mob:squid", "mob:goat", "mob:tropical_fish"] * 2  # 물고기 잡아 = 사냥(낚시는 낚시/낚아만)
MEAT_T = ["grp:meat", "beef", "porkchop", "chicken", "mutton", "grp:food", "leather", "white_wool", "feather", "salmon", "cod"]
HOSTILE = ["mob:zombie", "mob:skeleton", "mob:creeper", "mob:spider", "mob:enderman", "mob:witch", "mob:slime", "mob:drowned", "mob:husk",
           "mob:pillager", "mob:phantom", "mob:cave_spider", "mob:blaze", "mob:ender_dragon", "mob:wither"]
SMELT_T = ["raw_iron", "grp:iron", "grp:meat", "beef", "porkchop", "sand", "cobblestone", "raw_gold", "chicken", "oak_log", "potato", "clay_ball", "grp:gold"]
MISC = ["cobblestone", "dirt", "oak_log", "stick", "torch", "coal", "iron_ingot", "raw_iron", "diamond", "cooked_beef", "bread", "oak_planks",
        "wheat_seeds", "andesite", "sand", "gravel", "rotten_flesh", "leather", "bone", "string", "gold_ingot", "stone_pickaxe", "iron_pickaxe",
        "iron_sword", "stone_axe", "wooden_pickaxe", "shield", "bow", "arrow", "iron_helmet", "iron_chestplate", "grp:meat", "grp:food",
        "grp:iron", "grp:log", "crafting_table", "furnace", "chest", "bucket", "water_bucket", "lava_bucket", "bamboo", "glass", "diorite", "granite",
        "birch_log", "spruce_log", "acacia_log", "jungle_log", "cherry_log", "dark_oak_log", "mangrove_log", "birch_planks", "spruce_planks"]
EQUIP_T = ["iron_pickaxe", "stone_pickaxe", "wooden_pickaxe", "diamond_pickaxe", "iron_sword", "stone_sword", "stone_axe", "iron_axe", "shield",
           "torch", "bow", "iron_helmet", "iron_chestplate", "iron_leggings", "iron_boots", "diamond_chestplate", "netherite_leggings",
           "set:iron_armor", "grp:armor", "grp:sword", "grp:pickaxe", "grp:axe", "cobblestone", "coal", "golden_helmet"] + ["iron_chestplate", "set:iron_armor"] * 2
PLACE_T = ["crafting_table", "furnace", "chest", "torch", "white_bed", "cobblestone", "dirt", "oak_door", "campfire", "ladder"]


def ko(i):
    return C.ko_names().get(i, i)


class U:
    """발화 조립기: 문자열 조각 + 구간 기록"""

    def __init__(self):
        self.t = ""
        self.sp = []  # (s,e,label,item)
        self.pair = []  # (개수 idx, 대상 idx) GLiREL 짝
        self._pend = None  # 대상 앞에 온 개수

    def add(self, s, label=None, item=None):
        if not s:
            return self
        if self.t and not self.t.endswith(" ") and not s.startswith(" "):
            self.t += " "
        a = len(self.t) + (1 if s.startswith(" ") else 0)
        self.t += s
        if label:
            self._rec(a, label, item)
        return self

    def _rec(self, a, label, item):
        self.sp.append((a, len(self.t), label, item))
        k = len(self.sp) - 1
        if label == "개수":
            j = next((j for j in range(k - 1, -1, -1) if self.sp[j][2] in ("대상", "도구")), None)
            if j is not None and not any(p[1] == j for p in self.pair) and self.t[self.sp[j][1]:a].strip() in ("", ","):
                self.pair.append((k, j))
            else:
                self._pend = k
        elif label in ("대상", "도구") and self._pend is not None:
            self.pair.append((self._pend, k)); self._pend = None

    def glue(self, s, label=None, item=None):
        a = len(self.t)
        self.t += s
        if label:
            self._rec(a, label, item)
        return self


def pick_end(r, ends):
    return r.choice(ends)


E_CRAFT = ["만들어", "만들어줘", "만들어와", "만들자", "만들어봐", "만들어라", "만드셈", "만들셈", "제작해", "제작 ㄱ", "뽑아", "뽑자", "뽑아줘", "ㄱㄱ", "ㄱㄱㄱ", "고고",
           "만들어 줄래?", "만들어줄래", "좀 만들어", "만들어 ㄱㄱ", "만들어 주셈", "만들어주라", "하나 뽑아와", "제작 부탁", "만들래?", "만들어놔", "만들어 둬", "만들기"]
E_GATHER = ["캐와", "캐", "캐줘", "캐자", "캐와줘", "캐오셈", "캐 와", "파와", "채굴해", "모아와", "모아", "구해와", "가져와", "가온나", "구해온나", "캐러 가자",
            "캐올래?", "좀 캐와", "캐다줘", "캐와라", "파", "구해", "좀 구해와", "모아줘", "캐 ㄱㄱ", "캐오자", "캐와봐", "구하자", "캐 줄래"]
E_LOG = ["캐와", "베어와", "패와", "캐", "벌목해", "잘라와", "캐와줘", "해와", "구해와", "모아와", "캐자", "좀 캐와", "캐러 ㄱㄱ"]
E_DIG = ["파와", "캐와", "퍼와", "파", "삽질해", "모아와", "캐", "좀 파와"]
E_KILL = ["잡아", "죽여", "잡아와", "처리해", "때려", "공격해", "패", "족쳐", "잡자", "사냥해", "쳐", "공격", "잡아줘", "좀 잡아", "처치해", "없애", "해치워", "잡아죽여", "죽이자", "처리 ㄱㄱ", "잡으셈"]
E_GIVE = ["줘", "줘봐", "주셈", "주라", "줄래?", "내놔", "던져", "넘겨", "나한테 줘", "좀 줘", "줘라", "나줘", "나 줘", "주세여", "건네줘", "ㄱ"]
E_DROP = ["버려", "버려줘", "버리셈", "던져버려", "다 버려", "치워", "버리자", "갖다 버려"]
E_EQUIP = ["들어", "들어봐", "껴", "착용해", "장착해", "입어", "써", "손에 들어", "꺼내 들어", "끼셈", "장착", "들고 있어"]
E_PLACE = ["설치해", "깔아", "놔", "놓아", "설치", "깔아줘", "놔줘", "박아", "설치하", "둬"]
E_SMELT = ["구워", "구워와", "구워줘", "녹여", "제련해", "구워라", "구워놔", "좀 구워", "구워 ㄱㄱ", "굽자", "익혀"]
E_STORE = ["넣어", "넣어놔", "넣어줘", "보관해", "집어넣어", "넣어둬", "넣자", "넣셈"]
E_TAKE = ["꺼내", "꺼내와", "빼", "빼와", "가져와", "꺼내줘", "꺼네", "빼줘"]


VERBS_OLD = {"craft": E_CRAFT, "mine": E_GATHER, "log": E_LOG, "dig": E_DIG, "give": E_GIVE, "furnace": E_SMELT, "hunt": E_KILL}
VERBS = {**VERBS_OLD, "equip": E_EQUIP, "drop": E_DROP, "place": E_PLACE, "store": E_STORE, "retrieve": E_TAKE}
VERBS_ASK = set(VERBS) - {"log"}  # 나무캐→뭘요 부자연
WEARABLE = ["iron_leggings", "iron_helmet", "iron_chestplate", "iron_boots", "iron_sword", "iron_pickaxe", "iron_axe", "shield", "stone_sword",
            "diamond_sword", "diamond_pickaxe", "diamond_chestplate", "golden_helmet", "leather_boots", "bow", "stone_pickaxe"]


def tail(r, s):
    x = r.random()
    if x < 0.08:
        s += r.choice(["!!", "!", "!!!", "~", ".", "..", "ㅋㅋ", " ㅋㅋ", " 좀", " 빨리", " ㄱㄱ", " 부탁", "ㅎ", " 제발"])
    return s


def item_span(r, u, iid, label="대상", train=True, link=None):
    u.add(C.surface(r, iid, train), label, link or iid)


MINE_DROP = {"stone": "cobblestone", "iron_ore": "raw_iron"}
# 굽기 요청: 재료명 → 결과물로 링크 (철 구워 = 철괴 목표, 원석 캐기 X)
SMELT_OUT = {"raw_iron": "iron_ingot", "grp:iron": "iron_ingot", "raw_gold": "gold_ingot", "grp:gold": "gold_ingot", "beef": "cooked_beef",
             "porkchop": "cooked_porkchop", "chicken": "cooked_chicken", "sand": "glass", "cobblestone": "stone", "stone": "stone", "oak_log": "charcoal",
             "potato": "baked_potato", "clay_ball": "brick", "grp:meat": "grp:meat"}  # 캐기 요청의 블록명 → 실제 얻는 드롭템으로 링크 (돌 캐 = 조약돌, 굽기 X)


def count_span(r, u, glue=False):
    n = r.choice([1, 1, 2, 3, 4, 5, 8, 10, 16, 20, 32, 64, 64, 12, 6, 7, 24, 128, 9])
    s = C.count_surface(r, n)
    (u.glue if glue else u.add)(s, "개수", n)
    return n


def t_goal(r, ctx):
    """목표 실행 발화 → (U, type, target_id, count)"""
    u = U()
    k = r.random()
    if k < 0.28:  # craft
        iid = r.choice(CRAFT_T)
        n = None
        form = r.random()
        if form < 0.06:  # 원목 → 판자로: 대상=종별 판자
            sp = r.choice(P.WOOD_SP[:9])
            u.add(C.surface(r, f"{sp}_log") + r.choice([" 판자로", " 판자", "로 판자", " 나무판자로", "판자로"]), "대상", f"{sp}_planks")
            u.add(pick_end(r, E_CRAFT))
            return u, "craft", f"{sp}_planks", None
        if form < 0.25:
            item_span(r, u, iid); n = count_span(r, u)
        elif form < 0.35:
            n = count_span(r, u); item_span(r, u, iid)
        elif form < 0.45 and not iid.startswith("set:"):
            item_span(r, u, iid); u.add(r.choice(["하나", "하나만", "한개", "1개", "한개만"]), "개수", 1); n = 1
            if r.random() < 0.5:
                u.add(pick_end(r, E_CRAFT))
            return u, "craft", iid, n
        elif form < 0.55:  # 다중: A랑 B 만들어 → 첫 대상이 GOAL
            item_span(r, u, iid)
            if r.random() < 0.5:
                n = count_span(r, u)
            u.glue(r.choice(["랑", "하고", "이랑", ", "]))
            item_span(r, u, r.choice([c for c in CRAFT_T if c != iid]))
            if r.random() < 0.5:
                count_span(r, u)
        else:
            item_span(r, u, iid)
        if r.random() < 0.12:  # 무동사 (철 곡괭이 / 돌검!!!)
            return u, "craft", iid, n
        if r.random() < 0.15:
            u.glue(r.choice(["좀", "하나"]))
        u.add(pick_end(r, E_CRAFT))
        return u, "craft", iid, n
    if k < 0.46:  # gather
        iid = r.choice(list(GATHER_T) + ["stone"] * 3)  # 돌 캐 빈출
        ty = GATHER_T[iid]
        form = r.random()
        n = None
        gs = lambda i: item_span(r, u, i, link=MINE_DROP.get(i))  # noqa: E731
        if form < 0.5:
            gs(iid); n = count_span(r, u)
        elif form < 0.6:
            n = count_span(r, u); gs(iid)
        elif form < 0.7:  # 다중: A n개랑 B m개 캐와
            gs(iid)
            n = count_span(r, u) if r.random() < 0.7 else None
            u.glue(r.choice(["랑", "하고", "이랑", ", "]))
            gs(r.choice([k for k in GATHER_T if GATHER_T[k] == ty and k != iid] or [iid]))
            if r.random() < 0.7:
                count_span(r, u)
        else:
            gs(iid)
            if r.random() < 0.3:
                u.glue(r.choice(["좀", "점", "좀 더"]) if r.random() < 0.5 else "")
        ends = {"log": E_LOG, "dig": E_DIG}.get(ty, E_GATHER)
        if n is None or r.random() > 0.1:  # 소고기 20개 식 무동사 일부
            (u.glue if n is None and r.random() < (0.4 if ty == "log" else 0.2) else u.add)(pick_end(r, ends))  # 철캐와·고기구해와 식 붙여쓰기
        return u, ty, MINE_DROP.get(iid, iid), n
    if k < 0.53:  # hunt/meat
        if r.random() < 0.5:
            iid = r.choice(HUNT_T); item_span(r, u, iid)
            n = count_span(r, u) if r.random() < 0.3 else None
            u.add(pick_end(r, E_KILL))
        else:
            iid = r.choice(MEAT_T); item_span(r, u, iid)
            n = count_span(r, u) if r.random() < 0.4 else None
            u.add(r.choice(["구해와", "구해", "구하자", "좀 구해와", "구해온나", "모아와", "가져와", "사냥해와", "구해줘", "구해 ㄱㄱ"]))
        return u, "hunt", iid, n
    if k < 0.58:  # combat
        if r.random() < 0.3:
            p = r.choice(PLAYERS)
            if r.random() < 0.4:
                t = r.choice(["stone_axe", "iron_sword", "diamond_sword", "wooden_sword"]); item_span(r, u, t, "도구"); u.glue(r.choice(["로", "으로"]))
            u.add(p, "사람", p); u.glue(r.choice(["를", "을", "", ""]))
            u.add(r.choice(["공격해", "공격", "때려", "죽여", "패", "잡아"]))
            return u, "combat", None, None
        iid = r.choice(HOSTILE); item_span(r, u, iid)
        if r.random() < 0.2:
            u.glue(r.choice(["좀", "들"]))
        (u.glue if r.random() < 0.3 else u.add)(pick_end(r, E_KILL))  # 좀비처리해·좀비사냥해 붙여쓰기 (실발화 enchant 오분류)
        return u, "combat", iid, None
    if k < 0.63:  # smelt
        if r.random() < 0.12:
            u.add(r.choice(["화로 확인해", "화로 봐봐", "화로 체크해", "연료 넣어", "석탄 넣어", "화로에 연료 좀 넣어", "화로 상태 봐"]))
            return u, "check", "furnace", None
        iid = r.choice(SMELT_T + ["grp:iron"] * 2 + ["stone"])
        item_span(r, u, iid, link=SMELT_OUT.get(iid))
        n = count_span(r, u) if r.random() < 0.35 else None
        if r.random() < 0.2:
            u.add(r.choice(["다", "전부", "몽땅"]))
        u.add(pick_end(r, E_SMELT))
        return u, "furnace", SMELT_OUT.get(iid, iid), n
    if k < 0.69:  # give
        if r.random() < 0.2:
            u.add(r.choice(["나", "나한테", "내게", "저한테"]))
        iid = r.choice(MISC)
        n = None
        if r.random() < 0.12:
            w = r.choice(["템 다", "가진거 다", "캔거", "만든거", "구운거"])
            iid = "grp:item_all" if "다" in w else "ctx:last"  # ctx:last = 방금 작업 결과물 (링크는 NULL, 서빙에서 작업기록 참조)
            u.add(w, "대상", iid)
        else:
            item_span(r, u, iid)
            n = count_span(r, u) if r.random() < 0.35 else None
        if n is None and r.random() < 0.15:  # 철좀·철곡좀 = 줘
            (u.glue if r.random() < 0.6 else u.add)(r.choice(["좀", "좀요", "좀!", "점"]))
            return u, "give", iid, n
        u.add(pick_end(r, E_GIVE))
        return u, "give", iid, n
    if k < 0.72:  # drop
        iid = r.choice(MISC); item_span(r, u, iid)
        n = count_span(r, u) if r.random() < 0.3 else None
        u.add(pick_end(r, E_DROP))
        return u, "drop", iid, n
    if k < 0.76:  # equip
        iid = r.choice(EQUIP_T); item_span(r, u, iid)
        u.add(pick_end(r, E_EQUIP))
        return u, "equip", iid, None
    if k < 0.79:  # place
        iid = r.choice(PLACE_T)
        if r.random() < 0.2:
            u.add(r.choice(["여기", "앞에", "앞으로 한칸", "옆에", "화로 위에"]))
        item_span(r, u, iid)
        if r.random() < 0.15:
            count_span(r, u)
        u.add(pick_end(r, E_PLACE))
        return u, "place", iid, None
    if k < 0.83:  # store/retrieve
        where = r.choice(["chest", "chest", "furnace"])
        if r.random() < 0.5 and where == "chest":
            item_span(r, u, "chest", "장소"); u.glue(r.choice(["에", "에다", "에다가"]))
            if r.random() < 0.3:
                u.add(r.choice(["템", "아이템", "템 다", "다"]), "대상", "grp:item_all")
                iid = "grp:item_all"
            else:
                iid = r.choice(MISC); item_span(r, u, iid)
                if r.random() < 0.2:
                    u.add("다")
            u.add(pick_end(r, E_STORE))
            return u, "store", iid, None
        item_span(r, u, where, "장소"); u.glue(r.choice(["에서", "에서", "서"]))
        iid = r.choice(["raw_iron", "iron_ingot", "cooked_beef", "wheat_seeds", "glass", "coal", "cobblestone", "grp:meat", "diamond"])
        item_span(r, u, iid)
        n = count_span(r, u) if r.random() < 0.3 else None
        u.add(pick_end(r, E_TAKE))
        return u, "retrieve", iid, n
    # 이동·기타
    ms = [("come", ["집합해", "집합!", "모여라", "와라", "이리 온나", "빨리 집합", "이리와", "와바", "와봐", "일루와", "일루와봐", "집합", "온나", "여기로 와", "오셈", "와", "이리 와바", "나한테 와", "여기로", "빨리 와", "모여", "모여봐", "컴온"]),
          ("follow", ["따라와", "따라다녀", "날 따라와", "따라오셈", "나 따라와", "따라 와", "쫓아와", "뒤에 붙어"]),
          ("collect", ["주우러가", "죽은 데 가서 템 주워", "죽은곳 가서 아이템 챙겨", "죽은 자리 템 주워와", "템 떨군데 가서 주워", "죽은곳 템 회수하자", "아이템 주워", "떨어진거 주워", "템 주워와", "주워", "떨군거 주워"]),
          ("shelter", ["숨어", "밤이니까 숨어", "땅굴 파고 숨어", "피신해", "대피해", "굴 파고 들어가"]),
          ("sleep", ["자", "잠 자", "침대에서 자", "잘 시간이야", "자자"]), ("flee", ["도망가", "여기서 빠져나가", "탈출해", "밖으로 나가", "여기서 나가자", "빨리 나가", "튀어", "도망쳐", "빨리 도망가", "런"]),
          ("pillar", ["블럭 쌓아", "위로 쌓아", "쌓아서 올라가", "기둥 쌓아", "필러 해"]),
          ("tunnel", ["일자굴 파", "터널 파", "밑으로 파", "굴 파", "계단식으로 파 내려가", "브랜치 마이닝 해"]),
          ("farm", ["농사", "농사 ㄱㄱ", "농사짓자", "농사 지어", "농사 좀 지어봐", "밭 갈아", "경작지 만들어", "농사라도 짓자", "씨 심어", "밀 심어", "밭 만들어", "농사해"]),
          ("combat", ["몹 좀 잡아", "싸워봐", "싸우자", "가서 싸워", "덤벼", "나가서 몹좀 잡자", "몹 처리해", "나가서 몹 잡아", "몹 정리해", "몬스터 잡아", "주변 몹 다 잡아", "적 처리해", "몹들 패", "몹 쓸어"]),
          ("guard", ["나 좀 지켜줘", "지켜줘", "엄호해", "호위해", "나 지켜", "근처 몹 잡아줘"]),
          ("auto", ["자급자족해", "알아서 살아", "혼자서도 살 수 있게 준비해", "살아남아", "자율모드", "알아서 해", "생존해봐", "혼자 놀아", "자유롭게 해", "니 맘대로 살아봐"]),
          ("build", ["집 지어줘", "집 지어", "건물 지어", "성 지어줘", "집짓자"]), ("enchant", ["인챈트 해", "마법부여 해", "인첸트 좀"]),
          ("fish", ["낚시해", "낚시하자", "물고기 낚아", "연어 낚아와", "낚싯대로 잡아", "낚시 ㄱㄱ"]), ("trade", ["주민이랑 거래해", "거래해", "주민한테 팔아"]),
          ("ranged", ["활 쏴", "활로 쏴", "화살 쏴"]), ("boat", ["보트 타", "보트 타고 가"]), ("minecart", ["마카 타", "마인카트 타"]),
          ("eat", ["먹어", "밥 먹어", "뭐 좀 먹어", "피좀 채워", "배 채워", "밥 먹자", "먹을거 먹어", "고기 먹어", "스테이크 먹어", "빵 먹어"]),
          ("unequip", ["갑옷 벗어", "철 흉갑 벗어", "투구 벗어", "벗어"]),
          ("equip", ["장비 껴", "장비 착용해", "장비 다 껴", "템 장착해", "장비 챙겨 입어", "갑옷 다 입어"]),
          ("break", ["앞에 블럭 부숴", "앞에 캐", "이거 부숴", "앞 블럭 캐", "막힌거 부숴", "상자 캐", "상자 부숴", "화로 캐", "작업대 캐", "작업대 회수해", "화로 부숴", "침대 캐"])]
    x = r.random()
    if x < 0.12:  # 상대 이동·쌓기 + 거리
        d = r.choice([1, 1, 2, 3, 5, 10, 16, 23, 64, 300])
        ds = r.choice([f"{d}칸", f"{d} 칸", "한칸" if d == 1 else f"{d}칸", "한 칸" if d == 1 else f"{d}칸"])
        if r.random() < 0.35:
            ty = "pillar"
            if r.random() < 0.6:
                u.add(ds, "거리", d); u.add(r.choice(["올라가", "더 올라가", "쌓아", "위로 쌓아", "쌓아 올라가"]))
            else:
                u.add(r.choice(["블럭 쌓아", "위로 쌓아", "쌓아", "더 쌓아", "돌 쌓아", "위로 더 쌓아", "기둥 쌓아", "올라가", "위로 올라가"]))
            return u, ty, None, None
        if r.random() < 0.25:
            u.add(r.choice(["y좌표", "y", "와이"])); u.add(str(r.choice([-58, -54, 11, 16, 64, 70])), "좌표", None)
            u.add(r.choice(["까지 내려가", "까지 올라가", "까지 파"]))
            return u, "move", None, None
        u.add(r.choice(["앞으로", "뒤로", "옆으로", "왼쪽으로", "오른쪽으로", "위로", "밑으로", "아래로", ""]))
        if r.random() < 0.6:
            u.add(ds, "거리", d)
            if r.random() < 0.3:
                u.add("더")
        u.add(r.choice(["가", "가봐", "이동", "달려가", "달려", "내려가", "뛰어", "점프", "가자", "걸어가"]))
        return u, "move", None, None
    if x < 0.16:
        u.add(r.choice(["뛰어", "점프", "점프해", "뛰어 내려", "내려와", "내려가자", "달려가", "앞으로 달려", "웅크려", "쭈그려"]))
        return u, "move", None, None
    if x < 0.19:
        pl = r.choice(["place:home", "place:home", "place:here"])
        u.add(r.choice(["여기가", "여기를", "여기", "이 위치를", "지금 위치"]))
        u.add(C.surface(r, "place:home"), "장소", "place:home")
        u.glue(r.choice(["야", "이야", "로 해", "로 저장해", "로 기억해", "로 등록"]))
        return u, "mark", "place:home", None
    if x < 0.21:
        u.add(r.choice(["인벤토리 비워", "인벤 비워", "템 다 버려", "가진거 다 버려"]))
        return u, "drop", "grp:item_all", None
    if x < 0.23:
        u.add(r.choice(["나와", "나온나", "거기서 나와", "나가자", "밖으로 나와"]))
        return u, "come", None, None
    ty, opts = r.choice(ms)
    if ty == "goto" or r.random() < 0.18:
        g = r.random()
        if g < 0.4:
            x, y, z = r.randint(-300, 300), r.randint(-60, 120), r.randint(-300, 300)
            u.add(f"{x} {y} {z}", "좌표", (x, y, z))
            if r.random() < 0.9:
                u.glue(r.choice(["으로 가", "로 가", "으로 이동", "로 와", " 가", "까지 가", " ㄱㄱ", " 으로 가", "로 이동"]))
            return u, "goto", None, None
        pl = r.choice(["place:home", "place:death", "chest", "crafting_table", "furnace", "white_bed"])
        item_span(r, u, pl, "장소"); u.glue(r.choice(["으로 가", "로 가", "로 가자", "으로 가자", "로 와", "쪽으로 가", "에 가"]))
        return u, "goto", pl, None
    s = r.choice(opts)
    tgt = None
    if ty in ("eat", "unequip", "break", "equip"):
        words = {"스테이크": "cooked_beef", "빵": "bread", "고기": "grp:meat", "철 흉갑": "iron_chestplate", "투구": "grp:armor", "갑옷": "grp:armor",
                 "상자": "chest", "화로": "furnace", "작업대": "crafting_table", "침대": "white_bed"}
        for w, iid in words.items():
            if s.startswith(w):
                u.add(w, "대상", iid); u.add(s[len(w):].strip()); return u, ty, iid, None
    u.add(s)
    return u, ty, tgt, None


def t_query(r):
    u = U()
    q = r.choice(Q_KEYS)
    tgt = None
    T = {"inv": ["인벤 뭐있어", "템 뭐있냐", "인벤 보여줘", "인벤 어때", "뭐 가지고 있어?", "템 머머 있음", "인벤토리 확인", "가방 뭐있음", "인벤 뭐있음", "템 머잇어"],
         "hp": ["체력은?", "피 괜찮냐", "니 체력 몇임", "hp 몇이야", "피 몇", "안 아파?", "체력 어때"],
         "food": ["배고프냐", "배고파?", "배고픔 몇이야", "밥 먹었어?", "허기 어때"],
         "status": ["상태", "상태 어때", "괜찮아?", "컨디션 어때", "상태 알려줘", "ㅅㅌ"],
         "pos": ["어디야", "어디임?", "지금 어디", "위치 알려줘", "좌표 불러", "어디 있어?"],
         "doing": ["뭐해", "왜 멈춰있어?", "왜 가만히 있어", "왜 안 움직여", "왜 멈춤?", "왜 서있어", "지금 뭐해", "뭐함", "지금 머하냐", "뭐하는 중이야", "뭐 하고 있어?", "머ㅓ 만드는데"],
         "time": ["몇시야", "밤이야?", "아침이야?", "지금 낮이야?", "해 떴어?"],
         "chest": ["상자에 뭐 있어?", "상자에 뭐뭐 있어", "상자 안에 뭐 있음", "상자 열어봐", "체스트 확인해봐"],
         "furnace": ["화로에 뭐 있어", "화로에 뭐있어?", "다 구워졌어?", "화로 어때"],
         "abilities": ["뭐 할 수 있어?", "넌 뭐 할줄 알아", "할 줄 아는거 뭐야", "기능 뭐 있어"],
         "where_player": ["나 어딨는지 알아?", "내 위치 알아?", "나 보여?", "내가 어디 있게"],
         "progress": ["다 됐어?", "얼마나 남았어", "어떻게 됐어", "진행 어때", "아직이야?"]}
    if q in T:
        u.add(r.choice(T[q]))
        return u, q, None
    if q == "have":
        iid = r.choice(MISC); item_span(r, u, iid)
        u.add(r.choice(["있어?", "있냐", "있음?", "몇개 있어?", "몇개 있음?", "있니", "있나?", "는?", "도 있냐", "좀 있어?", "얼마나 있어?", "몇 개야"]))
        return u, q, iid
    if q in ("recipe", "can_make"):
        iid = r.choice(CRAFT_T); item_span(r, u, iid)
        if q == "recipe":
            u.add(r.choice(["어떻게 만들어?", "어캐 만듬?", "어떻게 만듦", "레시피 알려줘", "만드는 법", "어케 만들어", "조합법 뭐야", "만들려면 뭐 필요해?"]))
        else:
            u.add(r.choice(["만들 수 있냐?", "만들 수 있어?", "만들 수 있음?", "만들어져?", "만들 재료 있어?", "만들 수 있지?", "가능?"]))
        return u, q, iid
    if q == "can_do":
        iid = r.choice(["stone", "iron_ore", "diamond_ore", "obsidian", "oak_log", "cobblestone"]); item_span(r, u, iid)
        u.add(r.choice(["맨손으로 캐지냐", "맨손으로 캐져?", "나무곡괭이로 캐져?", "캘 수 있어?", "캐짐?", "뭘로 캐야해?"]))
        return u, q, iid
    if q == "near":
        if r.random() < 0.4:
            u.add(r.choice(["주변 뭐 있어", "주변에 뭐 보이냐", "옆에 뭐 있어", "근처에 뭐 있음", "뭐 보여?"]))
            return u, q, None
        iid = r.choice(["grp:log", "mob:cow", "mob:zombie", "iron_ore", "coal_ore", "water_bucket", "lava_bucket", "mob:pig", "mob:creeper", "sand"])
        u.add(r.choice(["근처에", "주변에", "이 근처", "근처", ""]))
        item_span(r, u, iid)
        u.add(r.choice(["있어?", "있음?", "보여?", "있냐", "있나"]))
        return u, q, iid
    iid = r.choice(["chest", "place:home", "crafting_table", "furnace", "white_bed", "place:death"])
    item_span(r, u, iid, "장소")
    u.add(r.choice(["어딨어", "어디야", "어디 있어?", "어딨음", "위치 어디", "설치 위치 어디야", "어디 설치했어", "어디다 놨어", "어디 뒀어", "설치한데 어디", "위치 알려줘"]))
    return u, "where_thing", iid


SIMPLE = {
    "멈춤": ["멈춰", "정지해", "정지!", "올스톱", "일단 정지", "그만", "스탑", "스톱", "됐어 멈춰", "ㄴㄴ 그만", "아 됐다 그만", "그만해", "멈춰봐", "취소", "하지마", "stop", "잠깐", "잠깐만", "스톱스톱", "기다려", "대기", "가만히 있어", "멈춰!!", "그거 하지마", "됐어 그만해"],
    "재개": ["하던거 마저 해", "마저해", "다시 ㄱㄱ", "하던 거 마저 해줘", "계속 진행해", "이어서 ㄱㄱ", "하던거 이어서", "다시 해봐", "진행해", "계속 해줘", "하던거 계속 ㄱㄱ", "아까 하던거 해", "이어서 해", "계속해", "다시 해", "하던거 해", "하던 거 계속", "마저 해", "다시 시작"],
    "긍정 대답": ["ㅇㅇ", "응", "어", "가자", "출발", "고고", "ㄱㄱ", "좋아", "그래", "진행해", "시작해", "만들자", "ㅋ", "ㅋㅋ", "ㅇㅋ", "오키", "웅", "해", "그렇게 해", "ok", "네", "넹", "콜", "출발해", "그냥 가", "맞아", "ㅇㅇ 그거", "해줘", "그래도 공격해", "그래도 해", "상관없어 해", "그냥 해", "괜찮으니까 해"],
    "부정 대답": ["ㄴㄴ", "아니", "싫어", "하지마", "노노", "아니야", "안돼", "ㄴ", "no", "됐어", "안 해도 돼", "그거 아니야", "다른거"],
    "잡담": ["안녕", "다시 시킬게요", "나중에 다시 시킬게", "이따 시킬게", "잠깐 딴거 할게", "아이고야", "아이고", "아이구", "??", "?", "???", "엥?", "뭐지", "하..", "아이고 ㅋㅋ", "헐", "에휴", "ㅎㅇ", "고마워", "잘했어 ㅋㅋ", "굿", "수고", "고마웡 ㅋㅋ", "안뇽", "ㅋㅋㅋㅋ", "잘자", "좋아 좋아", "와 대박", "ㄳ", "땡큐", "나 왔어", "심심하다", "휴 살았다", "ㅎㅎ", "귀엽네", "잘하네"],
    "욕설": ["멍청아 그것도 못해?", "바보냐", "병신아", "야 이 멍청아", "븅신", "개못하네", "쓰레기네", "죽을래?", "닥쳐", "등신아"],
    "위험 경고": ["뒤에 크리퍼!!", "너 익사해", "익사한다", "너 익사한다", "익사하겠다", "물에 빠졌잖아", "빠져죽는다", "숨 막혀", "물 속이야", "숨 막히겠다", "너 물에 빠졌어", "빠져 죽겠다", "너 죽는다", "피 없다", "떨어진다", "떨어져 죽어", "용암이야!!", "화살 맞는다", "크리퍼 온다", "좀비 온다", "조심해", "거미 있어", "뒤에 스켈레톤", "위험해", "몹 온다", "옆에 좀비", "피해!!", "용암 조심"],
}
ASK_REPLY = {"부정 대답": ["혼자해", "혼자 해", "혼자 해봐", "ㄴㄴ 혼자해봐", "못도와줌", "못 도와줘", "니가 해", "너가 해", "알아서 해", "나 바빠", "바빠", "혼자 할 수 있잖아",
                          "안 도와줄거임", "싫어 혼자해", "직접 해", "니 혼자 해", "그냥 혼자 해", "도움 없음", "알아서 해봐", "혼자서 해"],
             "긍정 대답": ["응 도와줄게", "도와줄게", "ㅇㅇ 도와줌", "뭐 필요해?", "뭐 줄까", "같이 하자", "도와줄께", "ㅇㅋ 도와줌", "같이 해", "뭐 도와줘?"]}
HINT_T = {"slow": ["도끼 없이 캐면 느릴듯", "맨손이면 한세월 걸리겠는데", "손으로 나무캐면 한세월일듯", "그거론 한참 걸리겠는데?", "곡괭이 만들고 캐", "너무 느린데", "그걸로 언제 캐"],
          "wrong": ["그건 돌이잖아", "옆에 자작나무 있잖아", "여기 나무 많은데", "가까운거 캐", "옆에 있는 나무 캐", "참나무 있잖아", "근처에 나무 있는데 왜 멀리가", "가문비 나무 있잖아", "그거 맞아?", "그거 아닌데", "잘못 만들었어", "그거 말고", "딴거 만들었네"],
          "short": ["그거가지고 되겠어?", "그걸로 부족할걸", "더 필요할텐데", "그거론 모자라"],
          "danger": ["밤인데 괜찮겠어?", "그러다 죽어", "위험하지 않아?", "갑옷 없이 가게?"],
          "done_claim": ["만들었다며", "캤다며", "없는데?", "안 줬잖아"]}


def ctx_text(r, s):
    """상태·대화 요약 → ctx 세그먼트 텍스트"""
    parts = [f"체력 {s['hp']}/20 배고픔 {s['food']}/20", "밤" if s["night"] else "낮"]
    if s["inv"]:
        parts.append("인벤: " + ", ".join(f"{ko(k)} {v}" for k, v in list(s["inv"].items())[:10]))
    else:
        parts.append("인벤: 비어있음")
    if s.get("placed"):
        parts.append("설치: " + ", ".join(f"{ko(k)} {v}칸" for k, v in s["placed"].items()))
    parts.append("작업: " + (s["task"] or "없음"))
    if s.get("paused"):
        parts.append("멈춘작업: " + s["paused"])
    if s.get("botq"):
        parts.append("봇질문: " + s["botq"])
    return " | ".join(parts)


def rand_state(r):
    inv = {}
    for _ in range(r.randint(0, 6)):
        inv[r.choice(MISC[:30])] = r.choice([1, 2, 3, 5, 8, 12, 32, 64])
    return {"hp": r.randint(3, 20), "food": r.randint(4, 20), "night": r.random() < 0.3, "inv": inv,
            "placed": {k: r.randint(2, 40) for k in r.sample(["crafting_table", "furnace", "chest"], r.randint(0, 2))},
            "task": r.choice([None, None, "철곡괭이 제작 중(3/9)", "나무 캐는 중(2/5)", "철괴 굽는 중", "따라가는 중", "원정 중(나무)", "자율모드: 장비 준비"]),
            "paused": r.choice([None, None, None, "철 흉갑 제작(4/7)", "나무 64개 캐기(20/64)"]), "botq": None}


def typo(r, t, sp, p=0.05):
    """구간 밖 한글 1자 오타 (집함·몹조ㅗㅁ·공격패 류). 길이 유지 → 구간 오프셋 불변"""
    if r.random() > p:
        return t
    cand = [i for i, c in enumerate(t) if "가" <= c <= "힣" and not any(a <= i < b for a, b, _, _ in sp)]
    if not cand:
        return t
    i = r.choice(cand)
    o = ord(t[i]) - 0xAC00
    cho, jung, jong = o // 588, o % 588 // 28, o % 28
    k = r.random()
    if k < 0.4:
        jong = r.choice([0, 4, 8, 16, 17, 19, 21])  # 받침 흔들림
    elif k < 0.8:
        jung = (jung + r.choice([-1, 1, 4, -4])) % 21  # 모음 옆키
    else:
        cho = (cho + r.choice([-1, 1])) % 19
    return t[:i] + chr(0xAC00 + cho * 588 + jung * 28 + jong) + t[i + 1:]


def unspace(r, u, p=0.2):
    """구간 끝 뒤 공백 제거 (나무캐와·철곡들어·철셋만들어 류, 실채팅 오분류). 뒤 구간 오프셋 -1"""
    if r.random() > p:
        return
    cand = [b for _, b, _, _ in u.sp if b < len(u.t) and u.t[b] == " "]
    if cand:
        i = r.choice(cand)
        u.t = u.t[:i] + u.t[i + 1:]
        u.sp = [(a - (a > i), b - (b > i), l, it) for a, b, l, it in u.sp]


def rows_turn(r, n, banned):
    out = []
    while len(out) < n:
        s = rand_state(r)
        k = r.random()
        y = {}
        hist = ""
        if k < 0.45:
            u, ty, tgt, cnt = t_goal(r, s)
            y = {"act": "목표 실행", "type": ty}
        elif k < 0.62:
            u, q, tgt = t_query(r)
            y = {"act": "질문 답하기", "query": q}
        elif k < 0.69:  # 되묻기: 모르는 말 / 대상 없음
            u = U()
            if r.random() < 0.6:
                w = "".join(r.choice("가나다라마바사아자차카타파하두루무부수우주추쿠투푸후뚝뽁쨍꿀롱") for _ in range(r.randint(1, 3)))
                u.add(w, "대상", "null")
                if r.random() < 0.4:
                    count_span(r, u)
                ty = r.choice(["craft", "mine", "give", "drop"])
                u.add(r.choice({"craft": E_CRAFT, "mine": E_GATHER, "give": E_GIVE, "drop": E_DROP}[ty]))
                y = {"act": "되묻기", "type": ty}
            else:
                u.add(r.choice(["그거 줘", "그거 만들어", "저거 캐와", "그거", "만들어", "가져와", "캐와", "줘", "구해와", "그거 좀"]))
                y = {"act": "되묻기"}
        elif k < 0.77:  # 다중턴: 이전 발화에서 대상 / 봇 되물음 후 답
            u0, ty, tgt, cnt = t_goal(r, s)
            if not any(l == "대상" and it and not it.startswith("ctx:") for _, _, l, it in u0.sp) or ty not in VERBS:
                continue
            m = r.random()
            if m < 0.35 and ty in VERBS_ASK:  # 동사만 → 봇 '뭘요?' → 대상만 답 = 이전 동사 type 계승 (실측: 입어→뭘요?→철레깅스 를 craft로 오분류)
                s["botq"] = r.choice(["뭘요?", "뭘요?", "뭘 할까요?"])
                hist = f"이전 나: {r.choice(['', '그거 ', '저거 ', '빨리 ', '좀 '])}{r.choice(VERBS[ty])} / 봇: " + r.choice({"give": ["뭘 줄까요?"], "place": ["뭘 설치할까요?"]}.get(ty, ["뭘요?", "뭘 할까요?", "뭘요?"]))
                u = U()
                if r.random() < 0.2:
                    u.add(r.choice(["아", "그거", "ㅇㅇ", "음"]))
                for a, b, lab, it in u0.sp:
                    if lab == "대상":
                        u.add(u0.t[a:b], lab, it)
                if r.random() < 0.3:
                    u.add(r.choice(["요", "ㅇㅇ", "말한거", "!", "그거"]))
                y = {"act": "목표 실행", "type": ty}
            elif m < 0.45:  # 만든 직후 동사만 (철레깅스 만들어 → 만들었어요! → 입어/줘) = 대상은 이전 발화
                g0 = r.choice(WEARABLE)
                ty = r.choice(["equip", "equip", "give", "drop", "store"])
                u0 = U(); u0.add(C.surface(r, g0), "대상", g0); u0.add(r.choice(E_CRAFT))
                hist = f"이전 나: {u0.t} / 봇: {ko(g0)} 1개 " + r.choice(["만들었어요!", "완료!", "만들었어요."])
                u = U()
                if r.random() < 0.3:
                    u.add(r.choice(["그거", "그럼", "이제", "만든거", "그럼 그거", "바로"]))
                u.add(r.choice({"equip": E_EQUIP, "give": E_GIVE, "drop": E_DROP, "store": E_STORE}[ty]))
                y = {"act": "목표 실행", "type": ty}
                off = len("이전 나: ")
                u.sp = [(a + off, b + off, l, it) for a, b, l, it in u0.sp]
                u.in_hist = True
            elif ty not in VERBS_OLD:
                continue
            elif m < 0.7:  # 봇이 되물음 → 사용자가 풀어 말함
                bad = "".join(r.choice("가나다라마바사뚝곡갑템") for _ in range(2))
                hist = f"이전 나: {bad} {r.choice(VERBS[ty])} / 봇: {bad}{r.choice(['이', '가', '는', ''])} 뭔가요?"
                u = U()
                u.add(r.choice(["아아", "아", "", "그거", "ㅇㅇ"]))
                for a, b, lab, it in u0.sp:
                    if lab == "대상":
                        u.add(u0.t[a:b], "대상", it)
                u.add(r.choice(["ㅇㅇ", "말하는거야", "말한거", "요", "", "그거"]))
                y = {"act": "목표 실행", "type": ty}
            else:  # 대상은 이전 발화, 지금은 동사만
                hist = f"이전 나: {u0.t} / 봇: {r.choice(['그건 지금 없어요.', '뭘로 할까요?', '어떻게 할까요?', '알겠어요.'])}"
                u = U()
                u.add(r.choice(["ㄱㄱ", "해", "해줘", "빨리", "그거", "그럼"]) + " " + r.choice(VERBS[ty]) if r.random() < 0.4 else r.choice(VERBS[ty] + ["ㄱㄱ", "해줘"]))
                y = {"act": "목표 실행", "type": ty}
                off = len("이전 나: ")
                u.sp = [(a + off, b + off, l, it) for a, b, l, it in u0.sp]
                u.pair = u0.pair  # 구간은 hist 쪽 (합친 텍스트 기준 이동은 아래)
                u.in_hist = True
        elif k < 0.80:  # 직전 작업 끝난뒤 동사만 (철 5개 캐와 → 완료! → 구워): 대상은 이전 발화, 링크는 새 동사 기준
            src = r.choice(["grp:iron", "raw_iron", "grp:gold", "stone", "cobblestone", "sand", "grp:meat", "beef", "oak_log", "grp:log", "dirt", "coal", "diamond"])
            ty = r.choice(["furnace", "furnace", "give", "drop", "store"]) if src in SMELT_OUT else r.choice(["give", "drop", "store", "craft"])
            u0 = U()
            u0.add(C.surface(r, src), "대상", "?")
            n0 = count_span(r, u0) if r.random() < 0.6 else None
            u0.add(r.choice(E_GATHER if src != "grp:meat" else E_KILL + ["구해와"]))
            got = MINE_DROP.get(src, src)
            lk = {"furnace": SMELT_OUT.get(src, src), "craft": "null"}.get(ty, got)  # craft: 뭘 만들지 모름 → 되묻기용 NULL
            u0.sp = [(a, b, l, lk if it == "?" else it) for a, b, l, it in u0.sp]
            done = f"{u0.t[u0.sp[0][0]:u0.sp[0][1]]} {n0 or 1}개 " + r.choice(["완료!", "캤어요!", "구했어요!", "모았어요."])
            hist = f"이전 나: {u0.t} / 봇: {done}"
            u = U()
            if r.random() < 0.3:
                u.add(r.choice(["그거", "그럼", "이제", "그거 다", "캔거", "그럼 그거"]))
            u.add(r.choice({"furnace": E_SMELT, "give": E_GIVE, "drop": E_DROP, "store": ["상자에 넣어", "넣어놔", "상자에 넣어둬"], "craft": E_CRAFT}[ty]))
            y = {"act": "되묻기" if ty == "craft" else "목표 실행", "type": ty}
            off = len("이전 나: ")
            u.sp = [(a + off, b + off, l, it) for a, b, l, it in u0.sp]
            u.pair = u0.pair
            u.in_hist = True
        elif k < 0.90:
            a = r.choice(list(SIMPLE))
            if a in ("긍정 대답", "부정 대답"):
                s["botq"] = r.choice(["원정 갈까요?", "밤인데 계속할까요?", "철이 부족해요. 캐러 갈까요?", "진짜로 공격할까요?", "이거 버려도 돼요?", "나무 더 캘까요?"])
            u = U()
            u.add(r.choice(SIMPLE[a]))
            y = {"act": a}
            if a in ("긍정 대답", "부정 대답") and r.random() < 0.4:  # 봇 도움요청(goal.ask) 답: 혼자해=부정(혼자 진행), 도와줄게=긍정. 봇질문 없으면 혼자해=auto
                g0 = r.choice(PLAN_GOALS)
                s["botq"] = f"{ko(g0)} " + r.choice(["도움", "도움", "방법", "실패"])
                hist = f"이전 나: {C.surface(r, g0)} {r.choice(E_CRAFT)} / 봇: " + r.choice([f"{ko(g0)}는 혼자 하기 어려워요, 도와줄래요?", "계속 안되네요, 도와줄래요?", f"{ko(g0)} 만드는 법을 모르겠어요, 도와줄래요?"])
                u = U(); u.add(r.choice(ASK_REPLY[a]))
            if a == "재개":
                s["paused"] = s["paused"] or "철 흉갑 제작(4/7)"
        elif k < 0.94:
            h = r.choice(H_KEYS)
            u = U(); u.add(r.choice(HINT_T[h]))
            s["task"] = s["task"] or r.choice(["나무 캐는 중(1/5, 맨손)", "철곡괭이 제작 중(2/9)"])
            y = {"act": "지적·조언", "hint": h}
        else:  # 봇질문 없을때 ㅇㅇ/ㅋㅋ → 잡담 (문맥 판별 학습)
            u = U(); u.add(r.choice(["ㅇㅇ", "ㅋㅋ", "ㅋ", "응", "ㅎㅎ", "굿"]))
            y = {"act": "잡담"}
        if not getattr(u, "in_hist", False):
            unspace(r, u)
        t = typo(r, u.t, u.sp)
        t = tail(r, t)
        if t.strip() in banned:
            continue
        if not hist and r.random() < 0.25:  # 무관한 직전대화 (봇은 2분내 직전대화 항상 전달) → 현재발화 완결이면 무시 학습
            h0, _, _, _ = t_goal(r, s)
            hist = f"이전 나: {h0.t} / 봇: {r.choice(['알겠어요.', '완료!', '할게요!', '네', '그건 지금 없어요.'])}"
        # 입력 텍스트 = [이전대화 ▶ ] 현재발화. 구간은 합친 텍스트 기준
        pre = hist + " ▶ " if hist else ""
        sh = 0 if getattr(u, "in_hist", False) else len(pre)
        spans = [(a + sh, b + sh, LI[l], it if isinstance(it, (str, int)) or it is None else list(it)) for a, b, l, it in u.sp]
        out.append({"kind": "turn", "utt": pre + t, "ctx": ctx_text(r, s), "y": y, "spans": spans, "pairs": u.pair})
    return out


# ---------- plan ----------
BLOCKS_NEAR = ["oak_log", "stone", "iron_ore", "coal_ore", "sand", "dirt", "gravel", "mob:cow", "mob:pig", "mob:chicken", "lava", "diamond_ore", "gold_ore", "short_grass"]
PLAN_GOALS = ["iron_pickaxe", "stone_pickaxe", "iron_sword", "set:iron_armor", "iron_helmet", "iron_chestplate", "torch", "furnace", "chest",
              "cooked_beef", "bucket", "shield", "glass", "diamond_pickaxe", "stone_axe", "iron_axe", "grp:log", "cobblestone", "raw_iron",
              "bread", "crafting_table", "stick", "iron_boots", "iron_leggings", "set:stone_tools", "white_bed", "coal", "golden_helmet"]


def rows_plan(r, n):
    out = []
    while len(out) < n:
        goal = r.choice(PLAN_GOALS)
        cnt = 1 if goal.startswith(("set:", "iron_", "stone_", "diamond_", "golden_")) or goal in ("furnace", "chest", "crafting_table", "shield", "bucket", "white_bed") else r.choice([1, 4, 8, 16, 32])
        inv = {}
        for _ in range(r.randint(0, 5)):
            inv[r.choice(["oak_log", "oak_planks", "stick", "cobblestone", "coal", "raw_iron", "iron_ingot", "wooden_pickaxe", "stone_pickaxe", "furnace", "crafting_table", "beef", "bucket", "stone_axe"])] = r.choice([1, 2, 3, 4, 8, 16])
        near = {b: (r.randint(3, 60) if r.random() < 0.7 else None) for b in BLOCKS_NEAR}
        placed = {k: r.randint(2, 80) if r.random() < 0.7 else r.randint(80, 2000) for k in r.sample(["crafting_table", "furnace"], r.randint(0, 2))}  # 원정중 먼 설치물
        ms = P.methods(goal, cnt, inv, {"placed": placed, "near": near}, k=6)
        if len(ms) < 1 or (ms[0]["via"] == "direct" and r.random() < 0.9):
            continue
        night = r.random() < 0.3
        armor = r.random() < 0.3
        hp = r.randint(4, 20)
        opts, val = [], []
        for m in ms:
            # 숨은 참값: 추정 대비 편차. 강한 편차는 대개 QED에 흔적(0.85)
            dev = math.exp(r.gauss(0, 0.2))
            ok = max(0.02, 1 - m["risk"] * r.uniform(0.6, 1.4))
            exp_steps = any(s["type"] == "expedition" for s in m["steps"])
            if night and not armor:
                ok *= 0.85 if exp_steps or any(s["type"] in ("mine", "hunt") for s in m["steps"]) else 1
            hidden = r.random()
            code = None
            if hidden < 0.12:  # 자원 실제로 없음/막힘
                ok *= r.uniform(0.02, 0.2); code = r.choice(["no_target", "no_path", "stuck"])
            elif hidden < 0.22:  # 느림
                dev *= r.uniform(1.8, 3.5); code = "slow"
            true_ms = m["est_ms"] * dev
            q = None
            evid = (code is not None and r.random() < 0.85) or (code is None and r.random() < 0.45)
            if evid:
                nq = r.randint(1, 12)
                okn = sum(r.random() < ok for _ in range(nq))
                q = {"n": nq, "ok": okn / nq, "avg_ms": int(true_ms * math.exp(r.gauss(0, 0.12)))}
                if code in ("no_target", "no_path", "stuck") and r.random() < 0.7:
                    q["recent_fail"] = r.randint(2, 4); q["fail"] = code
            opts.append(P.method_text(m, q, maxstep=4))
            val.append((true_ms, ok))
        # 도움 요청 옵션: 모두 나쁠때
        opts.append("ask | 플레이어에게 도움 요청하고 대기 | 예상 300초 위험 0%")
        val.append((300000.0, 0.9))
        cost = [ms_ / max(ok, 1e-3) for ms_, ok in val]
        cost[-1] = 0.0 if max(o for _, o in val[:-1]) < 0.15 else float("inf")  # 요청은 최후수단: 모든 방법 성공률 <15%일때만 (시간 긴 GOAL을 요청으로 라벨하던 오류)
        best = min(range(len(cost)), key=cost.__getitem__)
        order = sorted(range(len(cost)), key=cost.__getitem__)
        alt = order[1] if len(order) > 1 else best
        perm = list(range(len(opts) - 1))
        r.shuffle(perm)
        perm.append(len(opts) - 1)
        opts = [opts[i] for i in perm]
        val = [val[i] for i in perm]
        sp = {k: r.choice(P.WOOD_SP[:9]) if r.random() < 0.6 else "oak" for k in ("inv", "near")}  # 주변·보유 목재 종 다양화 (계산은 종 무관)
        sw = lambda k, w: k.replace("oak_", sp[w] + "_", 1) if k in ("oak_log", "oak_planks") else k
        inv_s = ", ".join(f"{ko(sw(k, 'inv'))} {v}" for k, v in inv.items()) or "비어있음"
        near = {sw(k, "near"): v for k, v in near.items()}
        if near.get(sw("oak_log", "near")) is not None and r.random() < 0.3:  # 더 먼 다른 종
            near[r.choice(P.WOOD_SP[:9]) + "_log"] = near[sw("oak_log", "near")] + r.randint(5, 40)
        ctx = f"GOAL: {ko(goal)} {cnt} | 체력 {hp}/20 {'밤' if night else '낮'} {'갑옷 있음' if armor else '갑옷 없음'} | 인벤: {inv_s} | 설치: " + (
            ", ".join(f"{ko(k)} {v}칸" for k, v in placed.items()) or "없음") + " | 주변: " + ", ".join(
            f"{'용암' if b == 'lava' else P.ko(b)} {d}칸" for b, d in near.items() if d is not None and r.random() < 0.6)
        out.append({"kind": "plan", "ctx": ctx, "opts": opts, "best": perm.index(best), "alt": perm.index(alt),
                    "val": [[math.log1p(a / 1000), o] for a, o in val], "goal": goal, "steps": ms[perm[perm.index(best)]]["steps"] if perm[perm.index(best)] < len(ms) else []})
    return out


# ---------- prio ----------
# 멈춘작업 = 봇이 넣는 원 요청문 그대로 (고정문구 학습시 실제 요청문에서 재개 못함 → 영구대기)
PAUSED_REQ = ["철 흉갑 제작", "철갑옷만들어", "나무 5개 캐와", "철곡 만들어", "돌 3개 캐", "상자 만들어", "고기 구해와", "철 5개 구워", "석탄 캐와",
              "철 곡괭이 만들어줘", "나무 좀 캐", "소 잡아", "다이아 캐와", "화로 만들어", "빵 만들어", "철셋 ㄱㄱ", "돌곡 만들어", "모래 퍼와"]
PRIO = ["계속 진행", "근접 전투", "달려서 도망", "블럭 쌓아 도망", "굴 파고 숨기", "먹기", "멈춘 작업 재개", "물 위로 올라가기", "인벤 정리"]


TASK_OUT = ("원정(철)", "나무 캐기")


def rows_incident():
    """사고 prio 행 재라벨 (data/incidents/*/prio_rows.json) ×10. 규칙 = rows_prio 교사와 동일 우선순위"""
    import glob
    out = []
    for f in sorted(glob.glob(os.path.join(H, "incidents", "*", "prio_rows.json"))):
        for x in json.load(open(f)):
            c = x["ctx"]
            th = [(m, int(d)) for m, d in re.findall(r"([가-힣]+) (\d+)칸", c.split("위협:")[1].split("|")[0])] if "위협:" in c else []
            night, weak = " 밤 " in c, "맨손" in c or "방어 0 " in c
            if any(m == "크리퍼" and d <= 6 for m, d in th):
                y = "달려서 도망"
            elif x["pred"] in ("달려서 도망", "근접 전투") and any(d <= (12 if night or m not in ("좀비", "스켈레톤") else 6) for m, d in th):
                y = x["pred"]  # 근접 위협 판단은 기존 유지
            elif night and weak and any(d <= 16 for _, d in th):
                y = "굴 파고 숨기"
            else:
                y = x.get("y") or x["pred"]
            out += [{"kind": "prio", "ctx": c, "y": PRIO.index(y)}] * 10
    return out


def rows_prio(r, n):
    import planner
    mobs = planner.db()["mob"]
    wpn = planner.db()["wpn"]
    out = []
    for _ in range(n):
        hp = r.randint(1, 20)
        food = r.randint(0, 20)
        night = r.random() < 0.4
        armor = r.choice([0, 0, 5, 10, 15, 20])
        weapon = r.choice(["hand", "wooden_sword", "stone_sword", "iron_sword", "diamond_sword", "stone_axe", "iron_axe"])
        dmg = wpn.get(weapon, (1, 4))[0] if weapon != "hand" else 1
        threats = []
        for _ in range(r.choice([0, 0, 1, 1, 2, 3, 5])):
            m = r.choice(["zombie", "skeleton", "creeper", "spider", "enderman", "witch", "husk", "drowned", "cave_spider", "slime"])
            threats.append((m, r.randint(2, 24)))
        has_food = r.random() < 0.6
        paused = r.random() < 0.3
        task = r.choice(["철곡괭이 제작", "나무 캐기", "원정(철)", "없음", "없음", "따라가기"] + [f"{ko(g)} {c}개 ({i}/{i + r.randint(0, 6)})" for g, c, i in [(r.choice(PLAN_GOALS), r.choice([1, 1, 2, 5]), r.randint(1, 5))]])  # 뒤: 봇 실측 형식
        deaths = r.choice([None, None, "creeper", "skeleton", "zombie", "drown"])
        air = 20 if r.random() < 0.7 else r.randint(0, 19)  # 물속 산소 (0~20, 0이면 익사 데미지)
        free = r.randint(8, 36) if r.random() < 0.75 else r.randint(0, 7)  # 인벤 빈칸
        cur = r.choice(["", "", "", "근접 전투", "달려서 도망"]) if threats else ""  # 현재 행동: 히스테리시스(전투↔도망 루프 방지)
        # 교사 규칙: 생존 1순위
        near = [t for t in threats if t[1] <= (6 if not night and t[0] in ("zombie", "skeleton") else 12)]  # 낮 좀비·스켈 원거리 = 타는중·안다가옴 → 무시 (12칸 스켈 도망 루프)
        danger = 0.0
        for m, d in near:
            mh, ma = mobs.get(m, (20, 3))
            ma = ma or 3
            danger += (ma * (1 - min(armor, 20) * 0.04)) * math.ceil(mh / dmg) * (1.6 if m == "creeper" else 1)
        far = [t for t in threats if t[1] <= 16]
        weak = weapon == "hand" or armor == 0
        if air <= 6 or (air <= 12 and (deaths == "drown" or hp <= 8)):  # 익사 직전: 전투·먹기보다 우선
            y = "물 위로 올라가기"
        elif near:
            creeper = any(m == "creeper" and d <= 6 for m, d in near)
            if creeper or (deaths == "creeper" and any(m == "creeper" for m, _ in near)):
                y = "달려서 도망"
            elif danger > hp * {"근접 전투": 1.6, "달려서 도망": 0.8}.get(cur, 1.2) or len(near) >= 4:  # 진행중 행동 유지편향
                y = "블럭 쌓아 도망" if any(m in ("zombie", "husk", "spider") for m, _ in near) and len(near) >= 3 else "달려서 도망"
            else:
                y = "근접 전투"
        elif hp <= 10 and has_food and food < 18:
            y = "먹기"
        elif night and weak and far:  # 밤·맨몸 + 먼 위협 → 숨기 (사고 2026-09-30 dig_place_loop)
            y = "굴 파고 숨기"
        elif cur == "달려서 도망" and far:  # 도망중 16칸 내 잔존 → 도망 유지 (재개↔도망 루프 방지)
            y = "달려서 도망"
        elif has_food and (food <= 6 or task == "없음" and food < 14):  # 선제 식사
            y = "먹기"
        elif night and armor == 0 and task in TASK_OUT and r.random() < 0.8:
            y = "굴 파고 숨기"
        elif free <= 2:  # 가득: 캔 템 못 주움 → 정리 먼저
            y = "인벤 정리"
        elif task == "없음" and paused and not (night and far):
            y = "멈춘 작업 재개"
        else:
            y = "계속 진행"
        ctx = (f"체력 {hp}/20 배고픔 {food}/20 빈칸 {free}/36" + (f" 산소 {air}/20" if air < 20 else "") + f" {'밤' if night else '낮'} 방어 {armor} 무기 {P.ko(weapon) if weapon != 'hand' else '맨손'} 공격력 {dmg}"
               f" | 음식 {'있음' if has_food else '없음'} | 작업: {task}" + (" | 멈춘작업: " + r.choice(PAUSED_REQ) if paused else "") + (f" | 현재: {cur}" if cur else "") +
               " | 위협: " + (", ".join(f"{P.ko('mob:' + m)} {d}칸" for m, d in threats) or "없음") +
               (f" | 최근 사망원인: {'익사' if deaths == 'drown' else P.ko('mob:' + deaths)}" if deaths else ""))
        out.append({"kind": "prio", "ctx": ctx, "y": PRIO.index(y)})
    return out


# ---------- tidy: 인벤 정리 (아이템별 유지/버리기/상자 보관) ----------
TIDY = ["유지", "버리기", "상자에 보관"]
TIDY_POOL = ["dirt", "cobblestone", "granite", "diorite", "andesite", "gravel", "sand", "oak_log", "oak_planks", "stick", "oak_sapling", "wheat_seeds",
             "rotten_flesh", "bone", "string", "flint", "coal", "raw_iron", "iron_ingot", "raw_copper", "copper_ingot", "raw_gold", "diamond", "emerald",
             "redstone", "lapis_lazuli", "cobbled_deepslate", "tuff", "beef", "cooked_beef", "bread", "apple", "wooden_pickaxe", "stone_pickaxe",
             "iron_pickaxe", "stone_sword", "iron_sword", "iron_helmet", "bucket", "torch", "crafting_table", "furnace", "leather", "feather",
             "gunpowder", "spider_eye", "poppy", "dandelion", "wheat", "netherrack", "clay_ball", "white_wool", "arrow", "oak_door", "ladder"]
_USE = {}


def tidy_label(item, n, v, need, free, chest_d, sit, filler, space):
    """교사 규칙: 필요템·도구·음식 유지. 버리기는 작업 공간 부족(빈칸<필요칸)일때만, 싼 잡템부터.
    원정 복귀는 공간 여유 있어도 가치 있는 여분 내 상자로. 쌓기용 블럭 한 묶음은 남김"""
    kind = P.kind_of(item)
    if need > 0 or kind in ("도구", "갑옷", "음식"):
        return "유지"
    short = free < space
    near = chest_d is not None and chest_d <= 48
    if re.search(P.FILLER, item) and filler - n < 32:  # 도망·굴용 블럭 부족해짐
        return "유지"
    if sit == "원정 복귀" and near and v * n >= 2:
        return "상자에 보관"
    if not short:
        return "유지"
    if near and v * n >= 2:
        return "상자에 보관"
    if v < 0.3 and v * n < 8 or v * n < 4:
        return "버리기"
    return "유지"


def rows_tidy(r, n):
    out = []
    val = P.db()["val"]
    for _ in range(n):
        item = r.choice(TIDY_POOL)
        cnt = r.choice([1, 2, 3, 5, 8, 12, 16, 24, 32, 48, 64])
        v = val.get(item, 0.5)
        goal = r.choice(PLAN_GOALS + [None] * 8)
        if goal and goal not in _USE:
            ms = P.methods(goal, 1, {}, {"placed": {}, "near": {}}, k=1)
            _USE[goal] = (ms[0]["use"], P.space_of(ms[0]["steps"], {})) if ms else ({}, 1)
        use, sp = _USE[goal] if goal else ({}, r.choice([2, 3, 4]))  # GOAL 없음(인벤 가득) = 주울 여유칸
        need = min(cnt, use.get(item, 0))
        space = max(1, sp - r.randint(0, 3))  # 일부 이미 보유
        free = r.choice([0, 0, 1, 1, 2, 3, 4, 6, 10, 15, 20])
        chest_d = r.choice([None, None, r.randint(2, 30), r.randint(30, 120)])
        sit = r.choice(P.TIDY_SIT)
        filler = cnt + r.choice([0, 0, 10, 40, 64, 128]) if re.search(P.FILLER, item) else r.choice([0, 0, 20, 64, 128])
        y = tidy_label(item, cnt, v, need, free, chest_d, sit, filler, space)
        ctx = P.tidy_ctx(item, cnt, v, need, ko(goal) if goal else None, free, chest_d, sit, filler, space)
        out.append({"kind": "tidy", "ctx": ctx, "y": TIDY.index(y)})
    return out


# ---------- 0.3 판단 문항 (봇 규칙 → Miya). 행 = {kind, utt, ctx, q, opts, y}. ctx·보기 텍스트 함수는 serve 와 공용 ----
JQ = {"food": ("음식 선택", "음식"), "weapon": ("무기 선택", "무기"), "target": ("전투 대상", "대상"), "hunt": ("사냥 대상", "사냥"),
      "explore": ("탐색 방향", "방향"), "fail": ("실패 대응", "대응"), "recover": ("사망 회수", "회수"), "qty": (None, "수량"), "pick": (None, "실물"),
      "hintact": (None, "조언 대응")}
# 허기·포만·부작용 (minecraft 위키)
FOOD = {"enchanted_golden_apple": (4, 9.6, "강력 재생"), "golden_apple": (4, 9.6, "재생"), "golden_carrot": (6, 14.4, ""), "cooked_beef": (8, 12.8, ""),
        "cooked_porkchop": (8, 12.8, ""), "cooked_mutton": (6, 9.6, ""), "cooked_chicken": (6, 7.2, ""), "cooked_salmon": (6, 9.6, ""), "cooked_cod": (5, 6.0, ""),
        "bread": (5, 6.0, ""), "baked_potato": (5, 6.0, ""), "pumpkin_pie": (8, 4.8, ""), "mushroom_stew": (6, 7.2, ""), "apple": (4, 2.4, ""), "carrot": (3, 3.6, ""),
        "melon_slice": (2, 1.2, ""), "sweet_berries": (2, 0.4, ""), "cookie": (2, 0.4, ""), "dried_kelp": (1, 0.6, ""), "potato": (1, 0.6, ""),
        "beef": (3, 1.8, ""), "porkchop": (3, 1.8, ""), "mutton": (2, 1.2, ""), "cod": (2, 0.4, ""), "salmon": (2, 0.4, ""),
        "chicken": (2, 1.2, "허기 30%"), "rotten_flesh": (4, 0.8, "허기 80%"), "spider_eye": (2, 3.2, "독"), "poisonous_potato": (2, 1.2, "독 60%")}
GOLD_F = ("enchanted_golden_apple", "golden_apple")


def food_opt(k, n):
    h, s, bad = FOOD.get(k, (2, 1.0, ""))
    return f"{ko(k)} {n}개 (허기 +{h} 포만 {s}{' ' + bad if bad else ''})"


def food_ctx(hp, food, fight, task):
    return f"체력 {hp}/20 배고픔 {food}/20 | {'전투중' if fight else '평시'} | 작업: {task or '없음'}"


def food_label(foods, hp, food, fight):
    """교사: 비상(전투·저체력)엔 황금사과, 평시엔 아낌. 부작용 음식은 최후. 넘치는 허기(낭비) 벌점"""
    if (fight and hp <= 8 or hp <= 4) and (g := [k for k in GOLD_F if k in foods]):
        return g[0]
    deficit = 20 - food

    def sc(k):
        h, s, bad = FOOD[k]
        return (k in GOLD_F) * -50 + bool(bad) * -30 + s + h * 0.5 - max(0, h - deficit) * (0.2 if hp <= 10 else 1.0) + foods[k] * 0.001
    return max(foods, key=sc)


def rows_food(r, n):
    out = []
    ks = list(FOOD)
    for _ in range(n):
        fs = {k: r.choice([1, 1, 2, 3, 5, 8, 16, 32, 64]) for k in r.sample(ks, r.choice([1, 2, 2, 3, 3, 4, 5]))}
        hp, food, fight = r.randint(1, 20), r.randint(0, 19), r.random() < 0.3
        y = food_label(fs, hp, food, fight)
        o = list(fs)
        r.shuffle(o)
        out.append({"kind": "food", "ctx": food_ctx(hp, food, fight, r.choice([None, "나무 캐기", "철곡괭이 제작", "원정(철)"])),
                    "opts": [food_opt(k, fs[k]) for k in o], "y": o.index(y)})
    return out


# 무기: 근접무기 + (방패 있으면) 방패 조합. dmg/spd = planner wpn 표
MELEE = ["wooden_sword", "stone_sword", "iron_sword", "golden_sword", "diamond_sword", "netherite_sword", "wooden_axe", "stone_axe", "iron_axe", "diamond_axe", "netherite_axe"]
RANGED_MOB = ("skeleton", "stray", "pillager", "witch", "blaze")


def wpn_stat(w):
    return (1.0, 4.0) if w == "hand" else P.db()["wpn"].get(w, (1.0, 4.0))


def weapon_opts(ws, shield):
    """[(키, 텍스트)] 키 = 무기id 또는 '무기id+shield'"""
    o = []
    for w, dur in ws.items():
        d, s = wpn_stat(w)
        t = f"{'맨손' if w == 'hand' else ko(w)} (공격력 {d:g} 속도 {s:g}" + (f" 내구도 {dur}%" if w != "hand" else "") + ")"
        o.append((w, t))
        if shield:
            o.append((w + "+shield", t + " + 방패"))
    return o


def weapon_ctx(mob, d, nthreat, hp, armor):
    return f"상대: {ko('mob:' + mob)} {d}칸 | 위협 {nthreat}마리 | 체력 {hp}/20 방어 {armor}"


def weapon_label(ws, shield, mob, nthreat):
    mh = P.db()["mob"].get(mob, (20, 3))[0]

    def ttk(w):  # 처치시간(초) ≈ 타수/공속. 내구도 5% 미만은 최후
        d, s = wpn_stat(w)
        return math.ceil(mh / d) / s + (100 if w != "hand" and ws[w] < 5 else 0)
    b = min(ws, key=ttk)
    return b + "+shield" if shield and (mob in RANGED_MOB or mob == "creeper" or nthreat >= 2) else b


def rows_weapon(r, n):
    out = []
    mobs = ["zombie", "skeleton", "creeper", "spider", "witch", "husk", "drowned", "cave_spider", "slime", "enderman", "pillager", "stray"]
    for _ in range(n):
        ws = {w: r.choice([100, 100, 80, 50, 20, 3]) for w in r.sample(MELEE, r.choice([0, 1, 1, 2, 2, 3]))}
        ws["hand"] = 100
        shield = r.random() < 0.35
        mob, d, nt = r.choice(mobs), r.randint(1, 16), r.choice([1, 1, 1, 2, 3])
        y = weapon_label(ws, shield, mob, nt)
        o = weapon_opts(ws, shield)
        r.shuffle(o)
        out.append({"kind": "weapon", "ctx": weapon_ctx(mob, d, nt, r.randint(3, 20), r.choice([0, 0, 5, 10, 15])),
                    "opts": [t for _, t in o], "y": [k for k, _ in o].index(y)})
    return out


# 전투 대상: 위협 목록 중. 가중 = 위험도 / 거리 (크리퍼 근접 최우선, 엔더맨 중립은 최후)
THREAT_W = {"creeper": 3.0, "skeleton": 3.0, "stray": 3.0, "witch": 3.0, "pillager": 3.0, "zombie": 2.0, "husk": 2.0, "drowned": 2.0, "spider": 2.0,
            "cave_spider": 2.5, "slime": 1.0, "enderman": 0.2}


def target_ctx(hp, weapon_ko, armor, why):
    return f"체력 {hp}/20 무기 {weapon_ko} 방어 {armor} | 요청: {why}"


def target_label(ts):
    return max(range(len(ts)), key=lambda i: (THREAT_W.get(ts[i][0], 1.5) * (2.5 if ts[i][0] == "creeper" and ts[i][1] <= 5 else 1)) / (ts[i][1] + 2))


def rows_target(r, n):
    out = []
    for _ in range(n):
        ts = [(r.choice(list(THREAT_W)), r.randint(1, 24)) for _ in range(r.choice([1, 2, 2, 3, 3, 4]))]
        y = target_label(ts)
        w = r.choice(["hand", "stone_sword", "iron_sword", "diamond_axe"])
        out.append({"kind": "target", "ctx": target_ctx(r.randint(3, 20), "맨손" if w == "hand" else ko(w), r.choice([0, 5, 10, 15]), r.choice(["몹 잡아", "자기방어", "지켜"])),
                    "opts": [f"{ko('mob:' + m)} {d}칸" for m, d in ts], "y": y})
    return out


# 사냥 대상: 주변 동물 중 고기 기대값/거리. 없으면 원정
MEAT_V = {"cow": 3.0, "pig": 2.4, "sheep": 1.6, "chicken": 1.0, "rabbit": 1.0, "mooshroom": 3.0, "goat": 0.1, "horse": 0.0, "llama": 0.0}
HUNT_NONE = "주변에 없음 → 원정"


def hunt_ctx(food, has_food, want):
    return f"배고픔 {food}/20 음식 {'있음' if has_food else '없음'} | 요청: {want}"


def hunt_label(an):
    if not an:
        return len(an)
    sc = [MEAT_V.get(m, 0.5) * (1 + min(c, 5) * 0.1) / (1 + d / 16) for m, d, c in an]
    return max(range(len(an)), key=lambda i: sc[i]) if max(sc) > 0.05 else len(an)


def rows_hunt(r, n):
    out = []
    for _ in range(n):
        an = [(m, r.randint(2, 48), r.randint(1, 6)) for m in r.sample(list(MEAT_V), r.choice([0, 1, 1, 2, 2, 3]))]
        out.append({"kind": "hunt", "ctx": hunt_ctx(r.randint(0, 20), r.random() < 0.5, r.choice(["사냥해", "고기 구해와", "동물 잡아", "먹을거 구해"])),
                    "opts": [f"{ko('mob:' + m)} {d}칸 {c}마리" for m, d, c in an] + [HUNT_NONE], "y": hunt_label(an)})
    return out


# 탐색 방향: 8방위 지표면 요약(봇 표본) + 방문 횟수. 찾는 것 종류별 선호 지형
DIRS = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]
SURF = ["나무", "풀", "돌", "모래", "물", "미로드"]
SEEK = {"log": {"나무": 1.0}, "animal": {"풀": 1.0, "나무": 0.2}, "ore": {"돌": 1.0}, "sand": {"모래": 1.0, "물": 0.3}, "water": {"물": 1.0}, "any": {}}
SEEK_KO = {"log": "원목", "animal": "동물", "ore": "광석·돌", "sand": "모래", "water": "물·점토"}


def explore_opt(dr, f, v):
    return f"{dr} " + " ".join(f"{k} {f.get(k, 0)}" for k in SURF) + f" 방문 {v}회"


def explore_ctx(seek, what_ko, y, night, hop):
    return f"찾는 것: {what_ko} ({SEEK_KO.get(seek, seek)}) | Y {y} | {'밤' if night else '낮'} | 탐색 {hop}번째"


def explore_label(seek, fs, vs):
    w = SEEK.get(seek, {})

    def sc(i):
        f = fs[i]
        return sum(w.get(k, 0) * f.get(k, 0) for k in SURF) - 2.0 * vs[i] - (0.4 * f.get("물", 0) if seek not in ("water", "sand") else 0) - 0.5 * f.get("미로드", 0)
    return max(range(len(fs)), key=sc)


def rows_explore(r, n):
    out = []
    what = {"log": ["oak_log", "birch_log", "spruce_log"], "animal": ["mob:cow", "mob:pig", "mob:sheep"], "ore": ["iron_ore", "coal_ore", "stone", "copper_ore"],
            "sand": ["sand"], "water": ["clay_ball", "water_bucket"]}
    for _ in range(n):
        seek = r.choice(list(what))
        fs, vs = [], []
        for _ in DIRS:
            f = {}
            for _ in range(8):  # 방향당 표본 8칸
                k = r.choices(SURF, weights=[r.random() for _ in SURF])[0]
                f[k] = f.get(k, 0) + 1
            fs.append(f); vs.append(r.choice([0, 0, 0, 0, 1, 1, 2, 3]))
        y = explore_label(seek, fs, vs)
        out.append({"kind": "explore", "ctx": explore_ctx(seek, ko(r.choice(what[seek])), r.randint(40, 110), r.random() < 0.3, r.randint(1, 5)),
                    "opts": [explore_opt(d, f, v) for d, f, v in zip(DIRS, fs, vs)], "y": y})
    return out


# 실패 대응 (안건4, O): 봇은 시도·재계획·연속 횟수만 셈, 결정은 모델. 같은 사유 반복 = 루프 → 재시도 금지
FAIL = ["같은 단계 재시도", "방법 다시 계획", "도움 요청", "포기(멈춘 작업으로)"]
REASON_KO = {"stuck": "끼임·이동 불가", "err:timeout": "시간 초과", "no_target": "대상 못찾음(탐색 실패)", "no_tool": "도구 없음(파손)", "no_material": "재료 부족",
             "no_table": "작업대 없음", "no_furnace": "화로 없음", "no_space": "설치 자리 없음", "craft_desync": "제작 동기화 오류", "slow": "굽기 지연",
             "taken": "누가 빼감", "liquid": "물·용암 만남", "no_floor": "발판 블럭 없음", "death": "사망", "err": "기타 오류"}
TRANSIENT = ("stuck", "err:timeout", "craft_desync", "slow", "no_space", "err")


def fail_ctx(goal_ko, step_ko, reason, tries, replans, streak, qed_s, hp, night, player):
    return (f"GOAL: {goal_ko} | 실패 단계: {step_ko} | 사유: {REASON_KO.get(reason, reason)} | 이 단계 시도 {tries}회 | 재계획 {replans}회 | 같은 사유 연속 {streak}회"
            f" | 경험: {qed_s or '없음'} | 체력 {hp}/20 {'밤' if night else '낮'} | 플레이어 {'있음' if player else '없음'}")


def fail_label(reason, tries, replans, streak, qok, qn, hp, night, player):
    stop = FAIL[2] if player else FAIL[3]
    if streak >= 3 or replans >= 4 or (qn >= 5 and qok < 0.2 and replans >= 2):
        return stop
    if reason == "death" and (streak >= 2 or night and hp <= 6):
        return stop
    if reason in TRANSIENT and tries < 3:
        return FAIL[0]
    if reason == "no_target" and replans >= 2:
        return stop
    return FAIL[1]


def rows_fail(r, n):
    out = []
    steps = [("mine", "iron_ore"), ("log", "oak_log"), ("craft", "iron_pickaxe"), ("furnace", "iron_ingot"), ("hunt", "mob:cow"), ("place", "crafting_table"),
             ("expedition", "iron_ore"), ("mine", "stone"), ("craft", "stick"), ("dig", "sand")]
    for _ in range(n):
        st, tg = r.choice(steps)
        reason = r.choice(list(REASON_KO))
        tries, replans = r.choice([1, 1, 1, 2, 2, 3, 4]), r.choice([0, 0, 0, 1, 1, 2, 3, 4, 5])
        streak = min(r.choice([1, 1, 1, 2, 2, 3, 4]), replans + tries)
        qn = r.choice([0, 0, 0, 3, 8, 20])
        qok = r.random() if qn else 0
        hp, night, player = r.randint(2, 20), r.random() < 0.3, r.random() < 0.6
        qs = f"{qn}회 성공 {round(qok * 100)}%" if qn else None
        y = fail_label(reason, tries, replans, streak, qok, qn, hp, night, player)
        out.append({"kind": "fail", "ctx": fail_ctx(ko(r.choice(PLAN_GOALS)), f"{P.TYPE_KO.get(st, st)} {ko(tg)}", reason, tries, replans, streak, qs, hp, night, player),
                    "opts": FAIL, "y": FAIL.index(y)})
    return out


# 사망 회수 (P): 잃은 가치·거리·소멸(5분)·원인 위험
RECOVER = ["회수하러 가기", "포기하고 하던 일"]
DEATH_KO = {"lava": "용암", "void": "공허 추락", "fall": "낙사", "drown": "익사", "creeper": "크리퍼", "zombie": "좀비", "skeleton": "스켈레톤", "spider": "거미", "starve": "굶주림", "fire": "불"}


def recover_ctx(v, top_ko, d, el, cause, night, armor, weapon_ko, hp):
    return (f"잃은 가치 {v:g} | 주요: {top_ko or '없음'} | 거리 {d}칸 | 경과 {el}초 (300초 후 소멸) | 사망원인 {DEATH_KO.get(cause, cause)}"
            f" | {'밤' if night else '낮'} | 현재 방어 {armor} 무기 {weapon_ko} 체력 {hp}/20")


def recover_label(v, d, el, cause, night, armor, weapon):
    left = 300 - el - d * 0.3
    if cause in ("lava", "void", "fire") or left < 20 or v < 5:
        return RECOVER[1]
    risky = cause in ("creeper", "zombie", "skeleton", "spider") and (night or armor == 0 and weapon == "hand")
    return RECOVER[0] if v >= (100 if risky else 5) else RECOVER[1]


def rows_recover(r, n):
    out = []
    val = P.db()["val"]
    pool = ["dirt", "cobblestone", "oak_log", "iron_ingot", "raw_iron", "coal", "diamond", "iron_pickaxe", "diamond_sword", "diamond_chestplate", "bread",
            "torch", "stone_pickaxe", "iron_sword", "golden_apple", "oak_planks", "stick", "gold_ingot", "emerald", "iron_helmet"]
    for _ in range(n):
        inv = {k: (1 if re.search(r"_(sword|pickaxe|chestplate|helmet)$", k) else r.choice([1, 2, 5, 12, 32, 64])) for k in r.sample(pool, r.choice([1, 1, 2, 3, 5, 8]))}
        vs = {k: val.get(k, 0.5) * c for k, c in inv.items()}
        v = round(sum(vs.values()), 1)
        top = ", ".join(f"{ko(k)} {inv[k]}" for k in sorted(vs, key=lambda k: -vs[k])[:3])
        d, el = r.choice([5, 20, 40, 80, 150, 300, 600, 1200]), r.choice([10, 30, 60, 120, 200, 260, 290])
        cause, night, armor, weapon, hp = r.choice(list(DEATH_KO)), r.random() < 0.4, r.choice([0, 0, 5, 10]), r.choice(["hand", "hand", "stone_sword", "iron_sword"]), 20
        y = recover_label(v, d, el, cause, night, armor, weapon)
        out.append({"kind": "recover", "ctx": recover_ctx(v, top, d, el, cause, night, armor, "맨손" if weapon == "hand" else ko(weapon), hp), "opts": RECOVER, "y": RECOVER.index(y)})
    return out


# 수량 의미 (B, I): 개수 없음·"다"·"좀"·"더"·"까지" → 실제 개수는 serve 가 계산
QTY = ["전부", "1개", "절반", "말한 개수(추가로)", "말한 개수 맞추기(총)", "되묻기"]
Q_ALL = ["다", "전부", "몽땅", "싹 다", "있는거 다", "싹", "전부 다"]
Q_SOME = ["좀", "조금", "약간", "몇개", "몇 개"]
Q_TOTAL = ["까지", "되게", "맞춰", "채워"]


def qty_ctx(typ, item, held):
    return f"행동: {TYPES[typ]} | 대상 보유: {ko(item)} {held}개 (가치 {P.db()['val'].get(item, 0.5):g}) | 종류: {P.kind_of(item)}"


def qty_label(typ, utt, item, held, has_cnt):
    stack = not re.search(r"_(sword|pickaxe|axe|shovel|hoe|helmet|chestplate|leggings|boots)$|^(bow|shield|bucket|water_bucket|lava_bucket)$", item)
    v = P.db()["val"].get(item, 0.5)
    if has_cnt:
        return QTY[4] if typ == "craft" and any(w in utt for w in Q_TOTAL) else QTY[3]
    if typ == "craft":
        return QTY[1]
    if any(re.search(rf"(^|\s){re.escape(w)}(\s|$)", utt) for w in Q_ALL):
        return QTY[0]
    if any(w in utt for w in Q_SOME):
        return QTY[2] if held >= 2 else QTY[0]
    if not stack:
        return QTY[1]
    if typ == "drop":
        return QTY[5] if v >= 1 and held > 1 else QTY[0]
    return QTY[5] if v >= 1 and held > 16 else QTY[0]


def rows_qty(r, n):
    out = []
    pool = TIDY_POOL + ["diamond", "gold_ingot", "iron_ingot", "emerald", "diamond_sword", "iron_helmet"]
    verbs = {"give": E_GIVE, "drop": E_DROP, "craft": E_CRAFT}
    for _ in range(n):
        typ = r.choice(["give", "give", "drop", "drop", "craft"])
        item = r.choice(pool if typ != "craft" else CRAFT_T)
        held = r.choice([0, 1, 2, 3, 5, 8, 16, 32, 64]) if typ == "craft" else r.choice([1, 2, 3, 5, 8, 16, 32, 64])
        u = C.surface(r, item)
        has_cnt, k = r.random() < 0.35, r.random()
        if has_cnt:
            tot = typ == "craft" and r.random() < 0.4
            u += " " + ("더 " if not tot and r.random() < 0.3 else "") + C.count_surface(r, r.choice([1, 2, 3, 5, 8, 10, 16, 32, 64])) + (r.choice(Q_TOTAL) if tot else "")
        elif k < 0.25:
            u += " " + r.choice(Q_ALL)
        elif k < 0.45:
            u += " " + r.choice(Q_SOME)
        u = tail(r, u + " " + r.choice(verbs[typ]))
        out.append({"kind": "qty", "utt": u, "ctx": qty_ctx(typ, item, held), "opts": QTY, "y": QTY.index(qty_label(typ, u, item, held, has_cnt))})
    return out


# 실물 후보 (A, E, D): 묶음 대상 → 보유 실물 중 선택. 종·재료 수식어 우선, 파괴적 행동 + 불확실 → 되묻기
SP_KO = {"oak": ["참나무"], "spruce": ["가문비나무", "가문비"], "birch": ["자작나무", "자작"], "jungle": ["정글나무", "정글"], "acacia": ["아카시아나무", "아카시아"],
         "cherry": ["벚나무", "벚꽃나무"], "dark_oak": ["짙은 참나무", "다크오크"], "mangrove": ["맹그로브나무", "맹그로브"]}
PICK_ASK = "되묻기"
PICK_GRP = {"grp:log": [f"{s}_log" for s in SP_KO], "grp:planks": [f"{s}_planks" for s in SP_KO],
            "grp:meat": ["beef", "porkchop", "chicken", "mutton", "cooked_beef", "cooked_porkchop", "cooked_chicken", "cooked_mutton"],
            "grp:pickaxe": [f"{t}_pickaxe" for t in ("wooden", "stone", "iron", "golden", "diamond")], "grp:sword": [f"{t}_sword" for t in ("wooden", "stone", "iron", "golden", "diamond")],
            "grp:axe": [f"{t}_axe" for t in ("wooden", "stone", "iron", "diamond")], "grp:iron": ["raw_iron", "iron_ingot"]}
TIER_I = {"wooden": 1, "golden": 1, "stone": 2, "iron": 3, "diamond": 4, "netherite": 5}


def sp_forms(item):
    """종 지정 목재 표현 (아카시아 나무·자작 원목·가문비 판자)"""
    m = re.match(r"(.+)_(log|planks)$", item)
    if not m or m.group(1) not in SP_KO:
        return []
    out = []
    for s in SP_KO[m.group(1)]:
        b = s[:-2] if s.endswith("나무") else s
        out += [f"{s} 판자", f"{b} 판자"] if m.group(2) == "planks" else [f"{s} 원목", f"{b} 나무", f"{b}나무", f"{s} 통나무", f"{b} 통나무"]
    return out


for _s in SP_KO:  # E: 종+나무 표현 → turn 학습 표면형
    for _i in (f"{_s}_log", f"{_s}_planks"):
        C.EXTRA[_i] = list(dict.fromkeys(C.EXTRA.get(_i, []) + sp_forms(_i)))


def pick_ctx(typ, rest=""):
    return f"행동: {TYPES[typ]}" + (f" | {rest}" if rest else "")


def pick_label(typ, spec, cands, inv):
    """spec = 발화가 가리킨 실물(없으면 None). 후보 보기 인덱스, 되묻기 = len(cands)"""
    if spec:
        return cands.index(spec) if spec in cands else len(cands)
    if len(cands) == 1:
        return 0
    if typ == "equip" and re.search(r"_(pickaxe|sword|axe)$", cands[0]):
        return max(range(len(cands)), key=lambda i: TIER_I.get(cands[i].split("_")[0], 0))
    if typ == "drop" or re.search(r"_(pickaxe|sword|axe)$", cands[0]) and typ == "give":
        return len(cands)
    return max(range(len(cands)), key=lambda i: inv[cands[i]])


def rows_pick(r, n):
    out = []
    verbs = {"give": E_GIVE, "drop": E_DROP, "equip": E_EQUIP, "store": E_STORE, "place": E_PLACE}
    for _ in range(n):
        g = r.choice(list(PICK_GRP))
        typ = r.choice(["equip", "equip", "give", "drop"] if re.search("pickaxe|sword|axe", g) else ["give", "give", "drop", "drop", "store"])
        cands = r.sample(PICK_GRP[g], min(len(PICK_GRP[g]), r.choice([1, 2, 2, 3, 3, 4])))
        inv = {c: (1 if re.search(r"_(pickaxe|sword|axe)$", c) else r.choice([1, 3, 5, 8, 16, 32, 64])) for c in cands}
        spec = None
        if r.random() < 0.45:  # 수식어로 특정 (보유 or 미보유)
            spec = r.choice(PICK_GRP[g])
            fs = sp_forms(spec)
            u = r.choice(fs) if fs and r.random() < 0.8 else C.surface(r, spec)
        else:
            u = r.choice(C.GROUPS[g][1])
        u = tail(r, u + " " + r.choice(verbs[typ]))
        o = list(cands)
        r.shuffle(o)
        out.append({"kind": "pick", "utt": u, "ctx": pick_ctx(typ), "opts": [f"{ko(c)} {inv[c]}개" for c in o] + [PICK_ASK], "y": pick_label(typ, spec, o, inv)})
    return out


# 조언 대응 (F, Q): 지적·조언 발화 → 행동 변화
HACT = ["설명하고 계속 진행", "다른 방법으로 재계획", "멈추고 되묻기", "주변 위험 먼저 확인", "인벤·설치물 재확인 후 이어서"]


def hint_ctx(goal_ko, step_ko, via_ko, faster, threat):
    return (f"GOAL: {goal_ko or '없음'} | 현재 단계: {step_ko or '없음'} | 방법: {via_ko or '없음'} | 더 빠른 방법 {'있음' if faster else '없음'}"
            f" | 위협: {threat or '없음'}")


def hint_label(h, goal, faster):
    if h == "danger":
        return HACT[3]
    if not goal:
        return HACT[2] if h == "wrong" else HACT[0]
    return {"slow": HACT[1] if faster else HACT[0], "wrong": HACT[2], "short": HACT[4], "done_claim": HACT[4]}[h]


def rows_hintact(r, n):
    out = []
    for _ in range(n):
        h = r.choice(H_KEYS)
        goal = r.choice(PLAN_GOALS + [None, None])
        st = r.choice([("log", "oak_log"), ("mine", "stone"), ("mine", "iron_ore"), ("craft", "iron_pickaxe"), ("furnace", "iron_ingot")]) if goal else None
        faster = r.random() < 0.5
        u = tail(r, r.choice(HINT_T[h]))
        ctx = hint_ctx(ko(goal) if goal else None, f"{P.TYPE_KO.get(st[0], st[0])} {ko(st[1])}" if st else None, r.choice(["바로 제작", "돌 곡괭이 경유", "연료 석탄"]) if goal else None,
                       faster, r.choice([None, None, None, "좀비 8칸", "크리퍼 5칸"]))
        out.append({"kind": "hintact", "utt": u, "ctx": ctx, "opts": HACT, "y": HACT.index(hint_label(h, goal, faster))})
    return out


def rows_judge(r, n):
    """0.3 판단 문항 전체. n = 문항당 기본 행수 (가중)"""
    w = {rows_food: 1.0, rows_weapon: 1.0, rows_target: 0.8, rows_hunt: 0.6, rows_explore: 0.8, rows_fail: 1.4, rows_recover: 0.6, rows_qty: 1.5, rows_pick: 1.5, rows_hintact: 0.8}
    out = []
    for f, k in w.items():
        rs = f(r, int(n * k))
        for x in rs:
            u, q = JQ[x["kind"]]
            x.setdefault("utt", u); x["q"] = q
        out += rs
    return out


def main():
    r = random.Random(int(os.environ.get("SEED", 1)))
    banned = set()
    for l in open(f"{H}/chat_raw.jsonl"):
        banned.add(json.loads(l)["text"].strip())
    nt, npl, npr = int(os.environ.get("NT", 200000)), int(os.environ.get("NP", 40000)), int(os.environ.get("NR", 30000))
    rows = rows_turn(r, nt, banned) + rows_plan(r, npl) + rows_prio(r, npr) + rows_tidy(r, int(os.environ.get("NTD", 20000))) + rows_judge(r, int(os.environ.get("NJ", 8000))) + rows_incident()
    r.shuffle(rows)
    nd = len(rows) // 50
    os.makedirs(f"{H}/gen", exist_ok=True)
    for name, part in (("dev", rows[:nd]), ("train", rows[nd:])):
        with open(f"{H}/gen/{name}.jsonl", "w") as f:
            for x in part:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(len(rows), "dev", nd)


if __name__ == "__main__":
    main()
