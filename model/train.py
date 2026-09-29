"""Miya-0.2 학습. data/gen/{train,dev}.jsonl → ckpt/miya-0.2
손실: 문항 group CE + plan 가치(시간 MSE, 성공 BCE) + 구간 BCE(GLiNER) + 링크 CE(in-batch bank, grad 흐름)
"""
import json, math, os, random, sys, time

import torch
import torch.nn.functional as F

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H); sys.path.insert(0, f"{H}/../data")
import catalog as C  # noqa: E402
import gen as G  # noqa: E402
from miya import LABELS, build, collate, keep_vocab, load_tok, pack  # noqa: E402

TURN_Q = {"act": G.ACTS, "type": [G.TYPES[k] for k in G.TYPE_KEYS], "query": [G.QUERIES[k] for k in G.Q_KEYS], "hint": [G.HINTS[k] for k in G.H_KEYS]}
TIDX = {"act": {a: i for i, a in enumerate(G.ACTS)}, "type": {k: i for i, k in enumerate(G.TYPE_KEYS)},
        "query": {k: i for i, k in enumerate(G.Q_KEYS)}, "hint": {k: i for i, k in enumerate(G.H_KEYS)}}
LINKABLE = {0, 2, 5}  # 대상·도구·장소
OUT = os.environ.get("OUT", f"{H}/../ckpt/miya-0.2")


def encode_row(tok, x):
    """행 → pack 결과 + 타깃"""
    if x["kind"] == "turn":
        p = pack(tok, x["utt"], x["ctx"], TURN_Q, LABELS, [(a, b, l) for a, b, l, _ in x["spans"]])
        tg = {}
        for gi, q in enumerate(TURN_Q):
            if q in x["y"]:
                tg[gi] = TIDX[q][x["y"][q]]
        # 링크 타깃: 구간 → bank idx
        idx = C.index()
        links = []
        for a, b, l, it in x["spans"]:
            if l in LINKABLE and isinstance(it, str) and it in idx:
                links.append((a, b, idx[it]))
        p["links"] = links
        # 짝 타깃: 대상/도구 구간 목록 + 개수 구간별 짝 idx(대상 목록 기준)
        ti = [k for k, s in enumerate(x["spans"]) if s[2] in (0, 2)]
        pm = dict(x.get("pairs", []))
        p["tgt_sp"] = [tuple(x["spans"][k][:2]) for k in ti]
        p["cnt_sp"] = [(tuple(s[:2]), ti.index(pm[k]) if k in pm and pm[k] in ti else None) for k, s in enumerate(x["spans"]) if s[2] == 1]
    elif x["kind"] == "plan":
        p = pack(tok, "방법 선택", x["ctx"], {"방법": x["opts"]}, [], None)
        tg = {0: x["best"]}
        p["val"] = x["val"]
        p["links"] = []
    elif x["kind"] == "tidy":
        p = pack(tok, "아이템 정리", x["ctx"], {"정리": G.TIDY}, [], None)
        tg = {0: x["y"]}
        p["links"] = []
    else:
        p = pack(tok, "우선순위 판단", x["ctx"], {"우선": G.PRIO}, [], None)
        tg = {0: x["y"]}
        p["links"] = []
    # 그룹별 마커 시작
    st, k = [], 0
    for g in range(len(p["qids"])):
        st.append(k)
        k += sum(1 for gg in p["groups"] if gg == g)
    p["tg"] = [(g, st[g] + t) for g, t in tg.items()]
    p["kind"] = x["kind"]
    return p


_TOK = None


def _enc_chunk(lines):
    global _TOK
    if _TOK is None:
        _TOK = load_tok()
    from miya import pretok
    rows = [json.loads(l) for l in lines]
    txt = []
    for x in rows:
        txt.append(x["ctx"])
        if x["kind"] == "turn":
            txt.append(x["utt"])
        elif x["kind"] == "plan":
            txt += [" " + o for o in x["opts"]]
    pretok(_TOK, txt)
    return [encode_row(_TOK, x) for x in rows]


def load_enc(path, nproc=os.cpu_count() or 4):
    """jsonl → encode_row 결과. 멀티프로세스 + 캐시(원본 mtime 같으면 재사용)"""
    import pickle
    from multiprocessing import get_context
    cp = path + ".enc.pkl"
    if os.path.exists(cp) and os.path.getmtime(cp) > os.path.getmtime(path):
        return pickle.load(open(cp, "rb"))
    L = open(path).readlines()
    ch = [L[k:k + 8000] for k in range(0, len(L), 8000)]
    with get_context("spawn").Pool(nproc) as pool:
        out = [r for part in pool.map(_enc_chunk, ch) for r in part]
    pickle.dump(out, open(cp, "wb"), protocol=5)
    return out


