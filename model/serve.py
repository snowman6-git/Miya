"""Miya 서빙 (stdlib http). POST JSON
/turn {utt, state|ctx, hist?} → {act, act_p, type, query, hint, spans:[{text,label,item,ko,count,score}], goals:[{item,ko,count}], ctx}
/plan {goal, cnt, inv, placed, near, hp, night, armor, req?} → {opts, pick, p, val, via, steps} (QED 경험 자동 주입)
/prio {ctx}                 → {label, p}
/qed  {req, goal, cnt, via, ok, ms, fail?, steps:[{type,target,cnt,tool,ms,ok,fail?}]} → QED DB(data/qed.db) 기록
/ko   {ids:[..]}            → {id: 한국어}
/death {req?, cause, killer?, hp, food, night, armor, weapon, pos, dim, inv, vars?} → {id, inv_value, top} 사망 기록
/value {inv}                → {total, items:{id:v}} 아이템 가치 (기본값 + 경험 보정)
/tidy {inv, goal?, cnt?, free, chest_d?, sit} → {acts:[{item,ko,n,act}]} 인벤 정리 판단(모델)
/placed {add?|del?|kind?|all?} → {list} 내 설치물(상자 소유 구분), del=좌표 kind=종류 all=전부 삭제
/lesson {}                  → {death:{killer,cause,n}|null} prio ctx '최근 사망원인'용
/choose {utt, ctx, qid, opts} → {k, p}  벤치(eval/bench.py)용 원시 선택
0.3 판단(봇 규칙→Miya, ctx·보기 텍스트 = gen.py 공용 함수):
/food {inv, hp, food, fight?, task?}           → {item|null, p}
/weapon {inv, dur?:{id:%}, mob, d, n, hp, armor} → {item(hand|id), shield, p}
/target {threats:[[mob,d]], hp, weapon, armor, why?} → {i, p}
/hunt {animals:[[mob,d,n]], food, has_food, want?} → {i|null(원정), p}
/explore {target, y, night, hop, dirs:[{f:{나무..},v}]×8(북부터 시계)} → {i, dir, p}
/fail {goal, step:{type,target}, reason, tries, replans, streak, hp, night, player} → {act:retry|replan|help|giveup, label, p}
/recover {inv, d, el, cause, night, armor, weapon, hp} → {go, value, p}
/hintact {utt, hint?, goal?, step?, threat?} → {act, label, p}  (turn 이 지적·조언이면 자동 포함)
/turn: give·drop·equip·store·place 묶음 대상 → 실물 선택(pick), give·drop·craft 개수 없음·다·좀·더·까지 → 수량 의미(qty). 되묻기면 goal.ask
봇은 판단 안 함: 이 결과만 실행. CK=ckpt 경로, PORT=기본 8765, SERVE_HOST=바인드(원격 봇이면 0.0.0.0)
"""
import glob, json, math, os, re, sqlite3, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer

import torch

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H); sys.path.insert(0, f"{H}/../data")
import catalog as C  # noqa: E402
import gen as G  # noqa: E402
import planner as P  # noqa: E402
from eval import Runner  # noqa: E402
from miya import collate, pack  # noqa: E402

