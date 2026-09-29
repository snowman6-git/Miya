# 인포그래픽 생성기. LANG=en 이면 영문판 (docs/miya_infographic.en.svg)
import base64, os, pathlib
EN = {
'→ QED 반영해 재계획 ≤ 5': '→ replan with QED, ≤ 5 times',
'→ 같은 단계 재시도 ≤ 3': '→ retry the same step, ≤ 3 times',
'→ 중복 제작 없음, 남의 상자 구분': '→ no duplicates, own vs others\' chests',
'139M 인코더': '139M encoder',
'1,628개 · ColBERT': '1,628 items · ColBERT',
'170초" 를 붙임': 'avg 170 s" added',
'1회 인코딩 ~18ms': '1 pass ~18 ms',
'312M → 139M (어휘 가지치기)': '312M → 139M (vocab pruning)',
'act = 목표 실행': 'act = run goal',
'act·type·prio·방법': 'act·type·prio·method',
'bf16 · 턴 p50 17.8ms': 'bf16 · turn p50 17.8 ms',
'GOAL 예시: 철 곡괭이': 'GOAL example: iron pickaxe',
'GOAL 완료': 'GOAL done',
'[MASK]라벨×n': '[MASK]label×n',
'mmBERT 22층': 'mmBERT 22 layers',
'planner · 사실만': 'planner · facts only',
'/plan · 모델': '/plan · model',
'QED 경험 일기': 'QED experience diary',
'/turn · 모델': '/turn · model',
'vs LAYA base (판단만 교체)': 'vs LAYA base (decisions only)',
'가치': 'Value',
'개수 ↔ 대상': 'count ↔ target',
'걷기·캐기·제작': 'walk · dig · craft',
'게임 채팅': 'in-game chat',
'"경험 5회': '"5 runs,',
'경험 빼고 다시 선택 → 다르면 배지 "QED: A → B"': 'Re-choose without experience → if different, badge "QED: A → B"',
'경험 주입': 'Experience',
'광석 높이·연료': 'ore height · fuel',
'구간 추출': 'Spans',
'굽기': 'Smelt',
'기록': 'Record',
'나무 곡괭이': 'Wood pickaxe',
'놓은 작업대·화로·상자 기억': 'Remembers placed tables, furnaces, chests',
'다음 같은 요청은': 'next time, same',
'다음엔 그 선택지 피하기': 'avoid that choice next time',
'다음 판단에 경험으로 되먹임 = 재귀적 자기개선': 'Fed back into the next decision (self-improvement)',
'다이아 풀셋 → 되찾기': 'full diamond → recover',
'단계별 도구·시간': 'per-step tool · time',
'단계 재시도 ≤ 3 · 재계획 ≤ 5': 'Step retry ≤ 3 · replan ≤ 5',
'대상·개수·좌표 7종': 'target·count·pos, 7 kinds',
'대상 아이템 87.3% (6.2%)': 'Target item 87.3% (6.2%)',
'더 나은 방법으로': 'request, better way',
'도망': 'Flee',
'돌 곡괭이': 'Stone pickaxe',
'돌 채광': 'Mine stone',
'동물 없음': 'No prey',
'레시피·채굴시간': 'recipes · dig time',
'먹기': 'Eat',
'명령 하나가 처리되는 길': 'How one command is handled',
'모델 안쪽': 'Inside the model',
'모델이 우선순위': 'Model decides',
'모르면 되묻기: "철뚝이 뭔가요?"': 'Unsure? Ask: "What\'s 철뚝?"',
'무한루프 차단': 'Infinite-loop guards',
'문항:[MASK]보기…': 'Q:[MASK]opt…',
'발화 이해': 'Understand',
'밤': 'Night',
'방법·단계·도구': 'method · steps · tool',
'방법 선택': 'Choose',
'방법 후보 ≤ 6': '≤ 6 method options',
'배고픔': 'Hunger',
'벌목': 'Chop logs',
'보기 점수': 'Options',
'봇 · mineflayer': 'bot · mineflayer',
'사냥': 'Hunt',
'사망·설치물': 'deaths · placed',
'사망 원인·가해자': 'death cause · killer',
'산소': 'Air',
'상태': 'State',
'상태·QED': 'state·QED',
'상태가 바뀔 때만 /prio 요청': '/prio only when state changes',
'생존 · 경험 · 안전장치': 'Survival · Experience · Safety',
'생존 우선순위 86.6% (11.5%)': 'Survival prio 86.6% (11.5%)',
'생존 판단  /prio': 'Survival  /prio',
'설치물 재사용': 'reuse own blocks',
'설치한 블럭 위치': 'placed block positions',
'성공 80% 평균': '80% success,',
'소요 ms·성패': 'ms · success',
'숨기': 'Hide',
'실발화 의도 94.5% (11.0%)': 'Real intent 94.5% (11.0%)',
'실패하면 재시도': 'retry on failure',
'실행': 'Execute',
'"아아 철 헬멧 ㅇㅇ" → 답까지 합쳐 다시 인식': '"ah, iron helmet" → re-read with the answer',
'아이템 링크': 'Item link',
'연속 실패가 QED로 보임 → 같은 방법 X': 'Repeated failures visible via QED → no repeats',
'영구 실패 (자원 없음·막힘)': 'Hard failure (no resource, blocked)',
'예상 시간·성공률': 'est. time · success',
'예: 철곡 ㄱㄱ': 'e.g. 철곡 ㄱㄱ ("iron pick, go")',
'완료를 채팅으로': 'reports in chat',
'완료 인지': 'Done',
'요청·방법·성패·ms': 'request·method·ok·ms',
'요청 폭주 ✗': 'request flood ✗',
'원목 ×3': 'log ×3',
'원정·계단굴': 'expedition · stairs',
'위협': 'Threat',
'음슴체도 OK': 'internet slang OK',
'이유를 채팅으로': 'explains in chat',
'이전 모델': 'Previous model',
'인게임 13/14 (0/14)': 'In-game 13/14 (0/14)',
'일시 실패 (끼임·동기화)': 'Transient failure (stuck, desync)',
'입력 (GLiNER2식 스키마)': 'Input (GLiNER2-style schema)',
'있으면 재사용': 'reuse if exists',
'자동 재개 상한 (resume_max)': 'Auto-resume cap (resume_max)',
'작업대': 'Crafting table',
'작업대 제작': 'craft at table',
'재개': 'Resume',
'전투': 'Fight',
'전투·도망 결정은 잠시 유지': 'Fight/flee decisions held briefly',
'조약돌 ×3': 'cobblestone ×3',
'조합': 'craft',
'줄임말·인터넷체': 'abbreviations',
'질문·보기를 입력에 같이 넣고 1회 인코딩으로 모든 판단': 'questions + options in the input, every decision in one pass',
'짝': 'Pairing',
'철곡 → 철 곡괭이': '철곡 → iron pickaxe',
'"철곡 ㄱㄱ"': '"철곡 ㄱㄱ"',
'철 곡괭이': 'Iron pickaxe',
'철 채광': 'Mine iron',
'체력': 'HP',
'체력 없음': 'Low HP',
'크리퍼에 사망': 'Creeper death',
'판단 = 모델 · 실행 = 봇': 'model decides · bot acts',
'판자·막대': 'Planks · sticks',
'플레이어 채팅': 'Player chat',
'한국어 한마디 → 모델이 판단 → 봇이 실행 → 경험이 쌓여 다음 판단이 좋아짐': 'One Korean line → model decides → bot acts → experience makes the next decision better',
'한눈에 보기': 'at a glance',
'한 번의 명령으로 단계를 만들고 끝까지 진행': 'one command → steps generated and run to the end',
'"화로는 있는거 쓸게요"': '"Reusing the furnace"',
'화로 재사용·석탄': 'reuse furnace · coal',
'후보 계산': 'Options',
'후보 중 1개 선택': 'picks one option',
'흙 하나 잃음 → 굳이 안 감': 'lost 1 dirt → not worth it',
}
EN_MODE = os.environ.get('LANG_OUT') == 'en'
def tr(s): return EN.get(s, s) if EN_MODE else s
R = pathlib.Path(__file__).resolve().parent.parent
ICON = base64.b64encode((R / 'docs/miya_icon.webp').read_bytes()).decode()
W, H = 1600, 1700
INK, SUB, LINE = '#263238', '#607d8b', '#cfd8dc'
GRN, BLU, ORG, PUR, BRN, RED, SLT = '#43a05a', '#3b78d0', '#e08a2c', '#8a5cc7', '#9a6a3a', '#d9534f', '#455a64'
LIGHT = {GRN: '#e3f4e7', BLU: '#e2edfb', ORG: '#fcefdf', PUR: '#efe7fa', BRN: '#f3e9dd', RED: '#fbe5e4', SLT: '#e6ecef'}
o = []
a = o.append

