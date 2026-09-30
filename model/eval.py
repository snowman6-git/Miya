"""Miya 평가: 실발화(eval/real.jsonl) + 줄임말 holdout + dev(plan/prio) + 지연
CK=ckpt 경로. 출력: 지표 + 오답 목록(eval/last_errors.txt)
"""
import json, os, sys, time

import torch

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H); sys.path.insert(0, f"{H}/../data")
import catalog as C  # noqa: E402
from miya import LABELS, build, collate, load_tok, pack, read_ck  # noqa: E402
from train import TURN_Q, encode_row, dev_acc  # noqa: E402
import gen as G  # noqa: E402

CK = os.environ.get("CK", f"{H}/../ckpt/miya-0.2")
EQ = [{"stone", "cobblestone"}, {"grp:iron", "raw_iron", "iron_ingot", "iron_ore"}, {"grp:log", "oak_log"},
      {"grp:meat", "beef", "porkchop", "chicken", "mutton"}, {"grp:gold", "raw_gold", "gold_ingot"}, {"glass", "sand"}]
QK = list(TURN_Q)


def same(a, b):
    return a == b or any(a in e and b in e for e in EQ)


class Runner:
    def __init__(self, ck=CK, dev="cuda"):
        self.dev = dev
        self.tok = load_tok()
        self.m = build(dev, base_init=False)
        self.m.load(read_ck(ck, dev))
        self.m.eval()
        self.ents = C.entries()
        with torch.no_grad():
            self.bank = self.m.item_bank(*self.m.pool_names(self.tok, [n for _, n in self.ents[1:]], device=dev))

    @torch.no_grad()
    def turn(self, utt, ctx):
        p = pack(self.tok, utt, ctx, TURN_Q, LABELS)
        b = collate([p], self.dev)
        o = self.m(b)
        out = {}
        for g, q in enumerate(QK):
            lg = o["opt"][0].masked_fill(b["groups"][0] != g, -1e4)
            pr = lg.softmax(-1)
            k = int(lg.argmax())
            st = int((b["groups"][0] == g).nonzero()[0])
            out[q] = (k - st, float(pr[k]))
        sp = o["span"][0].sigmoid()  # S,L
        sc, lab = sp.max(-1)
        spans = []
        used = set()
        for c in sc.argsort(descending=True).tolist():
            if sc[c] < 0.5 or c >= len(p["cand"]):
                break
            i, j = p["cand"][c]
            if used & set(range(i, j + 1)):
                continue
            used |= set(range(i, j + 1))
            a, e = p["uoffs"][i][0], p["uoffs"][j][1]
            item = None
            if int(lab[c]) in (0, 2, 5):
                t = torch.tensor([c], device=self.dev)
                lg = self.m.link(o["sp_rep"][0, c][None], self.bank, *self.m.span_tok(o["h"], t * 0, b["sp_i"][0, t], b["sp_j"][0, t]))[0]
                item = self.ents[int(lg.argmax())][0]
            spans.append((utt[a:e], LABELS[int(lab[c])], item, float(sc[c]), c))
        spans.sort(key=lambda z: p["cand"][z[4]][0])
        # 짝: 개수 → 대상/도구 (idx into spans, None=없음)
        ti = [k for k, z in enumerate(spans) if z[1] in ("대상", "도구")]
        pairs = {}
        for k, z in enumerate(spans):
            if z[1] == "개수":
                lg = self.m.pair(o["sp_rep"][0, z[4]][None], o["sp_rep"][0, [spans[t][4] for t in ti]])[0]
                j = int(lg.argmax())
                pairs[k] = ti[j - 1] if j else None
        out["pairs"] = pairs
        return out, spans


def main():
    R = Runner()
    tok = R.tok
    errs = []
    # 실발화
    rows = [json.loads(l) for l in open(f"{H}/../eval/real.jsonl")]
    base = "체력 20/20 배고픔 20/20 | 낮 | 인벤: 비어있음 | 작업: 없음"
    n = {"act": [0, 0], "type": [0, 0], "query": [0, 0], "hint": [0, 0], "tgt": [0, 0], "cnt": [0, 0]}
    lat = []
    for x in rows:
        ctx = base + (f" | 봇질문: {x['botq']}" if x["botq"] else "")
        torch.cuda.synchronize(); t0 = time.perf_counter()
        utt = f"이전 나: {x['prev_user']} / 봇: {x['prev_bot'] or ''} ▶ {x['utt']}" if x.get("prev_user") and not os.environ.get("NOHIST") else x["utt"]  # 봇은 2분내 직전대화 전달
        out, spans = R.turn(utt, ctx)
        torch.cuda.synchronize(); lat.append(time.perf_counter() - t0)
        pred = {"act": G.ACTS[out["act"][0]], "type": G.TYPE_KEYS[out["type"][0]], "query": G.Q_KEYS[out["query"][0]], "hint": G.H_KEYS[out["hint"][0]]}
        bad = []
        for q in ("act", "type", "query", "hint"):
            if q in x["y"]:  # 하위문항은 정답 act 조건부 정확도
                n[q][1] += 1
                if pred[q] == x["y"][q]:
                    n[q][0] += 1
                else:
                    bad.append(f"{q}:{pred[q]}≠{x['y'][q]}")
        if x["tgt"]:
            n["tgt"][1] += 1
            t = [s for s in spans if s[1] == "대상" and s[2]] or [s for s in spans if s[1] == "장소" and s[2]]  # 대상 우선
            if t and same(t[0][2], x["tgt"]):
                n["tgt"][0] += 1
            else:
                bad.append(f"tgt:{t[0][2] if t else None}≠{x['tgt']}")
        if x["cnt"]:
            n["cnt"][1] += 1
            c = [C.parse_count(s[0]) for s in spans if s[1] == "개수"]
            if c and c[0] == x["cnt"]:
                n["cnt"][0] += 1
            else:
                bad.append(f"cnt:{c}≠{x['cnt']}")
        if bad:
            errs.append(f"{x['utt']} | {' '.join(bad)} | {[(s[0], s[1], s[2]) for s in spans]} act_p={out['act'][1]:.2f}")
    res = {k: f"{a}/{b}={a / max(b, 1):.3f}" for k, (a, b) in n.items()}
    print("real", res)
    lat.sort()
    print(f"latency turn p50 {lat[len(lat) // 2] * 1000:.1f}ms p95 {lat[int(len(lat) * .95)] * 1000:.1f}ms")
    # holdout 줄임말 (학습에 없던 조합)
    ho = C.holdout_forms()
    k = 0
    for f, iid in ho:
        _, spans = R.turn(f"{f} 만들어", base)
        t = [s for s in spans if s[1] == "대상"]
        k += int(bool(t) and t[0][2] == iid)
        if not (t and t[0][2] == iid):
            errs.append(f"[holdout] {f} → {t[:1]} (정답 {iid})")
    print(f"holdout slang {k}/{len(ho)}")
    # dev plan/prio
    dv = [encode_row(tok, json.loads(l)) for l in open(f"{H}/../data/gen/dev.jsonl")]
    print("dev", dev_acc(R.m, tok, dv, R.dev))
    with open(f"{H}/../eval/last_errors.txt", "w") as f:
        f.write("\n".join(errs))
    print("errors", len(errs))


if __name__ == "__main__":
    main()
