"""Miya-0.2: mmBERT(베이스 laya-multilingual 인코더 가중치만) + GLiNER2식 스키마 입력 멀티태스크 헤드. 헤드 전부 새로 초기화

한 줄: [CLS] 발화 [SEP] 상태·QED [SEP] ([MASK]라벨)×n [SEP] (문항: [MASK]보기...[SEP])×m
- seg: 0 발화, 1 상태, 2 라벨, 3 문항 → seg_emb 더함
- 보기: [MASK] 위치 → scorer, 문항(group)별 softmax. 되묻기도 act 보기 하나로 학습
- 구간(GLiNER): 발화 토큰 i..j(폭≤MAXW) rep vs 라벨 [MASK] rep 내적 → sigmoid
- 아이템 링크: ITEM 구간 rep → 아이템 이름 임베딩 bank 내적(bi-encoder). bank[0]=NULL(모름 → 되묻기)
- 아이템 링크 2: ColBERT식 late interaction. 구간 토큰별 벡터 vs 이름 토큰별 벡터 MaxSim 평균 → bi 점수에 더함 (부분일치 줄임말 철뚝)
- 숫자: 숫자 첫 토큰 임베딩에 값 특징 MLP 더함
- 어휘 가지치기: remap 버퍼(원본 id → 축소 id, 없는 토큰 → unk). 토크나이저 원본 그대로, 모델 안에서 변환
"""
import glob, json, math, os, re
from typing import Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

