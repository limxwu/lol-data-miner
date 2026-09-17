# Analysis playbook — six steps from raw pull to match advice

The point of this file is that every answer is *derived from a fresh pull*, not recalled. Follow the order.

## Step 0 — State the frame before any advice

Open with: patch (`26.18` / `16.18.1`), mode, and where every number comes from. If a metric is
unavailable, say so instead of substituting a plausible number.

Metric vocabulary — never blur these:
- **performance** (op.gg, 0–100): their own impact score.
- **pick rate** (`popular`): how often offered/chosen.
- **tier** (1–5): op.gg tier bucket; 1 = best.
- **win rate**: **not available** for ARAM Mayhem augments. Say that when asked.

## Step 1 — Locate the champion

From `op_<mode>_champions.json`, report rank and tier. Report it even when it is unflattering —
a T5 champion needs a "how to play from behind" plan, not flattery. Equal-tier clusters tell you the
mode's axis (e.g. when T1 is all ranged mages/crit ADCs, that *is* the meta statement).

## Step 2 — Augments: two rankings, not one

- **By performance** → what changes a game most (often low pick rate = rarely offered).
- **By pick rate** → what you will realistically be offered; shows the practical "consensus" picks.
Give both. A single ranked list hides the rare-but-broken augments.

Filter by rarity (Silver / Gold / Prismatic) so the advice maps to the actual roll slots.

## Step 3 — Invert augment↔champion to answer "what do I take on X?"

`augment.champion_ids` lists the best-fit champions per augment. Invert it once:

```python
inv = defaultdict(list)
for a in augments:
    for c in a["champion_names"]:
        inv[c].append((a["performance"], a["name"], a["rarity"]))
```

Then present the champion's top augments sorted by performance. **This is the highest-value output of
the whole pipeline** — it is champion-specific, patch-current, and data-backed.

## Step 4 — Apply the patch's pool rules (the time-saver)

Before recommending anything, subtract what the champion **cannot be offered**. Read the current patch
notes (Step 3 of the workflow) for: exclusion pools, per-champion filters, and pool removals. Telling a
player "don't wait for 珠光护手, it was removed from your pool in 26.18" is worth more than another tier list.

Also flag **poison picks**: augments that exist for the champion but convert away their damage type
(e.g. physical→magic on a pen/AD-crit build). Data shows they are offered; mechanism says they are a trap.

## Step 5 — Items from mode economics

Use mode prices (`references/mode-internals.md`), never SR prices. Give an **order**, not a shopping list:
first three finished items, then the flex slot, then the 6000g/9000g tier. Attach each pick to a reason
(target archetype, counter need, or augment synergy).

Counter map for ARAM Mayhem (all purchasable at mode prices):

| Enemy pattern | Answer |
|---|---|
| Healing/shielding/lifesteal stacks | Grievous Wounds items (炼金科技纯化器 / 凡性的提醒 / 荆棘之甲 / 莫雷洛秘典 / 炼金朋克链锯剑) |
| Crit ADCs | 兰顿之兆 / 荆棘之甲 / 冰霜之心 |
| AP burst | 败魔 / 玛莫提乌斯之噬 / 女妖面纱 + 适应性头盔 (6000g) |
| Dive assassins | 中娅沙漏 / 守护天使 / hard CC |
| Immortal front line | 巨人杀手-style augments, 穿针引线 (18% pen), 多米尼克领主的致意, 黑曜切割者 |

## Step 6 — Counters, positioning, comms

- **Counters**: in this mode range and engage > champion-vs-champion stats. Explain *why* (who can reach
  whom, who interrupts the channel, who out-sustains). For SR counters with real win rates, read the
  champion's counters page in a browser — but say which mode the numbers come from.
- **When focus-fired**: name the concrete chain — cleanse/water-cleanser the CC → reposition → re-enter
  after key cooldowns. Tie it to the champion's own tool (stealth, dash, untargetable frames).
- **Comms**: hand the player paste-ready lines, not advice about communicating. Cover: pre-fight role
  statement, explicit asks when focused, and cooldown callouts ("my cleanse is down, don't let them hook").
  In this mode the highest-value callout is always *"my defensive cooldown is down"*.

## Answer template

```
**Frame** — patch 26.18 (16.18.1) · mode · sources
**Where you stand** — tier/rank, honest read of the matchup
**Augments** — top by performance (champion-specific) + patch pool exclusions + poison picks
**Items** — ordered build with reasons, mode prices
**Play** — positioning, engage timing, the defensive chain
**Comms** — paste-ready lines
**Next** — what to report back (enemy comp, roll options) for a sharper call
```

## Anti-patterns (each one bit us)

1. Quoting `performance` as a win rate.
2. Answering with SR item prices in a mode where everything is 2500g.
3. Hardcoding last patch's conclusions — tier lists and pool rules change every patch.
4. Recommending an augment that the patch removed from the champion's pool.
5. Treating a low pick rate as low value (often the opposite: rare = strong).
6. Trusting an LLM-written summary of a guide site. Read the primary source; summaries invent numbers.
