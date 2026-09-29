"""아이템·몹·가상그룹 목록(모델 링크 bank) + 학습용 표현 생성기(줄임말·구어). 서빙에선 entries/name_text/parse_count만 씀
- 줄임말 사전은 데이터 생성 전용. 모델이 학습으로 익힘 (items.nick 룩업 금지 방침)
- HOLDOUT: 학습에 안 넣는 조합 → 일반화 검사용
"""
import os, random, re, sqlite3
from functools import lru_cache

MCDB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../mcdata/mc.db")

MAT = {"wooden": ["나무", "목재"], "stone": ["돌"], "iron": ["철", "쇠"], "golden": ["금", "황금"],
       "diamond": ["다이아", "다이아몬드", "다야"], "netherite": ["네더라이트", "네더"], "copper": ["구리"],
       "leather": ["가죽"], "chainmail": ["사슬"]}
MAT_S = {"wooden": ["나"], "stone": ["돌"], "iron": ["철"], "golden": ["금"], "diamond": ["다", "다이아"], "netherite": ["네", "네더"], "copper": ["구"]}
PART = {"pickaxe": ["곡괭이", "곡갱이", "곡광이", "꼭괭이", "곡괭"], "axe": ["도끼"], "sword": ["검", "칼"], "shovel": ["삽"], "hoe": ["괭이"],
        "helmet": ["투구", "헬멧", "뚝배기", "머리", "모자"], "chestplate": ["흉갑", "갑빠", "상의", "가슴팍", "갑옷", "갑옷"],
        "leggings": ["레깅스", "바지", "하의", "각반"], "boots": ["부츠", "신발", "장화"]}
PART_S = {"pickaxe": ["곡"], "axe": ["도끼"], "sword": ["검", "칼"], "shovel": ["삽"], "helmet": ["뚝", "헬", "뚝배기"],
          "chestplate": ["갑빠", "흉", "갑"], "leggings": ["바지", "각"], "boots": ["신", "부츠"]}
HOLDOUT = {("golden", "helmet"), ("diamond", "boots"), ("netherite", "pickaxe"), ("stone", "shovel"), ("copper", "sword")}
EXTRA = {  # 공식명 외 흔한 부름. 학습 표현
    "crafting_table": ["작업대", "제작대", "크래프팅 테이블", "작대"], "furnace": ["화로", "퍼니스"], "torch": ["횃불", "토치"],
    "stick": ["막대기", "막대", "스틱", "나무막대"], "cobblestone": ["조약돌", "코블", "코블스톤"], "stone": ["돌", "스톤"],
    "cooked_beef": ["스테이크", "구운 소고기", "익힌 소고기"], "beef": ["생소고기", "날소고기", "소고기"], "chest": ["상자", "체스트"],
    "coal": ["석탄", "석탄덩이"], "raw_iron": ["철 원석", "철원석", "생철"], "iron_ingot": ["철괴", "철 주괴", "철덩이", "철 잉곳"],
    "diamond": ["다이아", "다이아몬드", "다야"], "white_bed": ["침대"], "wheat_seeds": ["씨앗", "밀 씨앗", "밀씨"], "bread": ["빵"],
    "dirt": ["흙"], "sand": ["모래"], "glass": ["유리"], "lava_bucket": ["용암 양동이", "용암"], "water_bucket": ["물 양동이", "물"],
    "bucket": ["양동이", "빈 양동이", "바께스"], "obsidian": ["흑요석", "옵시디언"], "gravel": ["자갈"], "grass_block": ["잔디", "잔디 블록"],
    "shield": ["방패"], "bow": ["활"], "arrow": ["화살"], "bamboo": ["대나무"], "leather": ["가죽"], "andesite": ["안산암"],
    "iron_ore": ["철광석", "철 광석"], "coal_ore": ["석탄 광석"], "diamond_ore": ["다이아 광석"], "oak_planks": ["참나무 판자"],
}
GROUPS = {  # 가상 항목: id → (표시이름, 학습 표현)
    "grp:log": ("나무 원목 아무거나", ["나무", "원목", "통나무", "나무토막"]),
    "grp:planks": ("판자 아무거나", ["판자", "나무판자", "목재"]),
    "grp:meat": ("고기 아무거나", ["고기", "고기점", "괴기", "육류"]),
    "grp:food": ("먹을 것 아무거나", ["먹을거", "먹을 것", "음식", "밥", "식량", "먹을꺼"]),
    "grp:iron": ("철 (원석·괴)", ["철", "쇠"]),
    "grp:gold": ("금 (원석·괴)", ["금", "골드"]),
    "grp:copper": ("구리 (원석·괴)", ["구리"]),
    "grp:item_all": ("가진 템 전부", ["템", "아이템", "템 다", "다", "전부", "몽땅"]),
    "grp:pickaxe": ("곡괭이 아무거나", ["곡괭이", "곡갱이", "곡"]),
    "grp:axe": ("도끼 아무거나", ["도끼"]), "grp:sword": ("검 아무거나", ["검", "칼", "무기"]),
    "grp:armor": ("갑옷 아무거나", ["갑옷", "장비", "방어구"]),
    "place:home": ("집", ["집", "베이스", "기지"]), "place:death": ("죽은 곳", ["죽었던 곳", "죽은 데", "사망 위치", "템 떨군 곳"]),
    "place:here": ("말한 사람 위치", ["여기", "이리", "일루", "요기"]),
}
for m in ("iron", "diamond", "golden", "netherite", "leather", "chainmail", "copper"):
    ko = MAT[m][0]
    GROUPS[f"set:{m}_armor"] = (f"{ko} 갑옷 풀세트(투구·흉갑·레깅스·부츠)", [f"{ko}셋", f"{ko}세트", f"{ko} 셋", f"{ko} 세트", f"{ko} 풀셋", f"{ko}풀셋", f"{ko} 풀세트", f"{ko}풀세트", f"{ko}갑옷 풀셋", f"{ko} 갑옷 풀세트", f"{ko}갑옷 세트", f"{ko} 갑옷세트",
                                                                          f"{ko}장비", f"{ko} 풀장비", f"{ko} 장비 풀셋", f"{ko}셋트", f"{ko} 방어구 세트"])  # {ko}갑옷 단독=흉갑
