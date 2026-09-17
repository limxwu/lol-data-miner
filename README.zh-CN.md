# lol-data-miner · 中文说明

[English](README.md) | **简体中文**

一个 agent skill：**抓取当前补丁**的英雄联盟数据（英雄梯队、强化符文强度、装备价格、官方公告原文），
再据此做有据可查的对局分析——而不是靠模型记忆里那份过期的印象。

面向海克斯大乱斗（ARAM Mayhem）、斗魂竞技场（Arena）、极地大乱斗。命令行界面全中文，数据同样是中文。

```bash
npx skills add limxwu/lol-data-miner
```

## 为什么需要它

问模型"这版本什么强"，它会给你一个自信但**落后几个版本**的答案；问到强化符文，基本开始编。
问题不在提示词，而在于**没人去拉当前数据**。这个 skill 把它变成可复现的四步：

1. **定版本** —— Data Dragon 最新版本号，映射到公开补丁号（2026 赛季：`16.18.1` = 补丁 `26.18`）。
2. **拉模式数据** —— op.gg 的英雄梯队与强化符文表现分／选取率。
3. **拉客户端权威数据** —— 符文全量清单与稀有度、装备 ID 与模式内价格（CommunityDragon 是客户端镜像）。
4. **分析** —— 六步法：梯队 → 符文 → 符文↔英雄反查 → 装备 → 克制 → 沟通。

全部来自公开、免密钥的接口。

## 用法

唯一入口，用**绝对路径**调用（会话的工作目录不是 skill 目录）：

```bash
# 一条命令拿全量：版本、符文清单、梯队、符文榜
python "<skill>/scripts/lolmeta.py" refresh

# 然后回答具体问题
python "<skill>/scripts/lolmeta.py" brief  --champion 提莫     # 版本+梯队+该英雄符文（一条命令）
python "<skill>/scripts/lolmeta.py" invert --champion 提莫     # 只要符文
python "<skill>/scripts/lolmeta.py" report                     # 完整梯队 + 两套符文榜
python "<skill>/scripts/lolmeta.py" notes 37096116             # 官方公告原文（静态页 id）
python "<skill>/scripts/lolmeta.py" items                      # 装备 ID 与模式内价格
python "<skill>/scripts/lolmeta.py" lists                      # 各模式符文清单与稀有度
```

- `brief` / `invert` 接受三种写法：英雄名（`提莫`）、称号（`迅捷斥候`）、英文 key（`teemo`）。
- 其他模式：`--mode arena|aram|aram-mayhem-classic`。
- 冷启动约 **2.5 秒**，缓存命中约 **0.2 秒**（符文数据 15 分钟 TTL，客户端数据按补丁号长期有效）。

## 什么时候该刷新（其余时候缓存就是对的）

刷新策略按"数据实际多久变一次"设计，不是一刀切计时：

| 数据 | 实际变化频率 | 策略 |
|---|---|---|
| 补丁号（Data Dragon） | 约两周 | 30 分钟 TTL，同时是其他缓存的失效键 |
| 符文清单 + 稀有度（客户端） | 仅补丁更新日 | **按补丁号键控**，12 小时兜底 —— 拉一次管整个补丁 |
| 装备 ID + 模式内价格 | 仅补丁更新日 | **按补丁号键控**，且只在跑 `items` 时才拉 |
| op.gg 梯队 + 符文表现分 | 持续重算 | 15 分钟 TTL **且**打补丁戳，补丁一变立刻失效 |
| 官方公告 | 不变（静态页） | 按 docid 缓存 |

结论：**同一个补丁内不必重复拉客户端数据**，它本来就是对的；唯一值得重拉的是 op.gg 的数值，且约 15 分钟一次。

## 融合攻略：搜得到，但必须先验

数据告诉你"什么强"，攻略告诉你"怎么打"——出装顺序、连招、开团时机，这些不在任何 JSON 里。
所以工作流里明确包含 web_search，但**搜到的每个名字都要过一遍校验**：

```bash
python "<skill>/scripts/lolmeta.py" verify 自我毁灭 小丑学院 最终都市列车
```

`verify` 给三种结论：`ok`（本模式存在）、`MISLEAD`（真实存在但属于**另一个模式**，通常是斗魂竞技场）、
`NOT FOUND`（并给出最接近的真实名字）。

这不是杞人忧天——patch 26.18 实测，某篇"自爆流"攻略提到的 `自我毁灭`、`最终都市列车`、`毁坏仪式`、
`物法双修`、`心之钢`、`盾魔转` 里，**一半在 223 张真实符文里根本不存在**；而 `最终都市列车` 真实存在，
但**只在经典变体模式**里——攻略串模式了。**验证不过的名字绝不复述**，改为描述机制本身。

## 我们已经替你踩过的坑

| 坑 | 真相 |
|---|---|
| "op.gg 的数据总得有个接口吧" | 没有。数据直接内嵌在 Next.js 的 RSC flight 载荷里，不发 XHR。脚本直接解析它 |
| u.gg / mobalytics / lolalytics | Cloudflare 403，别浪费时间 |
| **装备数据老是拉不到** | CommunityDragon（`raw.communitydragon.org`）在国内只有 **11–90 KB/s**，680 KB 的 `items.json` 实测 18 秒 / 8 秒 / 45 秒超时；而 Data Dragon 同一体积只要 **0.4 秒**。所以装备表**默认不拉**，需要时用 `items`，且按补丁号长期缓存 |
| 拿 op.gg 的 `performance` 当胜率 | 那是它自家的 0–100 表现分；`pick` 是选取率。**强化符文的胜率没有公开数据**，谁说有都别信 |
| `lol.qq.com/news/detail.shtml` | JS 空壳。用静态路由 `gicp/news/410/<id>.html`（GBK 编码） |
| 装备 ID 重复 | `22xxxx` / `77xxxx` 是模式内变体（价格不同）；海克斯大乱斗成品装统一 **2500g**，别拿峡谷价格回答 |
| 模式名对不上 | 海克斯大乱斗 = ARAM Mayhem = 内部代号 `KIWI`；斗魂竞技场 = Arena = `CHERRY` |

## 安装

```bash
npx skills add limxwu/lol-data-miner           # 装到当前项目
npx skills add limxwu/lol-data-miner -g --yes  # 全局（~/.agents/skills，并软链到各 agent 目录）
npx skills add limxwu/lol-data-miner --list    # 只克隆并解析，不安装
```

两点值得注意：

- **装完要重启 agent 会话**：skill 注册表在进程启动时扫描，不重启看不到。
- **`--list` 是最快的自检**：克隆并解析 frontmatter，能在别人踩到之前发现 `description` 写坏了。

环境要求：Python 3.10+ 和系统 `curl`（Windows 10+ 自带）。无第三方依赖、无需 API key。

## 数据口径与诚实边界

- 第三方数据（op.gg）与第一方游戏数据分开标注；不是胜率的数字绝不写成胜率。
- 表现分在同一补丁内也会随新对局漂移，引用前重新拉。
- 数据源被墙或改版时，脚本会**明说缺了什么**，并降级到客户端数据，而不是编一个数出来。

## 合规

只发布**方法**，不发布抓取到的数据快照——第三方数字属于对应站点，且在补丁内就会过期。
每个响应都会落盘缓存（默认 15 分钟），重复分析不会给对方站点增加请求。

非 Riot Games 官方产品。League of Legends 是 Riot Games, Inc. 的商标。

## 许可

MIT —— 见 [LICENSE](LICENSE)。
