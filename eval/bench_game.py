"""인게임 A/B 벤치: 같은 시드 로컬 Paper 2대(bench/a·b)에 봇 2개(Miya·Laya) → 같은 시나리오 병렬 실행 → 표
사용: python eval/bench_game.py > bench/game.md   (서버·서빙·봇은 먼저 기동, README: bench/)
판정: inv(아이템 n개 이상) / turn(TURN 로그 act·type·query) / gone(엔티티 처치)
"""
import json, os, re, sys, threading, time, urllib.request

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, f"{H}/../bench")
from rcon import run as rcon  # noqa: E402

BOTS = {"Miya": {"rcon": 25591, "web": 8190, "log": f"{H}/../bench/bot_Miya.log"},
        "Laya": {"rcon": 25592, "web": 8191, "log": f"{H}/../bench/bot_Laya.log"}}
SPAWN = "-632 65 -256"
# (발화, 지급템, 소환, 판정, 제한초)
SC = [
    ("체력 어때", {}, None, ("turn", "질문 답하기", "hp"), 20),
    ("인벤에 뭐있어", {"dirt": 3}, None, ("turn", "질문 답하기", "inv"), 20),
    ("그거론 한참걸리겠는데?", {}, None, ("turn", "지적·조언", None), 20),
    ("나무 5개 캐와", {}, None, ("inv", r"_log$", 5), 240),
    ("작업대 만들어", {"oak_log": 2}, None, ("inv", r"^crafting_table$", 1), 60),
    ("나무곡괭이 만들어", {}, None, ("inv", r"^wooden_pickaxe$", 1), 240),
    ("돌곡 만들어", {"wooden_pickaxe": 1, "oak_log": 3}, None, ("inv", r"^stone_pickaxe$", 1), 300),
    ("흙 10개 파와", {}, None, ("inv", r"^dirt$", 10), 180),
    ("화로 만들어", {"stone_pickaxe": 1, "oak_log": 2}, None, ("inv", r"^furnace$", 1), 300),
    ("철뚝 만들어", {"iron_ingot": 5, "oak_log": 2}, None, ("inv", r"^iron_helmet$", 1), 120),
    ("철곡 만들어", {"raw_iron": 3, "coal": 2, "cobblestone": 8, "oak_log": 4}, None, ("inv", r"^iron_pickaxe$", 1), 300),
    ("철셋 만들어", {"iron_ingot": 24, "oak_log": 2}, None, ("inv", r"^iron_chestplate$", 1), 180),
    ("돼지 잡아", {}, "pig", ("gone", "pig"), 120),
    ("좀비처리해", {"stone_sword": 1}, "zombie", ("gone", "zombie"), 120),
]


def st(b):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{b['web']}/state", timeout=5).read())


def cmd(b, t):
    urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{b['web']}/cmd", json.dumps({"text": t}).encode(), {"Content-Type": "application/json"}), timeout=5).read()


def inv(s):
    d = {}
    for i in s["inv"] + s["armor"]:
        if i:
            d[i["name"][10:]] = d.get(i["name"][10:], 0) + i["count"]
    return d


def tail(f, off):  # 바이트 오프셋 (한글 로그)
    with open(f, "rb") as h:
        h.seek(off); return h.read().decode("utf-8", "replace")


def ent(b, name, typ):
    r = rcon(b["rcon"], f"execute as {name} at @s if entity @e[type={typ},distance=..40]")[0]
    return "passed" in r


def one(name, b, sc, out):
    utt, give, summon, chk, lim = sc
    cmd(b, "멈춰"); time.sleep(2)
    rcon(b["rcon"], f"clear {name}", f"tp {name} {SPAWN}", "time set day", "kill @e[type=!player]", f"effect clear {name}",
         f"effect give {name} resistance 600 4 true", f"effect give {name} saturation 5 0 true",
         *[f"give {name} minecraft:{k} {v}" for k, v in give.items()])
    if summon:
        rcon(b["rcon"], f"execute at {name} run summon {summon} ~3 ~ ~")
    time.sleep(3)
    off = os.path.getsize(b["log"])
    t0 = time.time(); cmd(b, utt)
    ok, busy = False, False
    while time.time() - t0 < lim:
        time.sleep(2)
        s = st(b)
        log = tail(b["log"], off)
        if chk[0] == "turn":
            m = re.search(r"TURN .*? \| (.*?) \[", log)
            if m:
                a, _, q = m.group(1).rsplit(" ", 2)
                ok = a == chk[1] and (chk[2] is None or q == chk[2]); break
        elif chk[0].startswith("inv"):
            if sum(v for k, v in inv(s).items() if re.search(chk[1], k)) >= chk[2]:
                ok = True; break
        elif chk[0] == "gone" and re.search(r"TURN .*? \| 목표 실행 (hunt|combat) ", log) and not ent(b, name, chk[1]):  # 실행 인식 + 처치
            ok = True; break
        busy = busy or s["task"] != "idle"
        if busy and s["task"] == "idle" and time.time() - t0 > 8:
            break  # 포기·종료
    log = tail(b["log"], off)
    says = [l.split(">> ", 1)[1] for l in log.splitlines() if ">> " in l][:3]
    turn = re.search(r"TURN .*? \| (.*?) \[", log)
    out[name] = {"ok": ok, "sec": round(time.time() - t0), "turn": turn.group(1) if turn else "-", "say": " / ".join(says)[:120]}


def main():
    rows, only = [], sys.argv[1:]  # 인자 = 재측정할 발화들
    for sc in [x for x in SC if not only or x[0] in only]:
        out = {}
        ts = [threading.Thread(target=one, args=(n, b, sc, out)) for n, b in BOTS.items()]
        [t.start() for t in ts]; [t.join() for t in ts]
        rows.append((sc[0], out))
        print(sc[0], json.dumps(out, ensure_ascii=False), file=sys.stderr, flush=True)
    print("| 명령 | Miya-0.2 | LAYA base |\n|---|---|---|")
    for u, o in rows:
        f = lambda r: f"{'✅' if r['ok'] else '❌'} {r['sec']}s · {r['turn']} · {r['say']}".replace("|", "/")
        print(f"| {u} | {f(o['Miya'])} | {f(o['Laya'])} |")
    for n in BOTS:
        print(f"\n{n}: {sum(o[n]['ok'] for _, o in rows)}/{len(rows)} 성공, 총 {sum(o[n]['sec'] for _, o in rows)}s")


if __name__ == "__main__":
    main()