CK = os.environ.get("CK") or next(c for c in (f"{H}/../ckpt/miya-0.3", f"{H}/../ckpt/miya-0.21", f"{H}/../ckpt/miya-0.2", f"{H}/../ckpt/miya-0.1a") if glob.glob(f"{c}/model.*"))  # 최신 ckpt
R = Runner(CK)
SCH = json.load(open(os.path.join(CK, "schema.json")))
TIDY_OK = "tidy" in SCH
JUDGE_OK = "judge" in SCH  # 0.3+: 판단 문항 학습됨. 아니면 기존 규칙 폴백  # 미학습 ckpt면 정리 판단 끔(쓰레기값으로 템 버림 방지)
QDB = sqlite3.connect(os.environ.get("QED", f"{H}/../data/qed.db"), check_same_thread=False)
QDB.executescript("""
create table if not exists goals(id integer primary key, ts real, req text, goal text, cnt int, via text, ok int, ms int, fail text, ctx text);
create table if not exists steps(goal_id int, i int, type text, target text, cnt int, tool text, ms int, ok int, fail text);
create index if not exists g_via on goals(goal, via);
create table if not exists deaths(id integer primary key, ts real, goal_id int, req text, cause text, killer text, hp int, food int, night int,
  armor int, weapon text, pos text, dim text, inv text, inv_value real, vars text, recover text, fix text);
create table if not exists placed(kind text, x int, y int, z int, ts real, primary key(x, y, z));""")
if "vars" not in [r[1] for r in QDB.execute("pragma table_info(goals)")]:
    QDB.execute("alter table goals add column vars text")  # 변수: 보유 도구 티어·장비·시간 등 (같은 방법도 조건따라 결과 다름)


@torch.no_grad()
def choose(utt, ctx, qid, opts):
    """단일 문항 → (argmax, 확률목록, 가치[[log1p초, ok logit]])"""
    p = pack(R.tok, utt, ctx, {qid: opts}, [], None)
    b = collate([p], R.dev)
    o = R.m(b)
    pr = o["opt"][0, :len(opts)].softmax(-1)
    return int(pr.argmax()), pr.tolist(), o["val"][0, :len(opts)].tolist()


def turn(x):
    ctx = x["ctx"] if "ctx" in x else G.ctx_text(None, x["state"])  # ctx 직접 or state 로 생성
    utt = x["utt"]
    if x.get("hist"):  # 멀티턴: 직전 사용자·봇 발화
        utt = f"이전 나: {x['hist'][0]} / 봇: {x['hist'][1]} ▶ {utt}"
    out, spans = R.turn(utt, ctx)
    y = {"act": G.ACTS[out["act"][0]], "act_p": out["act"][1], "type": G.TYPE_KEYS[out["type"][0]], "type_p": out["type"][1],
         "query": G.Q_KEYS[out["query"][0]], "hint": G.H_KEYS[out["hint"][0]]}
    sp = []
    for t, lab, item, sc, _ in spans:
        d = {"text": t.strip(), "label": lab, "item": item, "ko": (P.ko(item) if P.ko(item) != item else t.strip()) if item else None, "score": round(sc, 3)}
        if lab in ("개수", "거리"):
            d["count"] = C.parse_count(t)
        sp.append(d)
    # 짝으로 GOAL 목록: 대상별 {item, count}
    goals, cnt_of = [], {}
    for k, j in out.get("pairs", {}).items():
        if j is not None:
            cnt_of[j] = sp[k].get("count")
    for k, d in enumerate(sp):
        if d["label"] in ("대상",) and d["item"]:
            goals.append({"item": d["item"], "ko": d["ko"], "count": cnt_of.get(k)})
    if y["type"] in HELD and x.get("state"):
        goals = held(goals, x["state"].get("inv", {}), y["type"], x["utt"]) if JUDGE_OK else held_rule(goals, x["state"].get("inv", {}))
    if JUDGE_OK and y["act"] == "목표 실행" and y["type"] in ("give", "drop", "craft") and x.get("state"):
        goals = [qty(g, y["type"], x["utt"], x["state"].get("inv", {})) for g in goals]
    if JUDGE_OK and y["act"] == "지적·조언":
        y["hact"] = hintact({"utt": x["utt"], "hint": y["hint"], **(x.get("task") or {})})
    y["spans"], y["goals"], y["ctx"] = sp, goals, ctx
    return y


