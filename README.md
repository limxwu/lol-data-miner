# lol-data-miner

An agent skill that mines **current-patch** League of Legends data — champion tiers, augment stats,
item prices, patch-note text — and turns it into grounded match analysis instead of stale model recall.

Built for ARAM Mayhem (海克斯大乱斗), Arena (斗魂竞技场), ARAM and SR-adjacent modes.

```bash
npx skills add limxwu/lol-data-miner
```

## Why this exists

Ask an LLM "what's strong this patch" and you get a confident answer from its training data — which is
months behind, and for augments it is usually just wrong. The fix is not a better prompt; it is a
repeatable pull:

1. **Establish the patch** — Data Dragon's latest version, mapped to the public patch number
   (2026: DDragon `16.18.1` = patch `26.18`).
2. **Pull mode meta** — op.gg's champion tier list and augment performance/pick rates.
3. **Pull authoritative client data** — augment roster + rarity, item IDs and mode prices
   (CommunityDragon mirrors the live client).
4. **Analyze** — six-step playbook: tier → augment stats → augment↔champion inversion → items →
   counters → comms.

Everything is reproducible from public, key-less endpoints.

## Usage

```bash
# 1. patch check (always first)
python scripts/fetch_cdragon.py versions

# 2. mode meta
python scripts/fetch_opgg.py champions --mode aram-mayhem   # tier list -> out/opgg_aram_mayhem_champions.json
python scripts/fetch_opgg.py augments  --mode aram-mayhem   # augment stats -> out/opgg_aram_mayhem_augments.json
python scripts/fetch_opgg.py report    --mode aram-mayhem   # human-readable summary

# 3. "what should I pick on this champion"
python scripts/fetch_opgg.py invert --champion 迅捷斥候

# 4. authoritative client data
python scripts/fetch_cdragon.py lists                       # roster + rarity per mode
python scripts/fetch_cdragon.py items                       # item IDs, localized names, mode prices
python scripts/fetch_cdragon.py notes 37096116              # official CN patch notes -> text
```

Requirements: Python 3.10+ and the system `curl` (present on Windows 10+). No API keys, no pip installs —
standard library only.

## What it knows that is easy to get wrong

| Trap | Reality |
|---|---|
| op.gg must have a data API somewhere | It doesn't issue XHR for this — the data ships in the Next.js RSC flight payload |
| u.gg / mobalytics / lolalytics | Cloudflare 403; don't burn turns there |
| op.gg `performance` | A 0–100 impact score, **not** a win rate (`popular` is pick rate) |
| "augment X has NN% win rate" | Riot does not expose per-augment win rates for ARAM Mayhem; treat such claims as unverifiable |
| `lol.qq.com/news/detail.shtml` | JS shell — use the static `gicp/news/410/<id>.html` route (GBK encoded) |
| Item IDs | `22xxxx`/`77xxxx` are **mode variants** with mode prices; ARAM Mayhem finished items are a flat 2500g |
| Mode names | 海克斯大乱斗 = ARAM Mayhem = internal `KIWI`; 斗魂竞技场 = Arena = `CHERRY` |

Details in [`references/`](references/).

## Scope and honesty

- This reports **third-party** stats (op.gg) alongside first-party game data. The two are labelled
  separately, and neither is presented as a win rate when it isn't one.
- Augment performance scores drift within a patch as new games land; timestamps matter.
- If a source is blocked, the skill says so and degrades to client data rather than inventing numbers.

## Compliance

Publishes the **method**, never a scraped data snapshot — third-party numbers belong to their sites and go
stale within a patch. Requests are minimal and sequential; `--delay` is available for politeness.

Not endorsed by or affiliated with Riot Games. League of Legends is a trademark of Riot Games, Inc.

## License

MIT — see [LICENSE](LICENSE).
