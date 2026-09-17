---
name: lol-data-miner
description: "Mine League of Legends patch data (ARAM Mayhem / 海克斯大乱斗, Arena / 斗魂竞技场, ARAM, SR) from authoritative sources and turn it into grounded meta analysis. Use when asked about LoL patch notes, augment / 强化符文 / 海克斯 tiers, champion tiers, item prices in a mode, champion counters or builds, or 'which augment should I pick' — i.e. whenever an answer must be accurate for the CURRENT patch instead of from model memory. Also use to refresh stale LoL data after a patch. Triggers — 海克斯大乱斗, 斗魂竞技场, 极地大乱斗, 强化符文, 符文推荐, 英雄梯队, 出装, 克制, 版本公告, ARAM Mayhem, Arena, augment tier list, patch meta."
---

# LoL Patch Data Miner

One command pulls the current patch; two more answer champion questions. Pull first, answer second —
model knowledge of a live patch is always stale.

## Step 0 — two path traps to avoid

- **Never call the script by relative path.** `python scripts/lolmeta.py` dies with `can't open file` —
  the session's working directory is not the skill directory.
- **Never rely on `$HOME`.** On Windows Git Bash it is frequently empty (verified: `HOME=` while
  `~` and `$USERPROFILE` both resolve). Use `~` / `$USERPROFILE`, or your own file tools.

## Step 1 — pull the patch (one shell call)

Copy this as-is: the first line resolves the skill directory, the second pulls everything.

```bash
S=$(ls -d ~/.agents/skills/lol-data-miner 2>/dev/null \
    || ls -d "$USERPROFILE"/.agents/skills/lol-data-miner 2>/dev/null \
    || ls -d .claude/skills/lol-data-miner 2>/dev/null)
python "$S/scripts/lolmeta.py" refresh
```

If `python` is not on PATH, use `py` (Windows) or `python3` (Unix). If `$S` comes back empty, locate the
skill with your own file tools (glob for `**/.agents/skills/lol-data-miner/scripts/lolmeta.py`) and pass
that absolute path instead.

`refresh` prints the patch (e.g. `26.18` / Data Dragon `16.18.1`), augment roster counts, item counts, the
tier distribution and the top augments by performance, then names the next command. ~2.5 s cold, ~0.2 s
from cache. op.gg and the client roster are fetched **concurrently**; the 680 KB item table is skipped by
default (CommunityDragon serves it at 11–90 KB/s from CN — 18 s / 8 s / timeout on three measured tries).

## Step 2 — answer the question

| Need | Command |
|---|---|
| Everything for one champion (patch + tier + augments) | `python "$S/scripts/lolmeta.py" brief --champion 提莫` |
| Augments for one champion | `python "$S/scripts/lolmeta.py" invert --champion 提莫` |
| Full tier list + both augment rankings | `python "$S/scripts/lolmeta.py" report` |
| What changed this patch | `python "$S/scripts/lolmeta.py" notes 37096116` (static page id) |
| Mode item ids and prices | `python "$S/scripts/lolmeta.py" items` |
| Roster + rarity per mode | `python "$S/scripts/lolmeta.py" lists` |
| Champion tier list only | `python "$S/scripts/lolmeta.py" champions` |

`brief`/`invert` accept the champion's name (`提莫`), their title (`迅捷斥候`) or the English key
(`teemo`) — all three resolve. Community-only nicknames (`女枪`, `VN`) do not; the error says what works.

Other modes: add `--mode arena` / `--mode aram` / `--mode aram-mayhem-classic`. Other locales: `--locale en`.
Item prices live behind `items`; if it fails, retry or `--force` — the roster and tier data are unaffected.

## Step 3 — fuse external guides (search the web, then verify it)

The data tells you *what is strong*; guides and videos tell you *how people actually play it* — build
orders, combo lines, engage timing, comp archetypes the tier list cannot express. So search for them:

```
web_search "海克斯大乱斗 <champion> 攻略 <patch>"      # or: ARAM Mayhem <champion> guide
web_search "海克斯大乱斗 套路 流派 出装思路"
```

**Then verify every name before you repeat it.** Guides mix up modes and invent augment names; this is
measured, not hypothetical. Patch 26.18 sample from real search results:

| Named in guides found by search | Client roster says |
|---|---|
| 自我毁灭 / 最终都市列车 / 毁坏仪式 / 物法双修 / 心之钢 / 盾魔转 | not in KIWI at all |
| 小丑学院 / 俯冲轰炸 / 钢化你心 / 会心治疗 / 超强大脑 / 珠光护手 | real |

```bash
python "$S/scripts/lolmeta.py" verify 自我毁灭 小丑学院 最终都市列车    # --with-items to include items
```

