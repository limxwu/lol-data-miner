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

One entry point, called by absolute path from any working directory:

```bash
# everything, one command: patch, roster, items, tier list, augment stats
python "<skill>/scripts/lolmeta.py" refresh

# then answer the actual question
python "<skill>/scripts/lolmeta.py" invert --champion 提莫      # augments for one champion
python "<skill>/scripts/lolmeta.py" report                     # full tier list + both rankings
python "<skill>/scripts/lolmeta.py" notes 37096116             # official CN patch notes -> text
python "<skill>/scripts/lolmeta.py" items                      # item ids + mode prices
python "<skill>/scripts/lolmeta.py" lists                      # augment roster + rarity per mode
```

`invert` resolves the champion name (`提莫`), their title (`迅捷斥候`) or the English key (`teemo`).
Other modes: `--mode arena|aram|aram-mayhem-classic`. Cold `refresh` takes ~6 s, cached repeats ~0.2 s.

Requirements: Python 3.10+ and the system `curl` (present on Windows 10+). No API keys, no pip installs —
standard library only.

## Installing

```bash
npx skills add limxwu/lol-data-miner           # project-local
npx skills add limxwu/lol-data-miner -g --yes  # global (~/.agents/skills, symlinked into agent dirs)
npx skills add limxwu/lol-data-miner --list    # clone + parse without installing
```

Two things worth knowing:

- **Restart your agent session afterwards.** Skill registries are scanned at startup; a freshly installed
  skill does not appear until the process restarts.
- **`--list` is the fastest sanity check** — it clones the repo and parses the frontmatter without
  installing, which catches a broken `description` before anyone else hits it.

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
stale within a patch. Responses are cached on disk (15 min default), so repeated analysis costs no extra
requests to anyone.

Not endorsed by or affiliated with Riot Games. League of Legends is a trademark of Riot Games, Inc.

## License

MIT — see [LICENSE](LICENSE).