# 보유템 대상 행동: 그룹(grp:/set:) → 실제 보유 아이템 (조회, 판단 아님). 전부·세트는 전체, 그외 최다 1개
HELD = {"give", "drop", "equip", "place", "eat", "store"}
GRP_RE = {"grp:log": r"_(log|stem)$", "grp:planks": r"_planks$", "grp:meat": r"(beef|porkchop|chicken|mutton|rabbit|cod|salmon)$",
          "grp:iron": r"^(raw_iron|iron_ingot)$", "grp:gold": r"^(raw_gold|gold_ingot)$", "grp:copper": r"^(raw_copper|copper_ingot)$",
          "grp:pickaxe": r"_pickaxe$", "grp:axe": r"_axe$", "grp:sword": r"_sword$", "grp:armor": r"_(helmet|chestplate|leggings|boots)$",
          "grp:food": r"(beef|porkchop|chicken|mutton|rabbit|cod|salmon|bread|apple|carrot|potato|melon_slice|cookie|pie|stew|berries)$", "grp:item_all": r"."}
ALL = ("grp:item_all", "grp:armor", "set:")


def fam(item):
    """아이템 → 속한 묶음 (종 지정 원목 → grp:log)"""
    return next((g for g, rx in GRP_RE.items() if g not in ALL and g not in ("grp:food",) and re.search(rx, item)), None)


def held(goals, inv, typ, utt):
    """묶음/미보유 대상 → 보유 실물 후보 중 모델 선택 (pick). 전부·세트는 전체. 되묻기 → ask"""
    out = []
    for g in goals:
        it = g["item"]
        if it in inv or it.startswith(ALL):
            out += held_rule([g], inv); continue
        grp = it if it.startswith("grp:") else fam(it)
        cands = sorted((k for k in inv if grp and re.search(GRP_RE.get(grp, "^$"), k)), key=lambda k: -inv[k])[:6]
        if not cands:
            out.append(g); continue
        k, pr, _ = choose(utt, G.pick_ctx(typ if typ in G.TYPES else "give"), "실물", [f"{P.ko(c)} {inv[c]}개" for c in cands] + [G.PICK_ASK])
        out.append({"item": cands[k], "ko": P.ko(cands[k]), "count": g["count"], "pick_p": round(pr[k], 3)} if k < len(cands) else
                   {**g, "ask": "which", "cands": [P.ko(c) for c in cands]})
    return out


def qty(g, typ, utt, inv):
    """수량 의미 (qty) → 실제 개수 계산은 여기(사실). 전부·1개·절반·추가·총·되묻기"""
    it = g["item"]
    if g.get("ask") or it.startswith(("grp:", "set:")):
        return g
    h = inv.get(it, 0)
    k, pr, _ = choose(utt, G.qty_ctx(typ, it, h), "수량", G.QTY)
    n = g.get("count")
    q = G.QTY[k]
    c = {"전부": h, "1개": 1, "절반": max(1, math.ceil(h / 2)), "말한 개수(추가로)": n, "말한 개수 맞추기(총)": None if n is None else n - h}.get(q)
    out = {**g, "qty": q, "qty_p": round(pr[k], 3)}
    if q == "되묻기" or c is None and q != "되묻기" and typ != "craft":
        out["ask"] = "count"; out["held"] = h
    elif c is not None:
        out["count"] = max(0, c) if typ == "craft" else min(max(c, 0), h) if h else c
    return out


def held_rule(goals, inv):
    out = []
    for g in goals:
        it = g["item"]
        if it in inv or not it.startswith(("grp:", "set:")):
            out.append(g); continue
        ks = [k for k in inv if k in P.GOAL_SETS.get(it, [])] if it.startswith("set:") else [k for k in inv if re.search(GRP_RE.get(it, "^$"), k)]
        if not ks:
            out.append(g); continue
        ks = sorted(ks, key=lambda k: -inv[k])
        out += [{"item": k, "ko": P.ko(k), "count": g["count"] if not it.startswith(ALL) else None} for k in (ks if it.startswith(ALL) else ks[:1])]
    return out


