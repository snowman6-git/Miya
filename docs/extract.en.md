# Extracting game data (Minecraft 26.1.2)

[한국어](extract.md) | **English**

Miya does **not distribute** any Mojang game data (item and block names, recipes, drops, worldgen numbers).
Build it **locally yourself**: download the jars from Mojang's official servers and run the official data generator, as shown below.
Read the [Minecraft EULA](https://www.minecraft.net/eula) first. Do not redistribute the outputs (`mcdata/`, `data/mcx.db`, `bot/assets/`).

Requirements:

- Java 25+
- Python 3
- Node, with `npm install` already run in `bot/` (this provides minecraft-data)

```bash
cd miya && mkdir -p mcdata/lang mcdata/raw && cd mcdata

# 1. Official jars + Korean language file (Mojang piston-meta / resources)
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

# 2. Official data generator → mcdata/gen (reports + data/minecraft/worldgen …)
java -DbundlerMainClass=net.minecraft.data.Main -jar server.jar --reports --server --output gen

# 3. en_us language file (inside the client jar)
python3 -c "import zipfile,shutil; shutil.copyfileobj(zipfile.ZipFile('client.jar').open('assets/minecraft/lang/en_us.json'), open('lang/en_us.json','wb'))"

# 4. Block hardness and harvest tools, mob sizes (minecraft-data, MIT)
cp ../bot/node_modules/minecraft-data/minecraft-data/data/pc/26.1/{blocks,entities}.json raw/

# 5. Build the DBs (stdlib only)
cd .. && python3 data/build_mc.py && python3 data/build_mcx.py
```

Outputs:

- `mcdata/mc.db` (items, blocks, mobs, recipes, tags, loot)
- `data/mcx.db` (ore_gen, spawn, mine_time, item_value)

Verified row counts for 26.1.2:

| DB | Table counts |
|---|---|
| `mc.db` | items 1506 · blocks 1168 · mobs 89 · recipes 1433 · tags 6346 · loot 1344 |
| `mcx.db` | ore_gen 60 · spawn 785 · mine_time 6984 |

## Optional: web viewer textures

```bash
python3 -c "import zipfile; z=zipfile.ZipFile('mcdata/client.jar'); [z.extract(n,'bot/assets') for n in z.namelist() if n.startswith('assets/minecraft/')]"
```

## Other versions

For another version, change `V` and the minecraft-data folder (`pc/<version>`).
The data generator doesn't include mob HP and damage. Check the `MOB` table in `data/build_mc.py` yourself; its values come from the wiki's Normal difficulty.
