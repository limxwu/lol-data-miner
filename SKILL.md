---
name: lol-data-miner
description: "Mine League of Legends patch data (ARAM Mayhem / 海克斯大乱斗, Arena / 斗魂竞技场, ARAM, SR) from authoritative sources and turn it into grounded meta analysis. Use when asked about LoL patch notes, augment / 强化符文 / 海克斯 tiers, champion tiers, item prices in a mode, champion counters or builds, or 'which augment should I pick' — i.e. whenever an answer must be accurate for the CURRENT patch instead of from model memory. Also use to refresh stale LoL data after a patch. Triggers — 海克斯大乱斗, 斗魂竞技场, 极地大乱斗, 强化符文, 符文推荐, 英雄梯队, 出装, 克制, 版本公告, ARAM Mayhem, Arena, augment tier list, patch meta."
---

# LoL Patch Data Miner

One command pulls the current patch; two more answer champion questions. Pull first, answer second —
model knowledge of a live patch is always stale.

## Step 0 — locate the scripts (once per session)

**Never call these scripts with a relative path**: the session's working directory is not the skill
directory, and `python scripts/lolmeta.py` fails with `can't open file`.

```bash
ls -d "$HOME/.agents/skills/lol-data-miner" 2>/dev/null \
  || ls -d .claude/skills/lol-data-miner 2>/dev/null \
  || ls -d .agents/skills/lol-data-miner 2>/dev/null
```

Use whatever it prints as `<SKILL>` below (global installs normally land in `~/.agents/skills/lol-data-miner`).

- Git Bash / macOS / Linux: `python "$HOME/.agents/skills/lol-data-miner/scripts/lolmeta.py" …`
- Windows shells: `python "C:/Users/<you>/.agents/skills/lol-data-miner/scripts/lolmeta.py" …`

## Step 1 — one command gets everything

```bash
python "<SKILL>/scripts/lolmeta.py" refresh
```

Prints the patch (e.g. `26.18` / Data Dragon `16.18.1`), augment roster counts, item counts, the tier
distribution and the top augments by performance, then tells you the next command. Takes ~6 s cold,
~0.2 s from cache (15 min TTL; `--cache-ttl` / `--force` to control). Output JSON lands in `<SKILL>/out/`.

## Step 2 — answer the question

| Need | Command |
|---|---|
| Augments for one champion | `… lolmeta.py invert --champion 提莫` |
| Full tier list + both augment rankings | `… lolmeta.py report` |
| What changed this patch | `… lolmeta.py notes 37096116` (static page id) |
| Mode item ids and prices | `… lolmeta.py items` |
| Roster + rarity per mode | `… lolmeta.py lists` |
| Champion tier list only | `… lolmeta.py champions` |

`invert` accepts the champion's name (`提莫`), their title (`迅捷斥候`) or the English key (`teemo`) —
all three resolve. Community-only nicknames (`女枪`, `VN`) do not; the error says so and tells you what works.

Other modes: add `--mode arena` / `--mode aram` / `--mode aram-mayhem-classic`. Other locales: `--locale en`.

## Step 3 — only now open a reference

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