def plan(x):
    inv, placed, near = x.get("inv", {}), x.get("placed", {}), x.get("near", {})
    goal, cnt = x["goal"], int(x.get("cnt") or 1)
    gi = set(P.GOAL_SETS.get(goal, [goal]))
    spec = {goal} if goal in P.WOOD else set()  # 종 지정 목재 GOAL(아카시아 캐와)만 종 구분
    pinv = {k: v for k, v in P.wood(inv, spec).items() if k not in gi}  # 요청은 "n개 더" (보유분 무시, 봇 실행도 보유+n 기준)
    ms = P.methods(goal, cnt, pinv, {"placed": placed, "near": P.wood(near, spec, True)}, k=6)
    if not ms:
        return {"opts": [], "pick": -1, "steps": [], "goal_set": sorted(gi)}
    qed = {m["via"]: q for m in ms if (q := qed_of(goal, m["via"]))}
    ask = [] if x.get("noask") else ["ask | 플레이어에게 도움 요청하고 대기 | 예상 300초 위험 0%"]  # noask: 도움요청에 혼자해 답 → ask 후보 제외
    opts = [P.method_text(m, qed.get(m["via"]), maxstep=4) for m in ms] + ask
    inv_s = ", ".join(f"{P.ko(k)} {v}" for k, v in inv.items()) or "비어있음"
    ctx = (f"GOAL: {P.ko(goal)} {cnt} | 체력 {x.get('hp', 20)}/20 {'밤' if x.get('night') else '낮'} {'갑옷 있음' if x.get('armor') else '갑옷 없음'}"
           f" | 인벤: {inv_s} | 설치: " + (", ".join(f"{P.ko(k)} {v}칸" for k, v in placed.items()) or "없음") +
           " | 주변: " + ", ".join(f"{'용암' if b == 'lava' else P.ko(b)} {d}칸" for b, d in near.items() if d is not None))
    k, pr, val = choose("방법 선택", ctx, "방법", opts)
    via = ms[k]["via"] if k < len(ms) else "ask"
    qi = None
    if qed:  # QED 발현 판정: 경험 빼고 한번 더 선택 → 다르면 경험이 결정 바꿈
        k0 = choose("방법 선택", ctx, "방법", [P.method_text(m, None, maxstep=4) for m in ms] + ask)[0]
        qi = {"changed": core(ms[k0]["via"] if k0 < len(ms) else "ask") != core(via), "base": ms[k0]["via"] if k0 < len(ms) else "ask", "ev": qed}
        qi["base_ko"] = via_ko(qi["base"])
    steps = ms[k]["steps"] if k < len(ms) else []
    for s in steps:  # 채광 목표 높이 (ore_gen 사실) → 봇 계단굴 모드가 사용
        if s["type"] == "mine" and x.get("y") is not None and (oy := P.ore_y(s["target"], x["y"])) is not None:
            s["y"] = oy
    for s in steps:  # 종 지정 아니면 아무 원목/판자 (봇이 주변·보유 종으로 실행)
        if s["target"] in ("oak_log", "oak_planks") and not spec or s.get("fuel") in ("oak_log", "oak_planks"):
            s["any"] = True
    why = {}  # 채팅 사유용 사실 (말투는 봇 replies.json). 같은 종류 묶음: 제작대, 화로는 있는거 쓸게요
    for t, _, v in (x.partition(":") for x in via.split(",")):
        if t in ("reuse", "fuel", "via"):
            why.setdefault(t, []).append({"lava": "용암", "oak_log": "원목", "oak_planks": "판자"}.get(v) or P.ko(v))
    why = [{"k": t, "ko": ", ".join(v)} for t, v in why.items()]
    fk = lambda v: ", ".join(dict.fromkeys({"lava": "용암", "oak_log": "원목", "oak_planks": "판자"}.get(f) or P.ko(f) for t, _, f in (x.partition(":") for x in v.split(",")) if t == "fuel")) or "가진 연료"
    if k < len(ms) and (alt := max((j for j, m in enumerate(ms) if j != k and m["via"] != "ask" and fk(m["via"]) != fk(via)), key=lambda j: pr[j], default=None)) is not None:
        for w in why:  # 연료 사유: 다른 연료 쓰는 차선(모델 확률)과 사실 비교 (예상 시간·위험). 선택은 모델
            if w["k"] == "fuel":
                a, m = ms[alt], ms[k]
                w.update(k="fuel_vs", alt=fk(a["via"]), dt=round((a["est_ms"] - m["est_ms"]) / 1000), dr=round((a["risk"] - m["risk"]) * 100))
                w["k"] = "fuel_fast" if w["dt"] > 0 else "fuel_safe" if w["dr"] > 0 else "fuel_exp" if qed.get(via) else "fuel"
    if (e := qed.get(via)) and e.get("n"):
        ch = qi and qi["changed"]
        why.append({"k": "qed_changed" if ch else "qed", "ko": via_ko(core(via)), "base": via_ko(core(qi["base"])) if ch else "", "n": e["n"], "ok": round(e["ok"] * 100)})
    detail = {"ctx": ctx, "pick": via, "pick_ko": via_ko(via), "qed_changed": bool(qi and qi["changed"]), "qed_base": qi and via_ko(qi["base"]),
              "opts": [{"via": m["via"], "ko": via_ko(m["via"]), "p": round(pr[j], 4), "pick": j == k, "est_s": round(m["est_ms"] / 1000), "risk": round(m["risk"] * 100),
                        "val_s": round(math.expm1(val[j][0])), "val_ok": round(100 / (1 + math.exp(-val[j][1]))), "qed": qed.get(m["via"]),
                        "steps": [P.step_text(x) for x in m["steps"]]} for j, m in enumerate(ms)]
              + [{"via": "ask", "ko": "도움 요청", "p": round(pr[-1], 4), "pick": k >= len(ms), "est_s": 300, "risk": 0}] * bool(ask)}  # 모달 상세용 (판단 근거 전부)
    LAST.update(goal=goal, via_ko=via_ko(via), faster=k < len(ms) and any(m["est_ms"] < ms[k]["est_ms"] * 0.7 for m in ms))
    return {"why": why, "detail": detail, "opts": opts, "pick": k, "p": pr, "val": [[round(math.expm1(a), 1), 1 / (1 + math.exp(-b))] for a, b in val],
            "via": via, "via_ko": via_ko(via), "steps": steps, "ctx": ctx, "qed": qi, "goal_set": sorted(gi)}


