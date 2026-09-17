# Mode internals — codenames, IDs, encoding

Sourced from client data (`game-mode-mutators.json`, `augment-lists.json`, `cherry-augments.json`,
`items.json`) and official notes, verified 2026-09 (patch 26.18).

## 1. Codename ↔ public name

| Internal | Global name | CN name | Map | Augments in roster |
|---|---|---|---|---|
| `KIWI` | ARAM Mayhem | 海克斯大乱斗 | Howling Abyss (`MapId 12`) | **223** |
| `KIWI_JADE` | variant with its own item pool | 海克斯大乱斗（经典/翡翠变体） | same map | 188 |
| `CHERRY` | Arena | 斗魂竞技场 | Cherry map | 44 listed (225 with details in `cdragon/arena`) |
| `ARAM` | ARAM | 极地大乱斗 | Howling Abyss | none (no augments) |
| Classic | League Classic | 经典模式 | SR | none |

`game-mode-mutators.json` maps `MapId` → map skins; `MapId 12` = Howling Abyss, which is how KIWI is
confirmed as an ARAM-family mode.

## 2. Augment rarity encoding

| Client (`cherry-augments.json`) | op.gg (`rarity`) | Meaning |
|---|---|---|
| `kSilver` | `1` | Silver |
| `kGold` | `4` | Gold |
| `kPrismatic` | `8` | Prismatic |

Patch 26.18 counts: client roster 223 for KIWI (62 Silver / 86 Gold / 75 Prismatic); op.gg carries 229
objects (61 / 88 / 80) because it also lists a few disabled or legacy entries. Prefer the client roster
for "does this exist", op.gg for "how strong is it".

Augment names differ per locale: use `cherry-augments.json` under `zh_cn/` for CN names (`nameTRA`) and
under `default/` for English. Arena augments additionally expose per-level `dataValues` (e.g. an omnivamp
augment at 15% → 25% at level 2) in `cdragon/arena/<locale>.json`.

## 3. Item ID ranges (ARAM Mayhem economy)

| Range | Meaning |
|---|---|
| 4 digits (e.g. `3031`) | Summoner's Rift item |
| `22xxxx` (e.g. `223031` 无尽之刃) | **ARAM Mayhem variant** — same item, mode pricing |
| `77xxxx` (e.g. `773074`) | Jade-variant item pool |
| `228xxx` | Prismatic item pool (obtainable via the 4000g prismatic item) |

**Mode pricing is flat** — do not answer mode questions with SR prices:

| Tier | Price |
|---|---|
| Component / starter | 300–1 300g |
| Finished item | **2500g** (a few at 2750g / 3000g, e.g. 渴血战斧 / 血色之刃) |
| `属性加成`, `锻造器兑换券` | 750g |
| `传说级X装备` (role bundles) | 2250g |
| `碎片之刃`, `棱彩装备` (random prismatic) | 2500g / 4000g |
| Top-tier: 虚空献祭 / 终极九头蛇 / 沃格勒特的巫师帽 / 适应性头盔 | 6000g |
| Iconic: 死亡之刃 / 符文阔剑 | 9000g |

## 4. Roster mechanics worth knowing (from official notes)

- **26.3** — +45 augments, augment *sets* (bonds/羁绊), a battle pass.
- **26.12** — bonds **removed** (official reasons: builds and games became homogeneous, bonds overshadowed
  champions); introduced **skill augments (技能符文)** which supercharge one chosen ability, plus **quest
  augments**. Augments are now pool-filtered per champion.
- **26.18** — pool hygiene pass:
  - new **exclusion pool** (质变类/潘朵拉的盒子/尊我为王) and a **"no AP-ratio" filter** that removes
    AP-conversion augments from 23 pure-AD champions (盖伦/劫/锐雯/泰隆/亚托克斯 …) — do not expect
    `物理转魔法` / `魔法转物理` / `超凡邪力` on those champions;
  - `珠光护手` removed from the four auto-attack pools (ranged/melee × attack/burst);
  - `终极九头蛇` sets items unsellable while held (anti gold-farming fix);
  - `小丑学院` re-enabled; `旋转至胜` ult damage 30% → 50%;
  - per-champion pool exclusions (e.g. `坦克引擎`/`飞身踢` excluded for 瑞兹/莫甘娜/奥莉安娜/卡尔萨斯/兰博).

## 5. Localization trap

CN names in community guides often differ from client `nameTRA`. Always match on the **client key**
(`ARAM_…` / English key), never on a translated string. Example: CN “面包和黄油” = key `ARAM_BreadAndButter`;
CN “旋转至胜” = `ARAM_SpinToWin`.