def span_link_pos(p, a, b):
    """문자구간 → cand 인덱스"""
    ok = [bool(p["utt"][s:e].strip()) for s, e in p["uoffs"]]
    ti = [k for k, (s, e) in enumerate(p["uoffs"]) if ok[k] and max(s, a) < min(e, b)]
    if not ti:
        return None
    try:
        return p["cand"].index((ti[0], ti[-1]))
    except ValueError:
        return None


def loss_fn(model, tok, ps, device, ents, nneg=192):
    b = collate(ps, device)
    o = model(b)
    B = len(ps)
    # 문항 CE
    lo = []
    for i, p in enumerate(ps):
        for g, t in p["tg"]:
            lg = o["opt"][i].masked_fill(b["groups"][i] != g, -1e4)
            lo.append(F.cross_entropy(lg[None], torch.tensor([t], device=device)))
    l_opt = torch.stack(lo).mean()
    # 가치
    lv = []
    for i, p in enumerate(ps):
        if "val" in p:
            v = torch.tensor(p["val"], device=device, dtype=torch.float)
            pr = o["val"][i, :len(p["val"])]
            lv.append(F.smooth_l1_loss(pr[:, 0], v[:, 0]) + F.binary_cross_entropy_with_logits(pr[:, 1], v[:, 1]))
    l_val = torch.stack(lv).mean() if lv else o["val"].sum() * 0
    # 구간 BCE (turn 행만)
    tm = torch.tensor([p["kind"] == "turn" for p in ps], device=device)
    L = o["span"].size(-1)
    l_span = o["span"].sum() * 0
    if L and tm.any():
        y = torch.zeros_like(o["span"])
        pos = b["sp_y"] >= 0
        if pos.any():
            y[pos] = F.one_hot(b["sp_y"][pos], L).float()
        m = (b["sp_m"] & tm[:, None]).float()[..., None].expand_as(y)
        w = torch.where(y > 0, 5.0, 1.0) * m
        l_span = (F.binary_cross_entropy_with_logits(o["span"], y, reduction="none") * w).sum() / m.sum().clamp(min=1)
    # 링크: gold + 무작위 음성으로 소형 bank, 이름 인코딩에 grad
    q, qb, qc, gold = [], [], [], []
    for i, p in enumerate(ps):
        for a, bb, gi in p["links"]:
            c = span_link_pos(p, a, bb)
            if c is not None:
                q.append(o["sp_rep"][i, c]); qb.append(i); qc.append(c); gold.append(gi)
    l_link = o["span"].sum() * 0
    if q:
        ids = sorted(set(g for g in gold if g > 0) | set(random.sample(range(1, len(ents)), nneg)))
        bank = model.item_bank(*model.name_enc(tok, [ents[k][1] for k in ids], device))  # [0]=NULL
        qb, qc = torch.tensor(qb, device=device), torch.tensor(qc, device=device)
        qt, qm = model.span_tok(o["h"], qb, b["sp_i"][qb, qc], b["sp_j"][qb, qc])
        pos_of = {k: j + 1 for j, k in enumerate(ids)}
        tgt = torch.tensor([0 if g == 0 else pos_of[g] for g in gold], device=device)
        l_link = F.cross_entropy(model.link(torch.stack(q), bank, qt, qm), tgt)
    # 짝(GLiREL): 개수 구간 → 같은 행 대상/도구 구간 중 하나 or 없음
    l_pair, lp = o["span"].sum() * 0, []
    for i, p in enumerate(ps):
        if not p.get("cnt_sp"):
            continue
        tc = [span_link_pos(p, a, bb) for a, bb in p["tgt_sp"]]
        keep = [k for k, c in enumerate(tc) if c is not None]
        for (a, bb), gt in p["cnt_sp"]:
            c = span_link_pos(p, a, bb)
            if c is None:
                continue
            lg = model.pair(o["sp_rep"][i, c][None], o["sp_rep"][i, [tc[k] for k in keep]] if keep else o["sp_rep"][i, :0])
            y = keep.index(gt) + 1 if gt is not None and gt in keep else 0
            lp.append(F.cross_entropy(lg, torch.tensor([y], device=device)))
    if lp:
        l_pair = torch.stack(lp).mean()
    return l_opt + 0.5 * l_val + l_span + 0.5 * l_link + 0.5 * l_pair, {"opt": l_opt.item(), "val": l_val.item(), "span": l_span.item(), "link": l_link.item(), "pair": l_pair.item()}


