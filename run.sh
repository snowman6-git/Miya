#!/bin/bash
# 서빙+봇(+테스터) 재시작. 로그: /tmp/cw/{serve,bot,tester}.log  사용: ./run.sh [host[:port]] [serve] [tester]
# 설정 우선순위: 인자 > env > .env (예시 .env.example). API 가 원격이면 로컬 서빙 안 띄움
cd "$(dirname "$0")"; mkdir -p /tmp/cw
[ -f .env ] && while IFS='=' read -r k v; do [[ $k =~ ^[A-Z_]+$ && -z ${!k} ]] && export "$k=$v"; done < .env  # 로컬 설정(미공개), 이미 있는 env 우선
for a in "$@"; do [[ $a == serve || $a == tester ]] || { MC_HOST=${a%%:*}; [[ $a == *:* ]] && MC_PORT=${a##*:}; }; done
export MC_HOST=${MC_HOST:-localhost} MC_PORT=${MC_PORT:-25565} API=${API:-http://127.0.0.1:8765}
LOCAL=0; [[ $API =~ ^https?://(127\.0\.0\.1|localhost)(:|/|$) ]] && LOCAL=1
k(){ [ -f /tmp/cw/$1.pid ] && kill -- -$(cat /tmp/cw/$1.pid) 2>/dev/null; true; }  # setsid 그룹째 종료
if (( LOCAL )) && { [[ " $* " == *" serve "* ]] || ! curl -s -m1 -X POST $API/ko -d '{"ids":[]}' >/dev/null; }; then
  k serve; PORT=${API##*:} setsid .venv/bin/python model/serve.py > /tmp/cw/serve.log 2>&1 & echo $! > /tmp/cw/serve.pid
  until grep -q "serve \|Error" /tmp/cw/serve.log; do sleep 1; done
fi
mkdir -p data/botlog; [ -s /tmp/cw/bot.log ] && mv /tmp/cw/bot.log data/botlog/$(date +%F_%H%M%S).log  # 봇로그 보관 → extract_chat 학습데이터
# 봇 종료(서버 재부팅·킥) → 서버 포트 열릴때까지 대기 후 자동 재접속
k bot; (cd bot; LOG=1 HIST=${HIST:-0} setsid bash -c 'while :; do until (exec 3<>/dev/tcp/$MC_HOST/$MC_PORT) 2>/dev/null; do sleep 5; done; sleep 10; node_modules/.bin/tsx src/main.ts; echo "RECONNECT $(date +%T)"; sleep 5; done' >> /tmp/cw/bot.log 2>&1 & echo $! > /tmp/cw/bot.pid)
if [[ " $* " == *" tester "* ]]; then k tester; (cd bot; setsid node_modules/.bin/tsx src/tester.ts > /tmp/cw/tester.log 2>&1 & echo $! > /tmp/cw/tester.pid); fi
until grep -q "SPAWN\|END\|ERR" /tmp/cw/bot.log; do sleep 1; done; tail -2 /tmp/cw/bot.log
