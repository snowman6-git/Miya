"""벤치 비교용: LAYA 기본(convaiinnovations/laya-multilingual, 제로샷) 서빙. serve.py와 같은 API
사실(planner·QED·설치물)은 serve.py 그대로, 판단(choose·turn)만 LAYA로 교체 → 같은 봇으로 A/B
LAYA엔 구간추출 없음 → 대상=공식 shortlist(아이템 이름 임베딩 top20)+choice, 개수=parse_count(숫자/수사 토큰)
가치헤드 없음 → val 고정. PORT=8766 QED=bench/qed_laya.db
"""
import os, re, sys

os.environ.setdefault("PORT", "8766")
os.environ.setdefault("USE_TF", "0")
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, f"{H}/../model")
import serve as S  # noqa: E402  (Miya ckpt도 로드됨: 판단엔 미사용)
import laya  # noqa: E402
from laya.shortlist import cached_embed_fn, embed_fn_from_agent, shortlist_choice  # noqa: E402

A = laya.load("convaiinnovations/laya-multilingual")
EMB = cached_embed_fn(embed_fn_from_agent(A))
HML = int(os.environ.get("HML", 1024))  # 보기 예산(기본 256) → 계획 보기 7개 잘림 방지
G, C, P = S.G, S.C, S.P
ITEMS = {i: n for i, n in C.entries()[1:]}  # id → 한글 이름(별칭 포함 문자열)
NONE = "없음"
CNT = re.compile(r"(\d+|한|두|세|네|하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열|스무|스물)(개|마리|칸|번)?(만|씩)?")  # 개수 토큰만


def ask(state, qid, instr, crit):
    """choice 1문항 → (key, {key: p})"""
    r = A.predict(state, {qid: {"type": "choice", "instructions": instr, "criteria": crit}}, head_max_len=HML)["answers"][qid]
    return r["choice"], r.get("probs") or r.get("distribution") or {r["choice"]: r.get("confidence", 1.0)}


def choose(utt, ctx, qid, opts):
    crit = {f"o{i}": o for i, o in enumerate(opts)}
    k, pr = ask({"요청": utt, "상황": ctx}, qid, f"{utt}: 상황에 가장 알맞은 보기", crit)
    ps = [float(pr.get(f"o{i}", 0)) for i in range(len(opts))]
    return int(k[1:]), ps, [[0.0, 0.0]] * len(opts)


def choose_many(utt, qid, opts, ctxs):
    return [choose(utt, c, qid, opts)[0] for c in ctxs]


def turn(x):
    ctx = x.get("ctx") or G.ctx_text(None, x["state"])
    utt, st = x["utt"], {"발화": x["utt"], "상황": ctx}
    act, ap = ask(st, "act", "마인크래프트 봇에게 한 플레이어 발화의 의도", {a: a for a in G.ACTS})
    ty, tp = ask(st, "type", "요청한 작업 종류", {k: G.TYPES[k] for k in G.TYPE_KEYS})
    q, _ = ask(st, "query", "질문이라면 무엇을 묻나", {k: G.QUERIES[k] for k in G.Q_KEYS})
    h, _ = ask(st, "hint", "지적·조언이라면 어떤 종류", {k: G.HINTS[k] for k in G.H_KEYS})
    y = {"act": act, "act_p": float(ap.get(act, 0)), "type": ty, "type_p": float(tp.get(ty, 0)), "query": q, "hint": h}
    top = shortlist_choice({"발화": utt}, ITEMS, EMB, k=20, instructions="발화가 가리키는 대상 아이템·몹")  # 공식 coarse-to-fine
    it, ip = ask({"발화": utt}, "tgt", "발화가 가리키는 대상 아이템·몹", {NONE: "대상 아이템 없음", **{i: ITEMS[i] for i in top}})
    it = None if it == NONE else it
    cnt = next((C.parse_count(w) for w in utt.split() if CNT.fullmatch(w)), None)
    sp = [{"text": utt, "label": "대상", "item": it, "ko": P.ko(it), "score": float(ip.get(it, 0))}] if it else []
    goals = [{"item": it, "ko": P.ko(it), "count": cnt}] if it else []
    if y["type"] in S.HELD and x.get("state"):
        goals = S.held(goals, x["state"].get("inv", {}))
    y["spans"], y["goals"], y["ctx"] = sp, goals, ctx
    return y


S.choose, S.choose_many, S.turn = choose, choose_many, turn
S.TIDY_OK = True
S.EP["/turn"] = turn

if __name__ == "__main__":
    port = int(os.environ["PORT"])
    print("serve-laya", port, flush=True)
    S.HTTPServer(("127.0.0.1", port), S.Hd).serve_forever()