@torch.no_grad()
def dev_acc(model, tok, rows, device, bs=64):
    model.eval()
    ok = {"turn": [0, 0], "plan": [0, 0], "prio": [0, 0], "tidy": [0, 0]}
    for k in range(0, len(rows), bs):
        ps = rows[k:k + bs]
        b = collate(ps, device)
        o = model(b)
        for i, p in enumerate(ps):
            for g, t in p["tg"]:
                lg = o["opt"][i].masked_fill(b["groups"][i] != g, -1e4)
                ok[p["kind"]][0] += int(lg.argmax().item() == t); ok[p["kind"]][1] += 1
    model.train()
    return {k: round(a / max(n, 1), 4) for k, (a, n) in ok.items()}


def main():
    torch.manual_seed(0); random.seed(0)
    dev = "cuda"
    tok = load_tok()
    D = f"{H}/../data/gen"
    t0 = time.time()
    tr, dv = load_enc(f"{D}/train.jsonl"), load_enc(f"{D}/dev.jsonl")
    print(f"encoded {len(tr)} / {len(dv)} in {time.time() - t0:.0f}s", flush=True)
    model = build(dev)
    if os.environ.get("PRUNE", "1") == "1":  # 어휘 가지치기: 데이터·실측·카탈로그 사용 토큰 + 한글/바이트/짧은 ASCII
        ex = [(lambda r: r.get("utt") or r.get("text") or "")(json.loads(l)) for f in (f"{H}/../eval/real.jsonl", f"{H}/../data/chat_raw.jsonl") for l in open(f)]
        keep = keep_vocab(tok, [p["ids"] for p in tr + dv], ex + [n for _, n in C.entries()[1:]])
        model.prune(keep, tok.unk_token_id)
        print(f"vocab {len(tok)} → {len(keep)}, params {sum(p.numel() for p in model.parameters()) / 1e6:.0f}M", flush=True)
    model.train()
    ents = C.entries()
    enc_p = [p for n, p in model.named_parameters() if n.startswith("encoder.")]
    head_p = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    EP = int(os.environ.get("EP", 2)); BS = int(os.environ.get("BS", 32))
    opt = torch.optim.AdamW([{"params": enc_p, "lr": float(os.environ.get("LR", 3e-5))}, {"params": head_p, "lr": 3e-4}], weight_decay=0.01)
    steps = EP * (len(tr) // BS)
    warm = max(100, steps // 30)
    sch = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, s / warm) * max(0.02, 0.5 * (1 + math.cos(math.pi * min(1, s / steps)))))
    step = 0
    # 길이 버킷: 비슷한 길이끼리 배치 (패딩 절감)
    for ep in range(EP):
        idx = sorted(range(len(tr)), key=lambda i: len(tr[i]["ids"]) + random.random() * 40)
        bats = [idx[k:k + BS] for k in range(0, len(idx), BS)]
        random.shuffle(bats)
        acc = {}
        t0 = time.time()
        for bi in bats:
            loss, parts = loss_fn(model, tok, [tr[i] for i in bi], dev, ents)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sch.step(); step += 1
            for k, v in parts.items():
                acc[k] = acc.get(k, 0) * 0.98 + v * 0.02
            if step % 200 == 0:
                print(f"ep{ep} {step}/{steps} " + " ".join(f"{k}={v:.3f}" for k, v in acc.items()) + f" {200 * BS / (time.time() - t0):.0f}ex/s", flush=True)
                t0 = time.time()
            if step % 2000 == 0:
                print("dev", dev_acc(model, tok, dv[:3000], dev), flush=True)
        print("dev ep", ep, dev_acc(model, tok, dv, dev), flush=True)
        os.makedirs(OUT, exist_ok=True)
        torch.save({k: v for k, v in model.state_dict().items()}, f"{OUT}/model.pt")
    json.dump({"labels": LABELS, "turn_q": TURN_Q, "type_keys": G.TYPE_KEYS, "q_keys": G.Q_KEYS, "h_keys": G.H_KEYS, "prio": G.PRIO, "tidy": G.TIDY},
              open(f"{OUT}/schema.json", "w"), ensure_ascii=False, indent=1)
    print("saved", OUT)


if __name__ == "__main__":
    main()