BASE = "convaiinnovations/laya-multilingual"  # 인코더 초기값·토크나이저 (Apache-2.0)
SNAP = os.environ.get("SNAP") or next(iter(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../hf_cache/hub/models--convaiinnovations--laya-multilingual/snapshots/*"))), None)
if not SNAP:  # 로컬 캐시 없음 → HF에서 config·토크나이저만 (가중치는 학습시 build에서)
    from huggingface_hub import snapshot_download
    SNAP = snapshot_download(BASE, allow_patterns=["encoder/*", "tokenizer/*"])
LABELS = ["대상", "개수", "도구", "사람", "좌표", "장소", "거리"]  # 구간 라벨. 입력에 이름으로 들어가므로 추가 쉬움
OPT_TOK = 96  # 보기당 최대 토큰 (plan 방법 텍스트 김)
MAXW = 8  # 구간 최대 토큰폭
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
SEG = {"utt": 0, "ctx": 1, "lab": 2, "q": 3}


def num_feat(v: float) -> List[float]:
    a = abs(v)
    return [1.0 if v < 0 else 0.0, math.log1p(a) / 8.0, min(a, 1000.0) / 1000.0, 1.0 if float(v).is_integer() else 0.0, min(a, 64.0) / 64.0]


def read_ck(ck, dev="cpu"):
    """ckpt 가중치: model.safetensors 우선, 구 model.pt 폴백"""
    if os.path.exists(f"{ck}/model.safetensors"):
        from safetensors.torch import load_file
        return load_file(f"{ck}/model.safetensors", device=str(dev))
    return torch.load(f"{ck}/model.pt", map_location=dev)


def load_tok():
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(f"{SNAP}/tokenizer")


_PC: Dict = {}  # 문자열→(ids,offs,nums) 캐시. 보기·라벨 반복 + 배치 선토큰화 결과


def pretok(tok, texts: List[str], bs: int = 8192):
    """배치 토큰화(Rust 병렬)로 캐시 채움. 학습 전처리 가속"""
    u = [t for t in dict.fromkeys(texts) if t not in _PC]
    for k in range(0, len(u), bs):
        e = tok(u[k:k + bs], add_special_tokens=False, return_offsets_mapping=True)
        for t, ids, offs in zip(u[k:k + bs], e["input_ids"], e["offset_mapping"]):
            _PC[t] = _nums(t, ids, [tuple(o) for o in offs])


def _piece(tok, text: str):
    r = _PC.get(text)
    if r is None:
        e = tok(text, add_special_tokens=False, return_offsets_mapping=True)
        r = _PC[text] = _nums(text, e["input_ids"], [tuple(o) for o in e["offset_mapping"]])
    return r


def _nums(text, ids, offs):
    nums = []
    for m in NUM_RE.finditer(text):
        for i, (s, t) in enumerate(offs):
            if t > m.start() and s < m.end():
                nums.append((i, float(m.group())))
                break
    return ids, offs, nums


def pack(tok, utt: str, ctx: str, questions: Dict[str, List[str]], labels: List[str] = LABELS,
         spans: Optional[List] = None, max_len: int = 2048) -> Dict:
    """questions: {qid: [보기텍스트...]}. spans: [(char_s, char_e, label_idx)] 발화 기준"""
    M = tok.mask_token_id
    ids, seg, nums = [tok.cls_token_id], [0], []
    uids, uoffs, un = _piece(tok, utt)
    u0 = len(ids)
    ids += uids; seg += [0] * len(uids); nums += [(u0 + i, v) for i, v in un]
    u1 = len(ids)
    ids.append(tok.sep_token_id); seg.append(0)
    cids, _, cn = _piece(tok, ctx)
    c0 = len(ids)
    ids += cids; seg += [1] * len(cids); nums += [(c0 + i, v) for i, v in cn]
    ids.append(tok.sep_token_id); seg.append(1)
    lab_pos = []
    for l in labels:
        lab_pos.append(len(ids))
        lid = _piece(tok, " " + l)[0]
        ids += [M] + lid; seg += [2] * (1 + len(lid))
    ids.append(tok.sep_token_id); seg.append(2)
    markers, groups, qids = [], [], []
    for g, (qid, opts) in enumerate(questions.items()):
        qi = _piece(tok, f" {qid}:")[0]
        ids += qi; seg += [3] * len(qi)
        for o in opts:
            oi, _, on = _piece(tok, " " + o)
            oi = oi[:OPT_TOK]
            markers.append(len(ids)); groups.append(g)
            ids.append(M); seg.append(3)
            nums += [(len(ids) + i, v) for i, v in on if i < OPT_TOK]
            ids += oi; seg += [3] * len(oi)
        ids.append(tok.sep_token_id); seg.append(3)
        qids.append(qid)
    if len(ids) > max_len:
        raise ValueError(f"len {len(ids)} > {max_len}")
    # 구간 후보: 발화 토큰 i..j. 공백만 토큰은 시작/끝 불가
    ok = [bool(utt[s:e].strip()) for s, e in uoffs]
    cand = [(i, j) for i in range(len(uids)) if ok[i] for j in range(i, min(i + MAXW, len(uids))) if ok[j]]
    gold = {}
    for s, e, t in spans or []:
        ti = [k for k, (a, b) in enumerate(uoffs) if ok[k] and max(a, s) < min(b, e)]
        if ti:
            gold[(ti[0], ti[-1])] = t
    return {"ids": ids, "seg": seg, "nums": nums, "u0": u0, "uoffs": uoffs, "lab_pos": lab_pos,
            "markers": markers, "groups": groups, "qids": qids, "cand": cand, "gold": gold, "utt": utt}


class Miya(nn.Module):
    def __init__(self, encoder: nn.Module, n_lab: int = len(LABELS)):
        super().__init__()
        self.encoder = encoder
        d = encoder.config.hidden_size
        self.d = d
        self.seg_emb = nn.Embedding(4, d)
        nn.init.zeros_(self.seg_emb.weight)
        self.num_mlp = nn.Sequential(nn.Linear(5, d), nn.GELU(), nn.Linear(d, d))
        nn.init.zeros_(self.num_mlp[2].weight); nn.init.zeros_(self.num_mlp[2].bias)
        self.scorer = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, d), nn.GELU(), nn.Linear(d, 1))
        self.value = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, d // 2), nn.GELU(), nn.Linear(d // 2, 2))  # 보기별 [log1p(초), 성공 logit] (QED 가치)
        self.w_emb = nn.Embedding(MAXW, d)
        self.span_mlp = nn.Sequential(nn.Linear(3 * d, d), nn.GELU(), nn.LayerNorm(d), nn.Linear(d, d))
        self.lab_mlp = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, d), nn.GELU(), nn.Linear(d, d))
        self.link_s = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, 256))
        self.link_i = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, 256))
        self.null_item = nn.Parameter(torch.zeros(1, d))
        self.link_scale = nn.Parameter(torch.tensor(math.log(20.0)))
        self.pair_c = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, 256))  # GLiREL 짝: 개수 구간 → 대상 구간
        self.pair_t = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, 256))
        self.pair_none = nn.Parameter(torch.zeros(256))
        self.col_q = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, 128))  # ColBERT 링크
        self.col_i = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, 128))
        self.col_scale = nn.Parameter(torch.tensor(math.log(10.0)))
        self.col_null = nn.Parameter(torch.tensor(0.5))
        self.register_buffer("remap", torch.arange(encoder.config.vocab_size))

    def prune(self, keep: List[int], unk: int):
        """어휘 가지치기: keep 토큰만 임베딩 유지"""
        keep = sorted(set(keep) | {unk})
        old = self.encoder.get_input_embeddings()
        new = nn.Embedding(len(keep), old.weight.size(1), dtype=old.weight.dtype, device=old.weight.device)
        kt = torch.tensor(keep, device=old.weight.device)
        if old.weight.size(0) == self.remap.numel():
            new.weight.data.copy_(old.weight.data[kt])
        self.encoder.set_input_embeddings(new)
        self.encoder.config.vocab_size = len(keep)
        rm = torch.full_like(self.remap, keep.index(unk))
        rm[kt] = torch.arange(len(keep), device=rm.device)
        self.remap = rm

    def load(self, sd):
        """가지치기된 ckpt 로드 (임베딩 크기 맞춤)"""
        k = [x for x in sd if x.endswith("embeddings.tok_embeddings.weight") or x.endswith("embed_tokens.weight")]
        if k and sd[k[0]].size(0) != self.encoder.get_input_embeddings().weight.size(0):
            self.prune(list(range(sd[k[0]].size(0))), 0)
        miss, unexp = self.load_state_dict(sd, strict=False)
        assert not unexp and all(k.startswith(("col_", "remap")) for k in miss), (miss[:5], unexp[:5])  # 0.1a ckpt 호환(ColBERT 없음)

    def encode(self, ids, att, seg, num_pos, num_f, num_m):
        emb = self.encoder.get_input_embeddings()(self.remap[ids])
        add = self.num_mlp(num_f) * num_m[..., None]
        emb = emb.scatter_add(1, num_pos[..., None].expand(-1, -1, emb.size(-1)), add.to(emb.dtype))
        emb = emb + self.seg_emb(seg).to(emb.dtype)
        return self.encoder(inputs_embeds=emb, attention_mask=att).last_hidden_state

    def forward(self, b):
        h = self.encode(b["ids"], b["att"], b["seg"], b["num_pos"], b["num_f"], b["num_m"]).float()  # 헤드 fp32
        D = h.size(-1)
        g = lambda pos: torch.gather(h, 1, pos.clamp(min=0)[..., None].expand(-1, -1, D))  # noqa: E731
        mh = g(b["markers"])
        opt = self.scorer(mh).squeeze(-1).float().masked_fill(~b["marker_m"], -1e4)
        val = self.value(mh).float()
        lab = self.lab_mlp(g(b["lab_pos"]))  # B,L,D
        s = torch.cat([g(b["sp_i"]), g(b["sp_j"]), self.w_emb((b["sp_j"] - b["sp_i"]).clamp(0, MAXW - 1))], -1)
        sp = self.span_mlp(s)  # B,S,D
        span_logit = torch.einsum("bsd,bld->bsl", sp, lab).float() / math.sqrt(D)
        return {"opt": opt, "val": val, "span": span_logit, "sp_rep": sp, "h": h}

    def item_bank(self, name_h, name_t=None, name_m=None):
        """name_h: [N,D] 이름 풀링, name_t: [N,T,D] 이름 토큰, name_m: [N,T]. NULL은 bi쪽 [0]"""
        v = F.normalize(self.link_i(torch.cat([self.null_item.to(name_h.dtype), name_h], 0)).float(), dim=-1)
        if name_t is None:
            return {"v": v}
        return {"v": v, "t": F.normalize(self.col_i(name_t.float()), dim=-1), "m": name_m.bool()}

    def span_tok(self, h, bi, pi, pj):
        """구간 토큰들 [Q,MAXW,D] + mask. bi 배치idx, pi/pj 절대 시작/끝"""
        pos = pi[:, None] + torch.arange(MAXW, device=h.device)
        m = pos <= pj[:, None]
        return h[bi[:, None], pos.clamp(max=h.size(1) - 1)], m

    def pair(self, c_rep, t_rep):
        """c_rep N,d / t_rep T,d → N,T+1 logits ([0]=짝 없음)"""
        c = self.pair_c(c_rep).float()
        t = torch.cat([self.pair_none[None], self.pair_t(t_rep).float()])
        return c @ t.T / 16

    def link(self, sp_rep, bank, qt=None, qm=None):
        """→ [Q, N+1] ([0]=NULL). qt/qm 있으면 ColBERT MaxSim 더함"""
        q = F.normalize(self.link_s(sp_rep).float(), dim=-1)
        lg = q @ bank["v"].T * self.link_scale.exp()
        if qt is None or "t" not in bank:
            return lg
        qv = F.normalize(self.col_q(qt.float()), dim=-1)  # Q,A,c
        sim = torch.einsum("qac,nbc->qnab", qv, bank["t"]).masked_fill(~bank["m"][None, :, None, :], -2)
        col = (sim.max(-1).values * qm[:, None, :]).sum(-1) / qm.sum(-1, keepdim=True).clamp(min=1)  # Q,N
        col = torch.cat([self.col_null.expand(col.size(0), 1), col], 1)
        return lg + col * self.col_scale.exp()

    @torch.no_grad()
    def pool_names(self, tok, names: List[str], bs: int = 256, device="cuda"):
        """아이템 이름 → (mean pool [N,D], 토큰 [N,32,D], mask [N,32])"""
        out, ts, ms = [], [], []
        for k in range(0, len(names), bs):
            p, t, m = self.name_enc(tok, names[k:k + bs], device, pad=True)
            out.append(p); ts.append(t); ms.append(m)
        return torch.cat(out), torch.cat(ts), torch.cat(ms)

    def name_enc(self, tok, names, device, pad=False):
        e = tok(names, padding="max_length" if pad else True, truncation=True, max_length=32, return_tensors="pt").to(device)
        hh = self.encoder(input_ids=self.remap[e["input_ids"]], attention_mask=e["attention_mask"]).last_hidden_state.float()
        m = e["attention_mask"]
        return (hh * m[..., None]).sum(1) / m.sum(1, keepdim=True), hh, m


def build(device="cuda", base_init: bool = True, attn=None) -> Miya:
    import importlib.util
    from transformers import AutoConfig, AutoModel
    attn = attn or ("flash_attention_2" if importlib.util.find_spec("flash_attn") else "sdpa")
    ec = AutoConfig.from_pretrained(f"{SNAP}/encoder")  # tf5는 rope_parameters 직접 읽음
    enc = AutoModel.from_config(ec, attn_implementation=attn, dtype=torch.bfloat16)
    if base_init:
        from safetensors.torch import load_file
        f = f"{SNAP}/model.safetensors"
        if not os.path.exists(f):
            from huggingface_hub import hf_hub_download
            f = hf_hub_download(BASE, "model.safetensors")
        sd = load_file(f)
        esd = {k[8:]: v for k, v in sd.items() if k.startswith("encoder.")}
        miss, unexp = enc.load_state_dict(esd, strict=False)
        assert not unexp and all("rotary" in m or "inv_freq" in m for m in miss), (miss[:5], unexp[:5])
    m = Miya(enc).to(device)
    for n, p in m.named_parameters():
        if not n.startswith("encoder."):
            p.data = p.data.float()
    return m


def collate(items: List[Dict], device="cuda") -> Dict:
    B = len(items)
    L = max(len(x["ids"]) for x in items)
    Mk = max(1, max(len(x["markers"]) for x in items))
    K = max(1, max(len(x["nums"]) for x in items))
    S = max(1, max(len(x["cand"]) for x in items))
    NL = max(len(x["lab_pos"]) for x in items)
    z = lambda *s, dt=torch.long: torch.zeros(*s, dtype=dt)  # noqa: E731
    t = {"ids": z(B, L), "att": z(B, L), "seg": z(B, L), "num_pos": z(B, K), "num_f": z(B, K, 5, dt=torch.float),
         "num_m": z(B, K, dt=torch.float), "markers": z(B, Mk), "marker_m": z(B, Mk, dt=torch.bool),
         "groups": torch.full((B, Mk), -1), "lab_pos": z(B, NL), "sp_i": z(B, S), "sp_j": z(B, S),
         "sp_m": z(B, S, dt=torch.bool), "sp_y": torch.full((B, S), -1)}
    for b, x in enumerate(items):
        n = len(x["ids"])
        t["ids"][b, :n] = torch.tensor(x["ids"]); t["att"][b, :n] = 1; t["seg"][b, :n] = torch.tensor(x["seg"])
        for k, (p, v) in enumerate(x["nums"]):
            t["num_pos"][b, k] = p; t["num_f"][b, k] = torch.tensor(num_feat(v)); t["num_m"][b, k] = 1
        mk = len(x["markers"])
        t["markers"][b, :mk] = torch.tensor(x["markers"]); t["marker_m"][b, :mk] = True
        t["groups"][b, :mk] = torch.tensor(x["groups"])
        t["lab_pos"][b, :len(x["lab_pos"])] = torch.tensor(x["lab_pos"])
        for k, (i, j) in enumerate(x["cand"]):
            t["sp_i"][b, k] = x["u0"] + i; t["sp_j"][b, k] = x["u0"] + j; t["sp_m"][b, k] = True
            t["sp_y"][b, k] = x["gold"].get((i, j), -1)
    return {k: v.to(device, non_blocking=True) for k, v in t.items()}


def group_logp(opt, groups, g: int):
    return torch.log_softmax(opt.masked_fill(groups != g, -1e4), -1)


def keep_vocab(tok, id_lists, extra_texts=()):
    """가지치기 유지 토큰: 데이터 사용 토큰 + 한글 포함 전부 + 바이트 폴백 + 특수 + 짧은 ASCII(≤3)"""
    keep = set(tok.all_special_ids)
    for ids in id_lists:
        keep.update(ids)
    for ids in tok(list(extra_texts), add_special_tokens=False)["input_ids"] if extra_texts else []:
        keep.update(ids)
    hg = re.compile("[가-힣ㄱ-ㅎㅏ-ㅣ]")
    for i, t in enumerate(tok.convert_ids_to_tokens(list(range(len(tok))))):
        if t and (hg.search(t) or t.startswith("<0x") or re.fullmatch(r"▁?[\x21-\x7e]{1,3}|▁", t)):
            keep.add(i)
    return sorted(keep)
