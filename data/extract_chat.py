"""서버로그+봇로그 → 사람 발화 원문·맥락 추출. 이전 모델 판단(intent 등)은 버림(구 데이터셋 금지)
out: data/chat_raw.jsonl  {src,ts,sender,text,prev_bot,prev_user,state}
     data/events_raw.jsonl  death/damage/threat 등 실사건 (QED 시드용)
"""
import glob, gzip, json, os, re
from datetime import datetime

H = os.path.dirname(os.path.abspath(__file__))
BOTS = {"Miya", "Opus5.5_Laya", "LAYA", "LAYA_J", "LAYA2", "init", "Server"}
TESTER = {"Claude", "Claude_Tester"}
EV = {"death", "damage", "threat", "cornered", "shelter", "defend", "smelted", "crafted"}
RX = re.compile(r"^\[(\d\d:\d\d:\d\d)\] \[[^]]*\]: (?:\[Not Secure\] )?<([^>]+)> (.*)$")


def op(p):
    return gzip.open(p, "rt", errors="replace") if p.endswith(".gz") else open(p, errors="replace")


def srv():
    out = []
    for p in sorted(glob.glob(f"{H}/srvlog/*/*.log*")):
        if p.endswith(".log") and os.path.exists(p + ".gz"):  # 같은 로그 중복
            continue
        day = os.path.basename(p)[:10] if os.path.basename(p)[0] == "2" else "latest"
        pb = pu = None
        for ln in op(p):
            m = RX.match(ln.rstrip("\n"))
            if not m:
                continue
            t, who, msg = m.groups()
            if who in BOTS:
                pb = msg
                continue
            if who in TESTER:
                continue
            out.append({"src": "srv:" + p.split("/srvlog/")[1], "ts": f"{day}T{t}", "sender": who, "text": msg, "prev_bot": pb, "prev_user": pu})
            pu = msg
    return out


BRX = re.compile(r"^(\d\d:\d\d:\d\d) << (\S+)(?: \(web\))? (.*)$")
TRX = re.compile(r"^\d\d:\d\d:\d\d TURN .*? \| (\S+ \S+) (\S+) (\S+) (\[.*\])")
ARX = re.compile(r"\x1b\[[0-9;]*m")


def botlog():
    """우리 봇로그(data/botlog/*.log, run.sh가 재시작 전 보관): << 발화 + 다음 TURN(모델판단) + 결과(>> 봇응답, STEP 실패)"""
    out = []
    for p in sorted(glob.glob(f"{H}/botlog/*.log")):
        day = os.path.basename(p)[:10]
        cur = None
        for ln in open(p, errors="replace"):
            ln = ARX.sub("", ln.rstrip("\n"))
            m = BRX.match(ln)
            if m:
                t, who, msg = m.groups()
                if who in BOTS or who in TESTER:  # 테스터(Claude) 발화 제외 (편향)
                    cur = None
                    continue
                cur = {"src": "bot:" + os.path.basename(p), "ts": f"{day}T{t}", "sender": who, "text": msg, "prev_bot": None, "prev_user": None, "pred": None, "reply": [], "fail": []}
                out.append(cur)
            elif cur and (m := TRX.match(ln)):
                cur["pred"] = {"act": m.group(1), "type": m.group(2), "q": m.group(3), "goals": m.group(4)}
            elif cur and " >> " in ln:
                cur["reply"].append(ln.split(" >> ", 1)[1])
            elif cur and " STEP " in ln and " ok " not in ln:
                cur["fail"].append(ln.split(" STEP ", 1)[1])
    return out, []


def main():
    a = srv()
    b, ev = botlog()
    rows = a + b
    # 봇로그 발화에 서버로그 prev_bot 보강: 같은 text 가장 가까운것
    pbm = {}
    for r in a:
        pbm.setdefault(r["text"], r["prev_bot"])
    for r in b:
        r["prev_bot"] = r["prev_bot"] or pbm.get(r["text"])
    with open(f"{H}/chat_raw.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(f"{H}/events_raw.jsonl", "w") as f:
        for e in ev:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    u = {r["text"].strip() for r in rows}
    print(f"rows {len(rows)} (srv {len(a)}, bot {len(b)}), uniq text {len(u)}, events {len(ev)}")


if __name__ == "__main__":
    main()