def esc(s): return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
def T(x, y, s, size=15, w=400, fill=INK, anchor='middle', mono=False):
    s = tr(s)
    fam = ' font-family="\'Noto Sans Mono CJK KR\',monospace"' if mono else ''
    a(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}"{fam}>{esc(s)}</text>')
def U(icon, x, y, s, color=INK):
    a(f'<use href="#{icon}" x="{x}" y="{y}" width="{s}" height="{s}" color="{color}"/>')
def box(x, y, w, h, fill='#fff', stroke=LINE, sw=2, r=14, extra=''):
    a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')
def arrow(x1, y1, x2, y2, c=SUB, dash=False, m='ar'):
    d = ' stroke-dasharray="7 6"' if dash else ''
    a(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="3"{d} marker-end="url(#{m})"/>')
def pill(x, y, w, h, color, s, size=14, fg='#fff'):
    box(x, y, w, h, color, color, 0, h / 2)
    T(x + w / 2, y + h / 2 + size * 0.36, s, size, 700, fg)
def section(n, y, s, sub=''):
    a(f'<circle cx="58" cy="{y - 8}" r="18" fill="{INK}"/>')
    T(58, y - 1, str(n), 20, 800, '#fff')
    T(88, y, s, 24, 800, INK, 'start')
    s = tr(s)
    if sub: T(88 + sum(24 if ord(ch) > 0x3000 else 13.5 for ch in s) + 18, y, sub, 16, 400, SUB, 'start')

SYM = '''
<symbol id="chat" viewBox="0 0 48 48"><path d="M8 8h32a4 4 0 0 1 4 4v18a4 4 0 0 1-4 4H21l-10 8v-8H8a4 4 0 0 1-4-4V12a4 4 0 0 1 4-4z" fill="currentColor"/><circle cx="15" cy="21" r="3" fill="#fff"/><circle cx="24" cy="21" r="3" fill="#fff"/><circle cx="33" cy="21" r="3" fill="#fff"/></symbol>
<symbol id="brain" viewBox="0 0 48 48"><g fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M22 8a6 6 0 0 0-10 3 6 6 0 0 0-5 8 6 6 0 0 0 0 10 6 6 0 0 0 5 8 6 6 0 0 0 10 3z"/><path d="M26 8a6 6 0 0 1 10 3 6 6 0 0 1 5 8 6 6 0 0 1 0 10 6 6 0 0 1-5 8 6 6 0 0 1-10 3z"/><path d="M12 20c3 0 5 2 5 5M36 20c-3 0-5 2-5 5M13 32c3-2 6-2 9-1M35 32c-3-2-6-2-9-1"/></g></symbol>
<symbol id="gear" viewBox="0 0 48 48"><circle cx="24" cy="24" r="16" fill="none" stroke="currentColor" stroke-width="7" stroke-dasharray="6.28 6.28"/><circle cx="24" cy="24" r="13" fill="currentColor"/><circle cx="24" cy="24" r="5.5" fill="#fff"/></symbol>
<symbol id="book" viewBox="0 0 48 48"><path d="M24 12c-5-4-12-4-19-2v27c7-2 14-2 19 2 5-4 12-4 19-2V10c-7-2-14-2-19 2z" fill="currentColor"/><path d="M24 12v27M10 17c3-1 6-1 9 0M10 23c3-1 6-1 9 0M10 29c3-1 6-1 9 0M29 17c3-1 6-1 9 0M29 23c3-1 6-1 9 0" stroke="#fff" stroke-width="2.2" fill="none" stroke-linecap="round"/></symbol>
<symbol id="target" viewBox="0 0 48 48"><circle cx="24" cy="24" r="18" fill="none" stroke="currentColor" stroke-width="4"/><circle cx="24" cy="24" r="10" fill="none" stroke="currentColor" stroke-width="4"/><circle cx="24" cy="24" r="4" fill="currentColor"/><path d="M24 24 40 8M34 8h6v6" stroke="currentColor" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="pick" viewBox="0 0 48 48"><g transform="rotate(45 24 24)"><rect x="21.5" y="12" width="5" height="32" rx="2" fill="#8d5a2b" stroke="#3e2a17" stroke-width="1.6"/><path d="M4 16Q24 0 44 16Q24 8 4 16z" fill="none" stroke="#37474f" stroke-width="6" stroke-linejoin="round"/><path d="M4 16Q24 0 44 16Q24 8 4 16z" fill="currentColor" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/></g></symbol>
<symbol id="db" viewBox="0 0 48 48"><path d="M8 11v26c0 3.5 7 6 16 6s16-2.5 16-6V11" fill="currentColor"/><ellipse cx="24" cy="11" rx="16" ry="6" fill="currentColor"/><ellipse cx="24" cy="11" rx="12" ry="3.4" fill="#fff" opacity=".45"/><path d="M8 20c0 3.5 7 6 16 6s16-2.5 16-6M8 29c0 3.5 7 6 16 6s16-2.5 16-6" fill="none" stroke="#fff" stroke-width="2.4"/></symbol>
<symbol id="flag" viewBox="0 0 48 48"><path d="M10 6v38" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 8h26l-6 8 6 8H12z" fill="currentColor"/></symbol>
<symbol id="check" viewBox="0 0 48 48"><circle cx="24" cy="24" r="21" fill="currentColor"/><path d="M13 25l7 7 15-15" stroke="#fff" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="xmark" viewBox="0 0 48 48"><circle cx="24" cy="24" r="21" fill="currentColor"/><path d="M16 16l16 16M32 16 16 32" stroke="#fff" stroke-width="5" stroke-linecap="round"/></symbol>
<symbol id="qmark" viewBox="0 0 48 48"><circle cx="24" cy="24" r="21" fill="currentColor"/><path d="M17 18a7 7 0 1 1 10 6c-2 1-3 2-3 5" stroke="#fff" stroke-width="4.5" fill="none" stroke-linecap="round"/><circle cx="24" cy="36" r="2.8" fill="#fff"/></symbol>
<symbol id="loop" viewBox="0 0 48 48"><g fill="none" stroke="currentColor" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"><path d="M38 20A15 15 0 0 0 10 17"/><path d="M10 28a15 15 0 0 0 28 3"/><path d="M38 9v11H27M10 39V28h11"/></g></symbol>
<symbol id="pin" viewBox="0 0 48 48"><path d="M24 44S9 28 9 18a15 15 0 0 1 30 0c0 10-15 26-15 26z" fill="currentColor"/><circle cx="24" cy="18" r="6" fill="#fff"/></symbol>
<symbol id="heart" viewBox="0 0 48 48"><path d="M24 42 8 26a9.5 9.5 0 0 1 16-12 9.5 9.5 0 0 1 16 12z" fill="currentColor"/></symbol>
<symbol id="meat" viewBox="0 0 48 48"><ellipse cx="20" cy="20" rx="14" ry="12" transform="rotate(-40 20 20)" fill="#c0703a"/><ellipse cx="18" cy="18" rx="7" ry="5" transform="rotate(-40 18 18)" fill="#e0955a"/><path d="M29 29l9 9" stroke="#f1ead8" stroke-width="5" stroke-linecap="round"/><circle cx="40" cy="36" r="3.4" fill="#f1ead8"/><circle cx="36" cy="40" r="3.4" fill="#f1ead8"/></symbol>
<symbol id="zomb" viewBox="0 0 16 16" shape-rendering="crispEdges"><rect width="16" height="16" fill="#4f8a3c"/><rect y="0" width="16" height="4" fill="#3b6b2c"/><rect x="3" y="6" width="3" height="2" fill="#10240b"/><rect x="10" y="6" width="3" height="2" fill="#10240b"/><rect x="6" y="10" width="4" height="2" fill="#2b4d22"/><rect x="2" y="12" width="2" height="2" fill="#3b6b2c"/></symbol>
<symbol id="moon" viewBox="0 0 48 48"><path d="M30 6a18 18 0 1 0 12 28A15 15 0 0 1 30 6z" fill="currentColor"/><circle cx="37" cy="12" r="2" fill="currentColor"/></symbol>
<symbol id="bubble" viewBox="0 0 48 48"><g fill="none" stroke="currentColor" stroke-width="3.4"><circle cx="18" cy="28" r="11"/><circle cx="35" cy="14" r="6"/><circle cx="37" cy="35" r="4"/></g><path d="M12 25a7 7 0 0 1 5-5" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round"/></symbol>
<symbol id="sword" viewBox="0 0 48 48"><g transform="rotate(45 24 24)"><path d="M21 4h6v26h-6z" fill="#dfe6ea" stroke="currentColor" stroke-width="2"/><rect x="14" y="30" width="20" height="5" rx="2" fill="currentColor"/><rect x="21.5" y="35" width="5" height="9" rx="2" fill="#8d5a2b"/></g></symbol>
<symbol id="run" viewBox="0 0 48 48"><path d="M8 10l14 14-14 14M24 10l14 14-14 14" stroke="currentColor" stroke-width="5.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="home" viewBox="0 0 48 48"><path d="M6 24 24 8l18 16" stroke="currentColor" stroke-width="4.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M11 22v19h26V22" fill="currentColor"/><rect x="20" y="29" width="8" height="12" fill="#fff"/></symbol>
<symbol id="play" viewBox="0 0 48 48"><circle cx="24" cy="24" r="21" fill="currentColor"/><path d="M19 14v20l16-10z" fill="#fff"/></symbol>
<symbol id="skull" viewBox="0 0 48 48"><path d="M24 5C13 5 7 12 7 21c0 6 3 10 7 12v7h20v-7c4-2 7-6 7-12 0-9-6-16-17-16z" fill="currentColor"/><circle cx="17" cy="22" r="5" fill="#fff"/><circle cx="31" cy="22" r="5" fill="#fff"/><path d="M22 31l2-4 2 4z" fill="#fff"/><path d="M19 36v4M24 36v4M29 36v4" stroke="#fff" stroke-width="2"/></symbol>
<symbol id="list" viewBox="0 0 48 48"><rect x="7" y="5" width="34" height="38" rx="4" fill="currentColor"/><path d="M14 15h20M14 24h20M14 33h13" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/></symbol>
<symbol id="gem" viewBox="0 0 48 48"><path d="M14 8h20l9 11-19 23L5 19z" fill="#4fd1c5"/><path d="M5 19h38M14 8l10 34 10-34M19 19l5-11 5 11" stroke="#1d8a80" stroke-width="2" fill="none"/></symbol>
<symbol id="dirt" viewBox="0 0 16 16" shape-rendering="crispEdges"><rect width="16" height="16" fill="#8b5e3c"/><rect y="0" width="16" height="4" fill="#5fa04a"/><rect x="2" y="7" width="2" height="2" fill="#6d4a2f"/><rect x="9" y="10" width="2" height="2" fill="#6d4a2f"/><rect x="12" y="6" width="2" height="2" fill="#a47550"/></symbol>
<symbol id="log" viewBox="0 0 16 16" shape-rendering="crispEdges"><rect width="16" height="16" fill="#6b4a2b"/><rect x="2" width="2" height="16" fill="#553a21"/><rect x="7" width="1" height="16" fill="#7c5733"/><rect x="11" width="2" height="16" fill="#553a21"/><rect x="5" y="4" width="1" height="3" fill="#3f2b18"/><rect x="13" y="10" width="1" height="3" fill="#3f2b18"/></symbol>
<symbol id="plank" viewBox="0 0 16 16" shape-rendering="crispEdges"><rect width="16" height="16" fill="#b8894d"/><rect y="3" width="16" height="1" fill="#8f6a38"/><rect y="7" width="16" height="1" fill="#8f6a38"/><rect y="11" width="16" height="1" fill="#8f6a38"/><rect y="15" width="16" height="1" fill="#8f6a38"/><rect x="5" width="1" height="3" fill="#8f6a38"/><rect x="11" y="4" width="1" height="3" fill="#8f6a38"/><rect x="3" y="8" width="1" height="3" fill="#8f6a38"/><rect x="9" y="12" width="1" height="3" fill="#8f6a38"/></symbol>
<symbol id="table" viewBox="0 0 16 16" shape-rendering="crispEdges"><rect width="16" height="16" fill="#9c6c3a"/><rect x="1" y="1" width="14" height="14" fill="#c49a5e"/><rect x="1" y="5" width="14" height="1" fill="#6b4a2b"/><rect x="1" y="10" width="14" height="1" fill="#6b4a2b"/><rect x="5" y="1" width="1" height="14" fill="#6b4a2b"/><rect x="10" y="1" width="1" height="14" fill="#6b4a2b"/><rect x="2" y="2" width="2" height="2" fill="#8a8a8a"/><rect x="12" y="12" width="2" height="2" fill="#d9d9d9"/></symbol>
<symbol id="stone" viewBox="0 0 16 16" shape-rendering="crispEdges"><rect width="16" height="16" fill="#8e8e8e"/><rect x="2" y="3" width="3" height="1" fill="#6f6f6f"/><rect x="9" y="2" width="2" height="2" fill="#a5a5a5"/><rect x="5" y="8" width="3" height="2" fill="#6f6f6f"/><rect x="12" y="9" width="2" height="1" fill="#6f6f6f"/><rect x="2" y="12" width="2" height="2" fill="#a5a5a5"/><rect x="10" y="13" width="3" height="1" fill="#6f6f6f"/></symbol>
<symbol id="ore" viewBox="0 0 16 16" shape-rendering="crispEdges"><use href="#stone" width="16" height="16"/><rect x="3" y="3" width="3" height="2" fill="#d8ad8c"/><rect x="4" y="5" width="2" height="1" fill="#b98a66"/><rect x="10" y="5" width="3" height="2" fill="#e6c3a5"/><rect x="6" y="10" width="3" height="2" fill="#d8ad8c"/><rect x="11" y="11" width="2" height="2" fill="#b98a66"/></symbol>
<symbol id="furn" viewBox="0 0 16 16" shape-rendering="crispEdges"><rect width="16" height="16" fill="#6e6e6e"/><rect x="1" y="1" width="14" height="4" fill="#858585"/><rect x="4" y="7" width="8" height="7" fill="#262626"/><rect x="5" y="10" width="6" height="4" fill="#f08a1c"/><rect x="6" y="9" width="2" height="2" fill="#ffc94a"/><rect x="9" y="11" width="1" height="3" fill="#ffc94a"/></symbol>
<symbol id="coal" viewBox="0 0 16 16" shape-rendering="crispEdges"><rect x="3" y="4" width="10" height="8" fill="#2b2b2b"/><rect x="4" y="3" width="6" height="1" fill="#2b2b2b"/><rect x="5" y="12" width="7" height="1" fill="#2b2b2b"/><rect x="5" y="5" width="2" height="2" fill="#555"/><rect x="9" y="8" width="2" height="1" fill="#555"/></symbol>
<marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" fill="#607d8b"/></marker>
<marker id="ap" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" fill="#8a5cc7"/></marker>
<marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" fill="#d9534f"/></marker>
<filter id="sh" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#263238" flood-opacity=".12"/></filter>
<clipPath id="icc"><rect x="36" y="18" width="92" height="92" rx="20"/></clipPath>
'''
a(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="\'Noto Sans CJK KR\',\'Noto Sans KR\',\'Apple SD Gothic Neo\',\'Malgun Gothic\',sans-serif">')
a('<defs>' + SYM + '</defs>')
a(f'<rect width="{W}" height="{H}" fill="#f7f6f1"/>')

# ── header
a(f'<rect width="{W}" height="128" fill="#2f3e46"/>')
for i in range(0, W, 32):  # 잔디 띠
    a(f'<use href="#dirt" x="{i}" y="128" width="32" height="32"/>')
a(f'<image href="data:image/webp;base64,{ICON}" xlink:href="data:image/webp;base64,{ICON}" x="36" y="18" width="92" height="92" clip-path="url(#icc)"/>')
T(150, 70, 'Miya', 48, 800, '#fff', 'start')
T(290, 70, '한눈에 보기', 30, 700, '#b0bec5', 'start')
T(150, 104, '한국어 한마디 → 모델이 판단 → 봇이 실행 → 경험이 쌓여 다음 판단이 좋아짐', 18, 400, '#cfd8dc', 'start')
for i, (s, c) in enumerate([('139M 인코더', BLU), ('1회 인코딩 ~18ms', GRN), ('판단 = 모델 · 실행 = 봇', ORG)]):
    pill(1008 + [0, 150, 330][i], 46, [138, 168, 222][i], 36, c, s, 15)

# ── ① 명령 흐름
Y1 = 212
section(1, Y1, '명령 하나가 처리되는 길', '예: 철곡 ㄱㄱ')
cards = [
    ('chat', GRN, '플레이어 채팅', '게임 채팅', ['"철곡 ㄱㄱ"', '줄임말·인터넷체', '음슴체도 OK']),
    ('brain', BLU, '발화 이해', '/turn · 모델', ['act = 목표 실행', 'type = craft', '철곡 → 철 곡괭이']),
    ('gear', ORG, '후보 계산', 'planner · 사실만', ['레시피·채굴시간', '광석 높이·연료', '방법 후보 ≤ 6']),
    ('book', PUR, '경험 주입', 'QED', ['"경험 5회', '성공 80% 평균', '170초" 를 붙임']),
    ('target', BLU, '방법 선택', '/plan · 모델', ['후보 중 1개 선택', '이유를 채팅으로', '"화로는 있는거 쓸게요"']),
    ('pick', BRN, '실행', '봇 · mineflayer', ['걷기·캐기·제작', '설치물 재사용', '실패하면 재시도']),
    ('db', PUR, '기록', '/qed', ['방법·단계·도구', '소요 ms·성패', '사망·설치물']),
    ('flag', GRN, '완료 인지', 'GOAL done', ['완료를 채팅으로', '다음 같은 요청은', '더 나은 방법으로']),
]
cy = Y1 + 30
for i, (ic, c, t, tag, ls) in enumerate(cards):
    x = 40 + i * 194
    a('<g filter="url(#sh)">'); box(x, cy, 160, 222, '#fff', c, 2.5, 16); a('</g>')
    a(f'<circle cx="{x + 80}" cy="{cy + 50}" r="34" fill="{LIGHT[c]}"/>')
    U(ic, x + 58, cy + 28, 44, c)
    a(f'<circle cx="{x + 18}" cy="{cy + 18}" r="12" fill="{c}"/>'); T(x + 18, cy + 23, str(i + 1), 13, 800, '#fff')
    T(x + 80, cy + 110, t, 19, 800, INK)
    T(x + 80, cy + 132, tag, 13, 500, c, mono=True)
    for j, s in enumerate(ls):
        T(x + 80, cy + 160 + j * 21, s, 13.5, 400, INK)
    if i < 7: arrow(x + 164, cy + 110, x + 190, cy + 110)
# 되묻기 가지
bx, by = 60, cy + 262
arrow(274, cy + 224, 274, by - 4, BLU, True)
box(bx, by, 440, 78, '#fff', BLU, 2, 14, 'stroke-dasharray="7 5"')
U('qmark', bx + 14, by + 17, 44, BLU)
T(bx + 72, by + 32, '모르면 되묻기: "철뚝이 뭔가요?"', 16, 700, INK, 'start')
T(bx + 72, by + 58, '"아아 철 헬멧 ㅇㅇ" → 답까지 합쳐 다시 인식', 14, 400, SUB, 'start')
# QED 되먹임 루프 (7 → 4)
lx1, lx2, ly = 1204 + 80, 622 + 80, cy + 300
a(f'<path d="M{lx1} {cy + 226} V{ly} H{lx2} V{cy + 232}" fill="none" stroke="{PUR}" stroke-width="3.5" stroke-dasharray="9 6" marker-end="url(#ap)"/>')
box(760, ly - 22, 470, 44, '#fff', PUR, 2, 22)
U('loop', 774, ly - 15, 30, PUR)
T(1010, ly + 6, '다음 판단에 경험으로 되먹임 = 재귀적 자기개선', 16, 700, PUR)

# ── ② GOAL 단계
Y2 = 650
section(2, Y2, 'GOAL 예시: 철 곡괭이', '한 번의 명령으로 단계를 만들고 끝까지 진행')
steps = [('log', '벌목', '원목 ×3'), ('plank', '판자·막대', '조합'), ('table', '작업대', '있으면 재사용'),
         ('pickw', '나무 곡괭이', '작업대 제작'), ('stone', '돌 채광', '조약돌 ×3'), ('picks', '돌 곡괭이', '작업대 제작'),
         ('ore', '철 채광', '원정·계단굴'), ('furn', '굽기', '화로 재사용·석탄'), ('picki', '철 곡괭이', 'GOAL 완료')]
sy = Y2 + 52
tags = {4: ('TASK_NOW', BLU), 5: ('TASK_NEXT', ORG), 8: ('TASK_GOAL', GRN)}
for i, (ic, t, cap) in enumerate(steps):
    x = 40 + i * 172
    c = tags.get(i, (0, LINE))[1]
    a('<g filter="url(#sh)">'); box(x, sy, 140, 158, LIGHT[GRN] if i == 8 else '#fff', c, 3.5 if i in tags else 2, 14); a('</g>')
    if i == 8: a(f'<circle cx="{x + 70}" cy="{sy + 48}" r="38" fill="#2f3e46"/>')
    if ic.startswith('pick'):
        col = {'w': '#b0804a', 's': '#8e8e8e', 'i': '#e9eef0'}[ic[-1]]
        a(f'<g color="{col}"><use href="#pick" x="{x + 38}" y="{sy + 16}" width="64" height="64" stroke="#546e7a" stroke-width="0"/></g>')
    else:
        a(f'<use href="#{ic}" x="{x + 42}" y="{sy + 20}" width="56" height="56"/>')
    if ic == 'furn': a(f'<use href="#coal" x="{x + 92}" y="{sy + 54}" width="30" height="30"/>')
    if ic == 'table': U('loop', x + 104, sy + 12, 26, GRN)
    T(x + 70, sy + 108, t, 15.5 if EN_MODE else 17, 800, INK)
    T(x + 70, sy + 132, cap, 13, 400, SUB)
    if i < 4: U('check', x + 114, sy - 10, 28, GRN)
    if i in tags: pill(x + 20, sy - 17, 100, 26, tags[i][1], tags[i][0], 12.5)
    if i < 8: arrow(x + 143, sy + 79, x + 168, sy + 79)
ny = sy + 190
for i, (ic, c, s1, s2) in enumerate([
        ('loop', BLU, '일시 실패 (끼임·동기화)', '→ 같은 단계 재시도 ≤ 3'),
        ('gear', ORG, '영구 실패 (자원 없음·막힘)', '→ QED 반영해 재계획 ≤ 5'),
        ('pin', GRN, '놓은 작업대·화로·상자 기억', '→ 중복 제작 없음, 남의 상자 구분')]):
    x = 40 + i * 515
    box(x, ny, 490, 64, LIGHT[c], c, 1.5, 14)
    U(ic, x + 14, ny + 12, 40, c)
    T(x + 68, ny + 27, s1, 16, 700, INK, 'start'); T(x + 68, ny + 50, s2, 14.5, 400, INK, 'start')

# ── ③ 생존 · QED · 루프차단
Y3 = 1010
section(3, Y3, '생존 · 경험 · 안전장치')
py, ph, pw = Y3 + 26, 360, 490
def panel(x, c, ic, title):
    a('<g filter="url(#sh)">'); box(x, py, pw, ph, '#fff', c, 2, 16); a('</g>')
    a(f'<path d="M{x} {py + 16}a16 16 0 0 1 16-16h{pw - 32}a16 16 0 0 1 16 16v38H{x}z" fill="{c}"/>')
    U(ic, x + 16, py + 9, 36, '#fff'); T(x + 62, py + 36, title, 19, 800, '#fff', 'start')
# A 생존
x = 40; panel(x, RED, 'heart', '생존 판단  /prio')
T(x + 20, py + 84, '상태', 14, 700, SUB, 'start')
for j, (ic, s, c) in enumerate([('heart', '체력', RED), ('meat', '배고픔', INK), ('zomb', '위협', INK), ('moon', '밤', '#5c6bc0'), ('bubble', '산소', '#29b6f6')]):
    cx = x + 65 + j * 90
    U(ic, cx - 22, py + 96, 44, c); T(cx, py + 162, s, 14, 500, INK)
arrow(x + 245, py + 176, x + 245, py + 204, RED, m='arr')
box(x + 150, py + 208, 190, 40, LIGHT[RED], RED, 1.5, 20)
U('brain', x + 162, py + 213, 30, RED); T(x + 260, py + 234, '모델이 우선순위', 15, 700, INK)
arrow(x + 245, py + 252, x + 245, py + 274, RED, m='arr')
for j, (ic, s, c) in enumerate([('sword', '전투', SLT), ('run', '도망', ORG), ('meat', '먹기', INK), ('home', '숨기', BRN), ('play', '재개', GRN)]):
    cx = x + 65 + j * 90
    box(cx - 38, py + 278, 76, 72, '#fafafa', LINE, 1.5, 12)
    U(ic, cx - 17, py + 284, 34, c); T(cx, py + 338, s, 14, 700, INK)
# B QED
x = 555; panel(x, PUR, 'book', 'QED 경험 일기')
for j, (ic, t, s) in enumerate([('target', 'goals', '요청·방법·성패·ms'), ('list', 'steps', '단계별 도구·시간'), ('skull', 'deaths', '사망 원인·가해자'), ('pin', 'placed', '설치한 블럭 위치')]):
    bx2, by2 = x + 18 + (j % 2) * 232, py + 70 + (j // 2) * 72
    box(bx2, by2, 222, 62, LIGHT[PUR], PUR, 1, 12)
    U(ic, bx2 + 10, by2 + 12, 38, PUR)
    T(bx2 + 58, by2 + 27, t, 15, 700, PUR, 'start', mono=True); T(bx2 + 58, by2 + 48, s, 13, 400, INK, 'start')
yy = py + 228
U('skull', x + 20, yy, 30, INK); T(x + 58, yy + 21, '크리퍼에 사망', 14, 700, INK, 'start')
arrow(x + 168, yy + 15, x + 198, yy + 15, PUR, m='ap')
T(x + 206, yy + 21, '다음엔 그 선택지 피하기', 14, 700, PUR, 'start')
yy += 44
U('dirt', x + 22, yy + 2, 26); T(x + 58, yy + 21, '흙 하나 잃음 → 굳이 안 감', 14, 400, INK, 'start')
U('gem', x + 262, yy, 30); T(x + 298, yy + 21, '다이아 풀셋 → 되찾기', 14, 400, INK, 'start')
yy += 44
box(x + 18, yy, 454, 34, '#fff', PUR, 1.5, 17, 'stroke-dasharray="5 4"')
T(x + 245, yy + 23, '경험 빼고 다시 선택 → 다르면 배지 "QED: A → B"', 13.5, 700, PUR)
# C 루프차단
x = 1070; panel(x, SLT, 'loop', '무한루프 차단')
T(x + 20, py + 84, '이전 모델', 14, 700, SUB, 'start')
ring = [('heart', '체력 없음', RED), ('pick', '사냥', BRN), ('xmark', '동물 없음', SLT)]
for j, (ic, s, c) in enumerate(ring):
    cx = x + 90 + j * 150
    box(cx - 62, py + 96, 124, 44, '#fff', LINE, 1.5, 22)
    U(ic, cx - 54, py + 103, 30, c); T(cx + 16, py + 124, s, 14, 700, INK)
    if j < 2: arrow(cx + 64, py + 118, cx + 86, py + 118, RED, m='arr')
a(f'<path d="M{x + 390} {py + 142} v18 H{x + 90} v-14" fill="none" stroke="{RED}" stroke-width="3" marker-end="url(#arr)"/>')
pill(x + 180, py + 148, 130, 26, RED, '요청 폭주 ✗', 13)
T(x + 20, py + 204, 'Miya', 14, 700, SUB, 'start')
for j, s in enumerate(['단계 재시도 ≤ 3 · 재계획 ≤ 5', '자동 재개 상한 (resume_max)', '상태가 바뀔 때만 /prio 요청', '전투·도망 결정은 잠시 유지', '연속 실패가 QED로 보임 → 같은 방법 X']):
    U('check', x + 22, py + 214 + j * 28, 22, GRN); T(x + 54, py + 231 + j * 28, s, 14.5, 500, INK, 'start')

# ── ④ 모델 안쪽
Y4 = 1440
section(4, Y4, '모델 안쪽', '질문·보기를 입력에 같이 넣고 1회 인코딩으로 모든 판단')
my = Y4 + 26
box(40, my, 560, 138, '#fff', BLU, 2, 14)
T(60, my + 28, '입력 (GLiNER2식 스키마)', 15, 700, BLU, 'start')
def toks(y, arr):
    xx = 60
    for s, c in arr:
        s = tr(s)
        w = 16 + len(s) * (8.2 if s.isascii() else 14)
        box(xx, y, w, 32, LIGHT.get(c, '#eceff1'), c, 1.2, 8)
        T(xx + w / 2, y + 21, s, 13, 600, INK, mono=True)
        xx += w + 6
toks(my + 42, [('[CLS]', SLT), ('철곡 ㄱㄱ', GRN), ('[SEP]', SLT), ('상태·QED', PUR), ('[SEP]', SLT)])
toks(my + 84, [('[MASK]라벨×n', ORG), ('[SEP]', SLT), ('문항:[MASK]보기…', BLU), ('[SEP]', SLT)])
arrow(604, my + 66, 636, my + 66)
box(640, my, 300, 138, BLU, BLU, 0, 14)
U('brain', 656, my + 14, 44, '#fff')
T(712, my + 46, 'mmBERT 22층', 20, 800, '#fff', 'start')
T(790, my + 82, '312M → 139M (어휘 가지치기)', 14, 500, '#e3edfb')
T(790, my + 108, 'bf16 · 턴 p50 17.8ms', 14, 500, '#e3edfb')
arrow(944, my + 66, 976, my + 66)
heads = [('보기 점수', 'act·type·prio·방법'), ('구간 추출', '대상·개수·좌표 7종'), ('아이템 링크', '1,628개 · ColBERT'), ('짝', '개수 ↔ 대상'), ('가치', '예상 시간·성공률')]
for j, (t, s) in enumerate(heads):
    hx, hy = 980 + (j % 2) * 292, my + (j // 2) * 46
    box(hx, hy, 284, 40, '#fff', BLU, 1.5, 10)
    T(hx + 14, hy + 26, t, 15, 800, BLU, 'start'); T(hx + 270, hy + 26, s, 13, 400, INK, 'end')

# ── 벤치 띠
by3 = 1672
T(40, by3 - 8, 'vs LAYA base (판단만 교체)', 14, 700, SUB, 'start')
for j, (s, c) in enumerate([('실발화 의도 94.5% (11.0%)', GRN), ('대상 아이템 87.3% (6.2%)', GRN), ('생존 우선순위 86.6% (11.5%)', GRN), ('인게임 13/14 (0/14)', BLU), ('/turn 57ms (181ms)', ORG)]):
    pill(260 + j * 262, by3 - 30, 254, 34, c, s, 14.5)
a('</svg>')
(R / ('docs/miya_infographic.en.svg' if EN_MODE else 'docs/miya_infographic.svg')).write_text('\n'.join(o))
print('ok')