for m in ("wooden", "stone", "iron", "diamond", "golden", "netherite", "copper"):
    ko = MAT[m][0]
    GROUPS[f"set:{m}_tools"] = (f"{ko} 도구 세트(곡괭이·도끼·검·삽)", [f"{ko} 도구", f"{ko}도구 세트", f"{ko} 연장"])


@lru_cache(1)
def entries():
    """[(id, 이름텍스트)]. [0]은 NULL(모름). 이름텍스트 = bank 인코딩 입력"""
    c = sqlite3.connect(MCDB)
    out = [("null", "모르는 것 (되묻기)")]
    for i, ko, en, kind in c.execute("select id,ko,en,kind from items order by id"):
        out.append((i, f"{ko} {en or ''} {i}".strip()))
    for i, ko, en in c.execute("select id,ko,en from mobs order by id"):
        out.append((f"mob:{i}", f"{ko} (몹) {en if en and en != 'UNKNOWN' else ''} {i}".strip()))
    for k, (name, _) in GROUPS.items():
        out.append((k, name))
    return out


@lru_cache(1)
def index():
    return {k: n for n, (k, _) in enumerate(entries())}


@lru_cache(1)
def ko_names():
    c = sqlite3.connect(MCDB)
    d = {i: ko for i, ko in c.execute("select id,ko from items")}
    d.update({f"mob:{i}": ko for i, ko in c.execute("select id,ko from mobs")})
    d.update({k: v[0] for k, v in GROUPS.items()})
    return d


def surface(rng: random.Random, iid: str, train: bool = True):
    """아이템 id → 사람이 부를 법한 표현 1개. 공식명+띄어쓰기변형+줄임말+EXTRA"""
    forms = []
    ko = ko_names().get(iid, iid)
    if iid in GROUPS:
        forms += GROUPS[iid][1]
    else:
        forms += [ko, ko.replace(" ", "")]
        forms += EXTRA.get(iid, [])
        m = re.match(r"(wooden|stone|iron|golden|diamond|netherite|copper|leather|chainmail)_(pickaxe|axe|sword|shovel|hoe|helmet|chestplate|leggings|boots)$", iid)
        if m and not (train and (m.group(1), m.group(2)) in HOLDOUT):
            a, b = m.groups()
            for x in MAT[a]:
                for y in PART[b]:
                    forms += [f"{x} {y}", f"{x}{y}"]
            for x in MAT_S.get(a, []):
                for y in PART_S.get(b, []):
                    forms += [f"{x}{y}"] * 3  # 줄임말 가중
        elif m:
            forms = [ko, ko.replace(" ", "")]
    return rng.choice(forms or [ko])


def holdout_forms():
    out = []
    for a, b in HOLDOUT:
        for x in MAT_S.get(a, []):
            for y in PART_S.get(b, []):
                out.append((f"{x}{y}", f"{a}_{b}"))
    return out


KNUM = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "석": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10,
        "스무": 20, "스물": 20, "서른": 30, "마흔": 40, "쉰": 50}


def parse_count(s: str):
    """개수 구간 텍스트 → 정수. 세트/셋/스택=64, 반세트=32. 실패시 None"""
    s = re.sub(r"(만|씩|정도|쯤)$", "", s.replace(" ", ""))
    mul = 1
    if re.search(r"(세트|셋|스택|셑|쎗)$", s) and not re.fullmatch(r"(셋)", s):
        mul = 64
        s = re.sub(r"(세트|셋|스택|셑|쎗)$", "", s)
        if s in ("", "한", "1"):
            return 64
        if s == "반":
            return 32
    s = re.sub(r"(개|개만|개씩|마리|칸|번|덩이|묶음)$", "", s)
    if re.fullmatch(r"\d+", s):
        return int(s) * mul
    if s in KNUM:
        return KNUM[s] * mul
    m = re.fullmatch(r"(열|스무|스물|서른|마흔|쉰)(한|하나|두|둘|세|셋|네|넷|다섯|여섯|일곱|여덟|아홉)?", s)
    if m:
        return (KNUM[m.group(1)] + (KNUM[m.group(2)] if m.group(2) else 0)) * mul
    return None


def count_surface(rng: random.Random, n: int):
    """정수 → 개수 표현"""
    if n == 64 and rng.random() < 0.6:
        return rng.choice(["한세트", "한 세트", "1세트", "한셋", "1셋", "한 스택", "64개"])
    if n == 32 and rng.random() < 0.4:
        return rng.choice(["반세트", "반 세트", "32개"])
    if n == 128 and rng.random() < 0.5:
        return rng.choice(["두세트", "2세트", "두 셋"])
    kn = {1: ["한개", "하나", "한 개", "1개"], 2: ["두개", "두 개", "2개", "둘"], 3: ["세개", "세 개", "3개", "셋"], 4: ["네개", "4개", "네 개"],
          5: ["다섯개", "5개"], 10: ["열개", "10개"], 20: ["스무개", "20개"]}
    if n in kn and rng.random() < 0.6:
        return rng.choice(kn[n])
    return rng.choice([f"{n}개", f"{n}개", f"{n} 개", f"{n}"])
