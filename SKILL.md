---
name: lol-data-miner
description: "Mine League of Legends patch data (ARAM Mayhem / 海克斯大乱斗, Arena / 斗魂竞技场, ARAM, SR) from authoritative sources and turn it into grounded meta analysis. Use when asked about LoL patch notes, augment / 强化符文 / 海克斯 tiers, champion tiers, item prices in a mode, champion counters or builds, or 'which augment should I pick' — i.e. whenever an answer must be accurate for the CURRENT patch instead of from model memory. Also use to refresh stale LoL data after a patch. Triggers — 海克斯大乱斗, 斗魂竞技场, 极地大乱斗, 强化符文, 符文推荐, 英雄梯队, 出装, 克制, 版本公告, ARAM Mayhem, Arena, augment tier list, patch meta."
---

# LoL Patch Data Miner

Turns "what's strong this patch" into reproducible JSON + a six-step analysis, instead of recalled
(and usually stale) model knowledge. Two hard rules:

1. **Never answer from memory about a patch.** Model knowledge is always behind. Pull, then answer.
2. **Never quote a metric you did not read.** If a number is missing, say it is missing.

## Workflow

### Step 1 — Establish the patch (mandatory, do this first)
```bash
python scripts/fetch_cdragon.py versions      # DDragon latest, e.g. 16.18.1
```
Map DDragon → public patch: **2026 season "26.N" is published as DDragon `16.N.x`** (26.18 → 16.18.1).
State both in every answer. If the client data and the public patch disagree, the pull is stale — redo it.

### Step 2 — Pull mode meta (tier list + augment stats)
```bash
python scripts/fetch_opgg.py champions --mode aram-mayhem     # champion tier list, ranked
python scripts/fetch_opgg.py augments  --mode aram-mayhem     # augment performance / pick rate / best champions
python scripts/fetch_opgg.py champions --mode arena           # other modes use the same script
```
Writes `out/opgg_<mode>_champions.json` and `out/opgg_<mode>_augments.json`.

### Step 3 — Pull authoritative client data (never guess IDs, prices, or rarity)
```bash
python scripts/fetch_cdragon.py lists                         # augment ids per mode + rarity (Silver/Gold/Prismatic)
python scripts/fetch_cdragon.py items                         # item ids, localized names, prices (incl. mode variants)
python scripts/fetch_cdragon.py notes <url-or-docid>          # official patch note text (handles GBK)
```

### Step 4 — Analyze
Follow `references/analysis-playbook.md` (tier → augment stats → augment↔champion inversion → items →
counters → comms). Cite the patch and the source for every number.

## Trap table (all verified on this machine)

| Symptom | Truth |
|---|---|
| Can't find op.gg's data API | The page issues **no XHR** for this data — it ships in the Next.js RSC flight payload (`self.__next_f.push([1,"..."])`). `scripts/fetch_opgg.py` already parses it. |
| u.gg / mobalytics / lolalytics / leagueofgraphs return 403 | Cloudflare bot wall, verified. Do not burn turns on them. |
| `performance` looks like a win rate | It is op.gg's own 0–100 **performance score**, not a win rate. `popular` is pick rate. Label them correctly. |
| A guide claims "augment X win rate = NN%" | Riot does not expose per-augment win rates for ARAM Mayhem; third parties don't have them either. Treat that claim as unverifiable. |
| `lol.qq.com/news/detail.shtml?docid=…` fetches an empty shell | JS-rendered. Use the static news route `lol.qq.com/gicp/news/410/<id>.html` (curl + decode) or open it in a browser. |
| Patch notes come back as mojibake | Those pages are **GBK**, not UTF-8. `bytes.decode("gbk")`. |
| Mode names don't match between sources | CN "海克斯大乱斗" = global **ARAM Mayhem** = internal **KIWI**; 斗魂竞技场 = **CHERRY**; `KIWI_JADE` is a variant with its own item pool. See `references/mode-internals.md`. |
| Item IDs look duplicated | `22xxxx`/`77xxxx` are **mode variants** of standard items (different prices). `228xxx` is the prismatic item pool. Mode finished-item price is a flat 2500g — do not quote SR prices for mode answers. |

## Output contract

Every analysis answer states: **patch** (26.18 / 16.18.1), **source per number** (op.gg / client data /
official notes), and **metric semantics** (performance vs win rate vs pick rate). When a data source is
blocked or a metric is unavailable, say so explicitly instead of substituting a guess.

## Files

- `references/data-sources.md` — every endpoint, parser and fallback path.
- `references/mode-internals.md` — mode codenames, map IDs, rarity encoding, item ID ranges, CN↔global names.
- `references/analysis-playbook.md` — the six-step analysis + answer templates.
- `scripts/fetch_opgg.py`, `scripts/fetch_cdragon.py` — the pullers (stdlib + system `curl`).

## Maintenance (whoever edits this file)

- **Keep the frontmatter `description` quoted.** A bare value containing `: ` (e.g. `Triggers: …`) fails the
  skills CLI's YAML parse and the skill is skipped silently — verified the hard way.
- **Verify after every edit**: `npx skills add limxwu/lol-data-miner --list` clones and parses without
  installing. It is the fastest way to catch broken frontmatter or a moved `SKILL.md`.
- **Data drifts inside a patch.** op.gg refreshes continuously, so two pulls minutes apart differ in the
  decimals and can shift marginal tier buckets. Re-pull before quoting numbers.
- **Restart the agent session after installing.** Skill registries are scanned at startup, so a freshly
  installed skill is not visible in `skill://` until the session (process) restarts.
- **`out/` stays gitignored.** Publish the method, never the snapshot.