def via_ko(via):
    """via 토큰 → 한글 표기 (webui·로그 표시용, 판단엔 미사용)"""
    if via in ("direct", "ask"):
        return {"direct": "바로 제작", "ask": "도움 요청"}[via]
    f = {"reuse": "{} 재사용", "fuel": "연료 {}", "via": "{} 경유"}
    return ", ".join(f.get(k, "{}").format("용암" if v == "lava" else P.ko(v)) for k, _, v in (t.partition(":") for t in via.split(",")))


def core(via):
    """경험 묶음 키: via: 토큰(중간 도구 경로)만. reuse:/fuel: 은 조건(변수)이라 제외 → 같은 방법 경험 합산"""
    return via if via == "ask" else ",".join(t for t in via.split(",") if t.startswith("via:")) or "direct"


def qed_of(goal, via):
    """경험 요약: 같은 goal·방법(core) 과거 기록 → method_text용 dict"""
    # stopped(유저 멈춤·선점)은 성패 아님 → 제외. 단 그 작업중 사망이면 실패(death). craft_unsynced=봇 버그(수정됨) 제외
    rs = QDB.execute("select g.ok, g.ms, case when d.id is not null then 'death' else g.fail end, g.via from goals g left join deaths d on d.goal_id=g.id"
                     " where g.goal=? and not (ifnull(g.fail,'')='stopped' and d.id is null) and ifnull(g.fail,'')!='craft_unsynced'"
                     " order by g.id desc limit 60", (goal,)).fetchall()
    c = core(via)
    rs = [r for r in rs if core(r[3]) == c][:20]
    if not rs:
        return None
    okms = [r[1] for r in rs if r[0]]
    q = {"n": len(rs), "ok": len(okms) / len(rs), "avg_ms": int(sum(okms) / len(okms)) if okms else 0}  # 소요시간은 성공분만
    rf = 0
    for r in rs:  # 최근 연속 실패
        if r[0]:
            break
        rf += 1
    if rf:
        q["recent_fail"], q["fail"] = rf, rs[0][2]
    return q


