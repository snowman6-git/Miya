"""가중치 평균(WiSE-FT): OUT = α·A + (1-α)·B. 이어학습 망각 완화, 학습 없음
사용: A=ckpt/miya-0.2 B=ckpt/miya-0.21 ALPHA=0.3 OUT=ckpt/soup python model/soup.py
A·B 같은 구조·어휘여야 함(이어학습 관계). schema/config 는 B 것 복사
"""
import os, shutil, sys

import torch
from safetensors.torch import save_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from miya import read_ck  # noqa: E402

A, B, OUT = os.environ["A"], os.environ["B"], os.environ["OUT"]
al = float(os.environ.get("ALPHA", 0.5))
a, b = read_ck(A), read_ck(B)
assert a.keys() == b.keys(), set(a) ^ set(b)
sd = {}
for k in b:
    assert a[k].shape == b[k].shape, k
    # 정수 버퍼(remap 등)는 평균 X, B 것 유지
    sd[k] = (al * a[k].float() + (1 - al) * b[k].float()).to(b[k].dtype) if b[k].is_floating_point() else b[k].clone()
os.makedirs(OUT, exist_ok=True)
save_file({k: v.contiguous() for k, v in sd.items()}, f"{OUT}/model.safetensors")
for f in ("schema.json", "config.json"):
    if os.path.exists(f"{B}/{f}"):
        shutil.copy(f"{B}/{f}", f"{OUT}/{f}")
print("soup", A, al, "+", B, 1 - al, "→", OUT)
