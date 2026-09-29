# 게임 데이터 추출법 (Minecraft 26.1.2)

**한국어** | [English](extract.en.md)

Miya 는 Mojang 게임 데이터(아이템·블럭 이름, 레시피, 드롭, 월드생성 수치)를 **배포하지 않아요**.
아래는 본인이 Mojang 공식 서버에서 jar 를 받아 공식 데이터 생성기로 **직접 로컬에서** 만드는 방법이에요.
실행 전 [Minecraft EULA](https://www.minecraft.net/eula) 를 확인하세요. 결과물(`mcdata/`, `data/mcx.db`, `bot/assets/`)은 재배포하지 마세요.

요구: Java 25+, Python 3, Node(봇 `npm install` 완료 → minecraft-data 포함)

```bash
cd miya && mkdir -p mcdata/lang mcdata/raw && cd mcdata

# 1. 공식 jar·한국어 언어파일 다운로드 (Mojang piston-meta / resources)
python3 - <<'PY'
import json, urllib.request as u
V = "26.1.2"
get = lambda url: json.load(u.urlopen(url))
v = get(next(x["url"] for x in get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")["versions"] if x["id"] == V))
u.urlretrieve(v["downloads"]["server"]["url"], "server.jar")
u.urlretrieve(v["downloads"]["client"]["url"], "client.jar")
h = get(v["assetIndex"]["url"])["objects"]["minecraft/lang/ko_kr.json"]["hash"]
u.urlretrieve(f"https://resources.download.minecraft.net/{h[:2]}/{h}", "lang/ko_kr.json")
PY

# 2. 공식 데이터 생성기 → mcdata/gen (reports + data/minecraft/worldgen …)
java -DbundlerMainClass=net.minecraft.data.Main -jar server.jar --reports --server --output gen

# 3. en_us 언어파일 (클라이언트 jar 안)
python3 -c "import zipfile,shutil; shutil.copyfileobj(zipfile.ZipFile('client.jar').open('assets/minecraft/lang/en_us.json'), open('lang/en_us.json','wb'))"

# 4. 블럭 경도·수확도구, 몹 크기 (minecraft-data, MIT)
cp ../bot/node_modules/minecraft-data/minecraft-data/data/pc/26.1/{blocks,entities}.json raw/

# 5. DB 생성 (표준 라이브러리만)
cd .. && python3 data/build_mc.py && python3 data/build_mcx.py
```

결과: `mcdata/mc.db` (items·blocks·mobs·recipes·tags·loot), `data/mcx.db` (ore_gen·spawn·mine_time·item_value)
검증(26.1.2): items 1506 · blocks 1168 · mobs 89 · recipes 1433 · tags 6346 · loot 1344 / ore_gen 60 · spawn 785 · mine_time 6984

## 선택: 웹 뷰어 텍스처

```bash
python3 -c "import zipfile; z=zipfile.ZipFile('mcdata/client.jar'); [z.extract(n,'bot/assets') for n in z.namelist() if n.startswith('assets/minecraft/')]"
```

## 다른 버전

`V` 와 minecraft-data 폴더(`pc/<버전>`)만 바꾸면 돼요. 몹 체력·공격력은 생성기에 없어 `data/build_mc.py` 의 `MOB` 표(위키 보통 난이도)를 직접 확인하세요.