def qed(x):
    c = QDB.execute("insert into goals(ts,req,goal,cnt,via,ok,ms,fail,ctx,vars) values(?,?,?,?,?,?,?,?,?,?)",
                    (time.time(), x.get("req"), x["goal"], x.get("cnt"), x["via"], int(x["ok"]), int(x["ms"]), x.get("fail"), x.get("ctx"),
                     json.dumps(x.get("vars"), ensure_ascii=False) if x.get("vars") else None))
    QDB.executemany("insert into steps values(?,?,?,?,?,?,?,?,?)",
                    [(c.lastrowid, i, s["type"], s["target"], s.get("cnt"), s.get("tool"), int(s.get("ms", 0)), int(s.get("ok", 0)), s.get("fail"))
                     for i, s in enumerate(x.get("steps", []))])
    QDB.commit()
    return {"id": c.lastrowid}


def value_of(item):
    """기본값(mcx 재료·희귀도) + 경험 보정: 성공 평균 소요 분당 +1 (얻기 힘들었으면 더 귀함)"""
    v = P.db()["val"].get(item, 0.5)
    r = QDB.execute("select avg(ms) from goals where goal=? and ok=1", (item,)).fetchone()[0]
    return round(v + (r or 0) / 60000, 3)


def value(x):
    items = {k: value_of(k) * n for k, n in x.get("inv", {}).items()}
    return {"total": round(sum(items.values()), 2), "items": items}


def death(x):
    v = value(x)
    g = QDB.execute("select id from goals order by id desc limit 1").fetchone()
    c = QDB.execute("insert into deaths(ts,goal_id,req,cause,killer,hp,food,night,armor,weapon,pos,dim,inv,inv_value,vars) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (time.time(), g and g[0], x.get("req"), x["cause"], x.get("killer"), x.get("hp"), x.get("food"), int(bool(x.get("night"))),
                     x.get("armor"), x.get("weapon"), json.dumps(x.get("pos")), x.get("dim"), json.dumps(x.get("inv", {})), v["total"],
                     json.dumps(x.get("vars"), ensure_ascii=False) if x.get("vars") else None))
    QDB.commit()
    top = sorted(v["items"].items(), key=lambda kv: -kv[1])[:3]
    return {"id": c.lastrowid, "inv_value": v["total"], "top": [[k, round(w, 2)] for k, w in top]}


def lesson(x):
    """최근 1시간 최다 사망원인 → prio ctx. ponytail: 원인별 대응(fix) 학습은 사망 데이터 쌓인 뒤"""
    r = QDB.execute("select killer, cause, count(*) n from deaths where ts > ? group by killer, cause order by n desc, max(ts) desc limit 1",
                    (time.time() - 3600,)).fetchone()
    return {"death": r and {"killer": r[0], "cause": r[1], "n": r[2]}}


@torch.no_grad()
def choose_many(utt, qid, opts, ctxs):
    """같은 문항 여러 문맥 한 배치 → [argmax]"""
    b = collate([pack(R.tok, utt, c, {qid: opts}, [], None) for c in ctxs], R.dev)
    return R.m(b)["opt"][:, :len(opts)].argmax(-1).tolist()


