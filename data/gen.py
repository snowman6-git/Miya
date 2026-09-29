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
        "grp:iron", "grp:log", "crafting_table", "furnace", "chest", "bucket", "water_bucket", "lava_bucket", "bamboo", "glass", "diorite", "granite"]
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


VERBS = {"craft": E_CRAFT, "mine": E_GATHER, "log": E_LOG, "dig": E_DIG, "give": E_GIVE, "furnace": E_SMELT, "hunt": E_KILL}


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
    "잡담": ["안녕", "다시 시킬게요", "나중에 다시 시킬게", "이따 시킬게", "잠깐 딴거 할게", "아이고야", "아이고 ㅋㅋ", "헐", "에휴", "ㅎㅇ", "고마워", "잘했어 ㅋㅋ", "굿", "수고", "고마웡 ㅋㅋ", "안뇽", "ㅋㅋㅋㅋ", "잘자", "좋아 좋아", "와 대박", "ㄳ", "땡큐", "나 왔어", "심심하다", "휴 살았다", "ㅎㅎ", "귀엽네", "잘하네"],
    "욕설": ["멍청아 그것도 못해?", "바보냐", "병신아", "야 이 멍청아", "븅신", "개못하네", "쓰레기네", "죽을래?", "닥쳐", "등신아"],
    "위험 경고": ["뒤에 크리퍼!!", "너 익사해", "익사한다", "숨 막히겠다", "너 물에 빠졌어", "빠져 죽겠다", "너 죽는다", "피 없다", "떨어진다", "떨어져 죽어", "용암이야!!", "화살 맞는다", "크리퍼 온다", "좀비 온다", "조심해", "거미 있어", "뒤에 스켈레톤", "위험해", "몹 온다", "옆에 좀비", "피해!!", "용암 조심"],
}
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
            if not any(l == "대상" and it and not it.startswith("ctx:") for _, _, l, it in u0.sp) or ty not in ("craft", "mine", "log", "dig", "give", "furnace", "hunt"):
                continue
            if r.random() < 0.5:  # 봇이 되물음 → 사용자가 풀어 말함
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
        task = r.choice(["철곡괭이 제작", "나무 캐기", "원정(철)", "없음", "따라가기"])
        deaths = r.choice([None, None, "creeper", "skeleton", "zombie", "drown"])
        air = 20 if r.random() < 0.7 else r.randint(0, 19)  # 물속 산소 (0~20, 0이면 익사 데미지)
        free = r.randint(8, 36) if r.random() < 0.75 else r.randint(0, 7)  # 인벤 빈칸
        # 교사 규칙: 생존 1순위
        near = [t for t in threats if t[1] <= (6 if not night and t[0] in ("zombie", "skeleton") else 12)]  # 낮 좀비·스켈 원거리 = 타는중·안다가옴 → 무시 (12칸 스켈 도망 루프)
        danger = 0.0
        for m, d in near:
            mh, ma = mobs.get(m, (20, 3))
            ma = ma or 3
            danger += (ma * (1 - min(armor, 20) * 0.04)) * math.ceil(mh / dmg) * (1.6 if m == "creeper" else 1)
        if air <= 6 or (air <= 12 and (deaths == "drown" or hp <= 8)):  # 익사 직전: 전투·먹기보다 우선
            y = "물 위로 올라가기"
        elif near:
            creeper = any(m == "creeper" and d <= 6 for m, d in near)
            if creeper or (deaths == "creeper" and any(m == "creeper" for m, _ in near)):
                y = "달려서 도망"
            elif danger > hp * 1.2 or len(near) >= 4:
                y = "블럭 쌓아 도망" if any(m in ("zombie", "husk", "spider") for m, _ in near) and len(near) >= 3 else "달려서 도망"
            else:
                y = "근접 전투"
        elif hp <= 10 and has_food and food < 18:
            y = "먹기"
        elif night and armor == 0 and task in ("원정(철)", "나무 캐기") and r.random() < 0.8:
            y = "굴 파고 숨기"
        elif free <= 2:  # 가득: 캔 템 못 주움 → 정리 먼저
            y = "인벤 정리"
        elif task == "없음" and paused:
            y = "멈춘 작업 재개"
        else:
            y = "계속 진행"
        ctx = (f"체력 {hp}/20 배고픔 {food}/20 빈칸 {free}/36" + (f" 산소 {air}/20" if air < 20 else "") + f" {'밤' if night else '낮'} 방어 {armor} 무기 {P.ko(weapon) if weapon != 'hand' else '맨손'} 공격력 {dmg}"
               f" | 음식 {'있음' if has_food else '없음'} | 작업: {task}" + (" | 멈춘작업: " + r.choice(PAUSED_REQ) if paused else "") +
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


def main():
    r = random.Random(int(os.environ.get("SEED", 1)))
    banned = set()
    for l in open(f"{H}/chat_raw.jsonl"):
        banned.add(json.loads(l)["text"].strip())
    nt, npl, npr = int(os.environ.get("NT", 200000)), int(os.environ.get("NP", 40000)), int(os.environ.get("NR", 30000))
    rows = rows_turn(r, nt, banned) + rows_plan(r, npl) + rows_prio(r, npr) + rows_tidy(r, int(os.environ.get("NTD", 20000)))
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