`verify` reports three outcomes: `ok` (exists in this mode), `MISLEAD` (real, but in a *different* mode —
usually Arena, so the guide is describing another mode), `NOT FOUND` (with closest real names suggested).
**Rule: never repeat a name that fails.** Restate the *pattern* ("stack-on-kill augments", "crit-to-heal"),
not the invented label.

## When to refresh (and when the cache is already correct)

Refresh is governed by *what actually changes*, not by a single timer:

| Data | How often it really changes | Policy in `lolmeta.py` |
|---|---|---|
| Patch number (Data Dragon `versions.json`) | every ~2 weeks | 30 min TTL; it is the invalidation key for everything else |
| Client roster — augment names + rarity (`cherry-augments.json`, `augment-lists.json`) | only on patch day | **keyed by patch**, 12 h fallback — a patch-26.18 pull stays valid all patch |
| Client items — ids + mode prices | only on patch day | **keyed by patch**, pulled only by `items` |
| op.gg tier list + augment performance/pick | recomputed continuously | 15 min TTL **and** patch-stamped: a patch bump invalidates it immediately |
| Official patch notes | never (static page) | cached per docid |

So: **inside one patch, do not re-pull the client data at all** — it is already correct. The only thing
worth re-pulling between games is op.gg's numbers, and only after ~15 minutes.

- Patch changed → everything self-invalidates; just run `refresh`.
- Same patch, want the newest op.gg numbers → `refresh` (15 min TTL) or `--cache-ttl 0`.
- Need item prices → `items` (the one slow call; then patch-cached).
- Stale cache after a network failure → the last good copy is reused and the output says so.

## Step 4 — only now open a reference

`references/` exists to be consulted, not read up front. Open the one you need:
`analysis-playbook.md` for the six-step analysis, `mode-internals.md` for codenames/rarity/pricing,
`data-sources.md` for endpoints and fallbacks.

## When something fails

| Message | Meaning | Do this |
|---|---|---|
| `can't open file …lolmeta.py` | relative path | use the absolute `<SKILL>` path from Step 0 |
| `unknown champion '女枪'` | community nickname, not in client data | retry as `赏金猎人` / title / English key |
| `no augment flagged for X` | op.gg has no data for that champion | use `report` + reason from the kit; say the data is missing |
| `op.gg unavailable` / `without its data payload` | blocked or page layout changed | answer from client data (roster, items, patch notes) and **state the gap** |
| `did not return JSON` | endpoint moved | report it; other subcommands still work |

Exit code 2 with a one-line `error:` means the command failed — do not treat its stdout as data.

## Metric semantics — never blur these

- `performance` — op.gg's own 0–100 impact score. **Not a win rate.**
- `pick` — pick/selection rate (%).
- `tier` — op.gg bucket, 1 = best, 5 = worst.
- Per-augment **win rates do not exist** publicly for these modes. Say so when asked.

## Verified traps (don't rediscover these)

| Trap | Reality |
|---|---|
| "Find op.gg's data API" | There is none for this data — it ships inside the Next.js RSC flight payload. `lolmeta.py` parses it. |
| u.gg / mobalytics / lolalytics | Cloudflare 403. Don't burn turns. |
| `lol.qq.com/news/detail.shtml` | JS shell. Use `gicp/news/410/<id>.html` (GBK) — `notes` does this. |
| Item ids | `22xxxx` / `77xxxx` are mode variants with mode prices; ARAM Mayhem finished items are a flat 2500g. |
| Mode names | 海克斯大乱斗 = ARAM Mayhem = internal `KIWI`; 斗魂竞技场 = Arena = `CHERRY`. |
| Locale formats | op.gg `zh-cn`, CommunityDragon `zh_cn`, Data Dragon `zh_CN`. The script normalizes; don't hand-build URLs. |

## Files

- `scripts/lolmeta.py` — the only entry point (pullers + parsers + cache).
- `references/data-sources.md` — endpoints, parser strategy, fallback ladder.
- `references/mode-internals.md` — codenames, map ids, rarity encoding, item id ranges, patch rules.
- `references/analysis-playbook.md` — six-step analysis + answer template + anti-patterns.

## Maintenance (whoever edits this)

- **Keep the frontmatter `description` quoted.** A bare value containing `: ` fails the skills CLI's YAML
  parse and the whole skill is skipped silently.
- **Verify after every edit**: `npx skills add limxwu/lol-data-miner --list` clones and parses without
  installing. Then reinstall so the local copy is current: `npx skills add limxwu/lol-data-miner -g --yes`.
- **Restart the agent session** after installing — skill registries are scanned at startup.
- **Data drifts inside a patch.** op.gg refreshes continuously; re-pull before quoting numbers.
- **`out/` stays gitignored.** Publish the method, never the snapshot.
