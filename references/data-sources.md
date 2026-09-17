# Data sources, parsers, fallbacks

Everything here was verified against live endpoints. Endpoint shapes change; the **parser strategies**
are the durable part.

## 1. Data Dragon (official static assets)

| What | URL |
|---|---|
| Latest versions | `https://ddragon.leagueoflegends.com/api/versions.json` |
| Items (localized) | `https://ddragon.leagueoflegends.com/cdn/<ver>/data/<locale>/item.json` (`en_US`, `zh_CN`) |
| Champions | `https://ddragon.leagueoflegends.com/cdn/<ver>/data/<locale>/champion.json` |

**Version ↔ patch mapping**: 2026 season patch `26.N` ships as DDragon `16.N.x`. So `16.18.1` = patch `26.18`
(2026-09-10). Always report both numbers.

Item JSON is *Summoner's Rift only*. Mode-specific prices (ARAM Mayhem's flat 2500g finished items) do
**not** appear here — take those from CommunityDragon (below).

## 2. CommunityDragon (client data mirror — authoritative for IDs, rarity, prices)

Base: `https://raw.communitydragon.org/latest/`

| What | Path |
|---|---|
| Mode → map | `plugins/rcp-be-lol-game-data/global/default/v1/game-mode-mutators.json` |
| Augment ids per mode | `plugins/rcp-be-lol-game-data/global/{default,zh_cn}/v1/augment-lists.json` |
| **All augments + rarity** | `plugins/rcp-be-lol-game-data/global/{default,zh_cn}/v1/cherry-augments.json` |
| Items incl. mode variants | `plugins/rcp-be-lol-game-data/global/{default,zh_cn}/v1/items.json` |
| Jade-mode items | `.../v1/jade-items.json` |
| Arena augment details | `cdragon/arena/{en_us,zh_cn}.json` (desc, `dataValues`, `MaxLevel`) |

Key facts:
- `augment-lists.json` is a list of `{modeName, augmentList[]}`. Augment entries are asset paths like
  `Maps/ModeSpecificData/Augments/ARAM_GetExcited`; join them to `cherry-augments.json` via `augmentNameId`.
- `cherry-augments.json` is the **full roster (552 entries)** with `rarity` = `kSilver | kGold | kPrismatic`.
  It is the single source of truth for "does this augment exist and at what rarity".
- `items.json` mixes SR items (4-digit ids) with mode variants (`22xxxx` = ARAM Mayhem, `77xxxx` = Jade).
  `228xxx` is the prismatic item pool. Static server-side rendered; curl works.
- Directory listings are browsable HTML (`raw.communitydragon.org/latest/cdragon/`), useful for discovery.
- Dead path: `plugins/rcp-be-lol-game-data/global/default/v1/augments.json` → 404. Don't use it.

## 3. op.gg (tier list + augment stats)

Page: `https://op.gg/<locale>/lol/modes/<mode>` (`aram-mayhem`, `aram`, `arena`, `aram-mayhem-classic`).

**Critical**: the page performs **no XHR** for this data. It is embedded in the Next.js RSC flight payload:

```python
chunks = re.findall(r'self\.__next_f\.push\((\[.*?\])\)\s*</script>', html, re.S)
payload = "".join(json.loads(c)[1] for c in chunks if json.loads(c)[1].__class__ is str)
```

Then extract objects with balanced-brace scanning (nested `champion_ids` breaks naive regex):

- Champion tier entries: `{"key":…,"name":…,"image_url":…,"champion_id":N,"id":N,"tier":N,"rank":N}` — `tier 1` is best, `5` worst.
- Augment entries: `{"id":N,"tier":N,"performance":F,"popular":F,"champion_ids":[…],"name":…,"key":…,"rarity":N,…}`.
  - `rarity`: **1 = Silver, 4 = Gold, 8 = Prismatic**.
  - `performance` = op.gg's own 0–100 score. **Not a win rate.** `popular` = pick rate %.
  - `champion_ids` = the best-fit champions for that augment → invert it to answer "which augments for champion X".

Fetching rules that matter:
- Use system `curl --compressed` with a desktop User-Agent. Headless browser requests to deep routes
  occasionally get 403; the tier-list route renders fine.
- Page is ~2 MB uncompressed; allow a generous timeout.
- `/modes/<mode>/<champ>/build` and `/modes/<mode>/<champ>/counters` do **not** expose per-champion data
  (counters redirects to the tier list). Do not promise per-champion mode builds from op.gg.
- Champion counters/synergies **do** exist, but only for SR: `op.gg/zh-cn/lol/champions/<champ>/counters`
  renders client-side, so read it with a real browser and extract the rendered text.

## 4. Official patch notes (CN)

| Route | Works? |
|---|---|
| `https://lol.qq.com/gicp/news/410/<id>.html` | ✅ static HTML, **GBK encoded** — curl + `decode("gbk")` |
| `https://lol.qq.com/news/detail.shtml?docid=<docid>` | ❌ JS shell only — needs a browser |
| `https://apps.game.qq.com/cmc/zmMcnContentInfo?...` | ❌ returns `{"status":0,"msg":"type invalid"}` |

HTML → text: drop `<script>/<style>`, `<br>`→newline, block tags→newline, strip tags, `html.unescape`,
collapse blank lines. That recovers patch-note bodies, augment pool edits and bug-fix lists verbatim.

## 5. Fallback ladder

1. op.gg (tier list + augment performance/pick) — richest, but third-party and rate-limited.
2. CommunityDragon client data (augment roster/rarity, item ids/prices) — authoritative, always available.
3. Official patch notes — authoritative for *changes this patch* (pool edits, exclusions, bug fixes).
4. If op.gg is unavailable: deliver 2 + 3 and **state explicitly** that tier/performance data is missing.
   Never fill the gap with recalled numbers.

## 6. Compliance

- Publish the **method**, never a scraped data snapshot: third-party numbers belong to their sites and go stale.
- Keep requests minimal; `lolmeta.py` caches every response on disk (15 min default) so repeated analysis
  costs no extra requests to anyone.
- Game data is Riot's; this tool only reads public endpoints.
