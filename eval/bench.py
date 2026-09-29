"""Miya vs LAYA 오프라인 벤치: 같은 셋을 두 서빙(HTTP)에 → 정확도·지연 비교표(md)
사용: python eval/bench.py [miya_port=8767] [laya_port=8766] > bench/offline.md
실발화 = eval/real.jsonl (prod HIST=0 → 발화 단독), dev = plan/prio/tidy (/choose)
"""
import json, os, sys, time, urllib.request

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, f"{H}/../data")
sys.path.insert(0, f"{H}/../model")
import gen as G  # noqa: E402
from eval import same  # noqa: E402

BASE = "체력 20/20 배고픔 20/20 | 낮 | 인벤: 비어있음 | 작업: 없음"
DEV = {"plan": ("방법 선택", "방법", None), "prio": ("우선순위 판단", "우선", G.PRIO), "tidy": ("아이템 정리", "정리", G.TIDY)}


def post(port, path, x):
    t = time.perf_counter()
    r = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(x).encode()), timeout=120).read())
    return r, time.perf_counter() - t


def real(port):
    n, lat = {k: [0, 0] for k in ("act", "type", "query", "hint", "tgt", "cnt")}, []
    for l in open(f"{H}/real.jsonl"):
        x = json.loads(l)
        r, dt = post(port, "/turn", {"utt": x["utt"], "ctx": BASE + (f" | 봇질문: {x['botq']}" if x["botq"] else "")})
        lat.append(dt)
        for q in ("act", "type", "query", "hint"):
            if q in x["y"]:  # 하위문항 = 정답 act 조건부
                n[q][1] += 1; n[q][0] += r[q] == x["y"][q]
        g = (r.get("goals") or [{}])[0]
        if x["tgt"]:
            n["tgt"][1] += 1; n["tgt"][0] += bool(g.get("item")) and same(g["item"], x["tgt"])
        if x["cnt"]:
            n["cnt"][1] += 1; n["cnt"][0] += g.get("count") == x["cnt"]
    return n, lat


def dev(port):
    n, lat = {k: [0, 0] for k in DEV}, []
    for l in open(f"{H}/../data/gen/dev.jsonl"):
        x = json.loads(l)
        if x["kind"] not in DEV:
            continue
        utt, qid, lab = DEV[x["kind"]]
        opts, y = (x["opts"], x["best"]) if lab is None else (lab, x["y"])
        r, dt = post(port, "/choose", {"utt": utt, "ctx": x["ctx"], "qid": qid, "opts": opts})
        lat.append(dt); n[x["kind"]][1] += 1; n[x["kind"]][0] += r["k"] == y
    return n, lat


def pct(a, b):
    return f"{a}/{b} ({a / max(b, 1) * 100:.1f}%)"


def ms(l, q):
    l = sorted(l); return f"{l[min(len(l) - 1, int(len(l) * q))] * 1000:.1f}"


if __name__ == "__main__":
    ports = {"Miya-0.2": int(sys.argv[1]) if len(sys.argv) > 1 else 8767, "LAYA base": int(sys.argv[2]) if len(sys.argv) > 2 else 8766}
    R = {}
    for name, p in ports.items():
        (rn, rl), (dn, dl) = real(p), dev(p)
        R[name] = (rn, rl, dn, dl)
        print(name, {k: pct(*v) for k, v in {**rn, **dn}.items()}, file=sys.stderr)
    cols = list(R)
    print("| 항목 | " + " | ".join(cols) + " |\n|---|" + "---|" * len(cols))
    for k in ("act", "type", "query", "hint", "tgt", "cnt"):
        print(f"| 실발화 {k} | " + " | ".join(pct(*R[c][0][k]) for c in cols) + " |")
    for k in DEV:
        print(f"| dev {k} | " + " | ".join(pct(*R[c][2][k]) for c in cols) + " |")
    print("| /turn p50·p95 ms | " + " | ".join(f"{ms(R[c][1], .5)} · {ms(R[c][1], .95)}" for c in cols) + " |")
    print("| /choose p50·p95 ms | " + " | ".join(f"{ms(R[c][3], .5)} · {ms(R[c][3], .95)}" for c in cols) + " |")