def tidy(x):
    """인벤 정리 판단 {inv, goal?, cnt?, free, chest_d?, sit} → {acts:[{item,n,act}]} (유지 제외)"""
    if not TIDY_OK:
        return {"acts": [], "untrained": True}
    inv, goal = x["inv"], x.get("goal")
    use, space = {}, 3  # GOAL 없음 = 주울 여유칸
    if goal:
        ms = P.methods(goal, int(x.get("cnt") or 1), {k: v for k, v in inv.items() if k not in P.GOAL_SETS.get(goal, [goal])}, {"placed": {}, "near": {}}, k=1)
        if ms:
            use, space = ms[0]["use"], P.space_of(ms[0]["steps"], inv)
    filler = sum(n for k, n in inv.items() if re.search(P.FILLER, k))
    ks = list(inv)
    if not ks:
        return {"acts": []}
    ctxs = [P.tidy_ctx(k, inv[k], value_of(k), min(inv[k], use.get(k, 0)), P.ko(goal) if goal else None, x["free"], x.get("chest_d"), x["sit"], filler, space) for k in ks]
    ys = choose_many("아이템 정리", "정리", G.TIDY, ctxs)
    return {"acts": [{"item": k, "ko": P.ko(k), "n": inv[k], "act": G.TIDY[y]} for k, y in zip(ks, ys) if y]}


def placed(x):
    """내가 설치한 블럭 영구 기록 (남의 상자와 구분) {add?:{kind,x,y,z}, del?:{x,y,z}} → {list}"""
    if a := x.get("add"):
        QDB.execute("insert or replace into placed values(?,?,?,?,?)", (a["kind"], a["x"], a["y"], a["z"], time.time()))
    if d := x.get("del"):
        QDB.execute("delete from placed where x=? and y=? and z=?", (d["x"], d["y"], d["z"]))
    if k := x.get("kind"):
        QDB.execute("delete from placed where kind=?", (k,))
    if x.get("all"):
        QDB.execute("delete from placed")
    QDB.commit()
    return {"list": [dict(zip(("kind", "x", "y", "z"), r)) for r in QDB.execute("select kind, x, y, z from placed")]}


def pick1(utt, ctx, q, opts):
    k, pr, _ = choose(utt, ctx, q, opts)
    return k, round(pr[k], 3)


def food(x):
    fs = {k: n for k, n in x["inv"].items() if k in G.FOOD}
    if not fs:
        return {"item": None}
    ks = list(fs)
    k, p = pick1("음식 선택", G.food_ctx(x.get("hp", 20), x.get("food", 20), x.get("fight"), x.get("task")), "음식", [G.food_opt(i, fs[i]) for i in ks])
    return {"item": ks[k], "ko": P.ko(ks[k]), "p": p}


def weapon(x):
    dur = x.get("dur") or {}
    ws = {w: dur.get(w, 100) for w in x["inv"] if w in G.MELEE}
    ws["hand"] = 100
    o = G.weapon_opts(ws, "shield" in x["inv"])
    k, p = pick1("무기 선택", G.weapon_ctx(x["mob"], x.get("d", 8), x.get("n", 1), x.get("hp", 20), x.get("armor", 0)), "무기", [t for _, t in o])
    w = o[k][0]
    return {"item": w.split("+")[0], "shield": w.endswith("+shield"), "p": p}


def target(x):
    ts = x["threats"]
    k, p = pick1("전투 대상", G.target_ctx(x.get("hp", 20), x.get("weapon") or "맨손", x.get("armor", 0), x.get("why") or "자기방어"), "대상",
                 [f"{P.ko('mob:' + m)} {d}칸" for m, d in ts])
    return {"i": k, "mob": ts[k][0], "p": p}


def hunt(x):
    an = x["animals"]
    k, p = pick1("사냥 대상", G.hunt_ctx(x.get("food", 20), x.get("has_food"), x.get("want") or "사냥해"), "사냥",
                 [f"{P.ko('mob:' + m)} {d}칸 {n}마리" for m, d, n in an] + [G.HUNT_NONE])
    return {"i": k if k < len(an) else None, "mob": an[k][0] if k < len(an) else None, "p": p}


def seek_of(t):
    return "log" if re.search(r"_(log|stem)$|^grp:log", t) else "animal" if t.startswith("mob:") else "sand" if "sand" in t else "water" if re.search("clay|water", t) else "ore"


def explore(x):
    t = x.get("target", "")
    k, p = pick1("탐색 방향", G.explore_ctx(seek_of(t), P.ko(t), x.get("y", 64), x.get("night"), x.get("hop", 1)), "방향",
                 [G.explore_opt(d, e["f"], e.get("v", 0)) for d, e in zip(G.DIRS, x["dirs"])])
    return {"i": k, "dir": G.DIRS[k], "p": p}


def fail(x):
    st = x.get("step") or {}
    rs = QDB.execute("select ok from goals where goal=? and ifnull(fail,'')!='stopped' order by id desc limit 20", (x.get("goal"),)).fetchall()
    qs = f"{len(rs)}회 성공 {round(100 * sum(r[0] for r in rs) / len(rs))}%" if rs else None
    ctx = G.fail_ctx(P.ko(x.get("goal", "")), f"{P.TYPE_KO.get(st.get('type'), st.get('type'))} {P.ko(st.get('target', ''))}", re.sub(r"^err:(?!timeout).*", "err", x["reason"]),
                     x.get("tries", 1), x.get("replans", 0), x.get("streak", 1), qs, x.get("hp", 20), x.get("night"), x.get("player"))
    k, p = pick1("실패 대응", ctx, "대응", G.FAIL)
    return {"act": ("retry", "replan", "help", "giveup")[k], "label": G.FAIL[k], "p": p, "ctx": ctx}


def recover(x):
    v = value(x)
    top = ", ".join(f"{P.ko(k)} {x['inv'][k]}" for k in sorted(v["items"], key=lambda k: -v["items"][k])[:3])
    w = x.get("weapon") or "hand"
    ctx = G.recover_ctx(v["total"], top, x.get("d", 0), x.get("el", 0), x.get("cause", ""), x.get("night"), x.get("armor", 0), "맨손" if w == "hand" else P.ko(w), x.get("hp", 20))
    k, p = pick1("사망 회수", ctx, "회수", G.RECOVER)
    return {"go": k == 0, "value": v["total"], "p": p, "ctx": ctx}


LAST = {}  # 최근 /plan: goal·현재방법·더 빠른 방법 유무 (hintact ctx)


def hintact(x):
    g = x.get("goal")  # 진행중 GOAL 없으면 None (최근 plan 은 같은 GOAL 일때만 참조)
    lp = LAST if g and LAST.get("goal") == g else {}
    ctx = G.hint_ctx(P.ko(g) if g else None, x.get("step"), x.get("via") or lp.get("via_ko"), lp.get("faster", False), x.get("threat"))
    k, p = pick1(x["utt"], ctx, "조언 대응", G.HACT)
    return {"act": ("explain", "replan", "ask", "danger", "recheck")[k], "label": G.HACT[k], "p": p}


def prio(x):
    k, pr, _ = choose("우선순위 판단", x["ctx"], "우선", G.PRIO)
    return {"label": G.PRIO[k], "p": pr[k]}


EP = {"/choose": lambda x: dict(zip(("k", "p"), choose(x["utt"], x["ctx"], x["qid"], x["opts"])[:2])),  # 벤치: 단일 문항 원시 선택
      "/turn": turn, "/plan": plan, "/prio": prio, "/qed": qed, "/death": death, "/value": value, "/lesson": lesson, "/tidy": tidy, "/placed": placed, "/food": food, "/weapon": weapon, "/target": target, "/hunt": hunt, "/explore": explore, "/fail": fail,
      "/recover": recover, "/hintact": hintact, "/ko": lambda x: {i: P.ko(i) for i in x["ids"]}}


class Hd(BaseHTTPRequestHandler):
    def do_POST(self):
        t0 = time.perf_counter()
        try:
            x = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            y = EP[self.path](x)
            y["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            code = 200
        except Exception as e:  # noqa: BLE001
            y, code = {"error": repr(e)}, 500
        b = json.dumps(y, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    print("serve", port, flush=True)
    HTTPServer((os.environ.get("SERVE_HOST", "127.0.0.1"), port), Hd).serve_forever()
