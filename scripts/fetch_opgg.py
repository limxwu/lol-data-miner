#!/usr/bin/env python3
"""Pull op.gg mode meta: champion tier list + augment stats (performance / pick rate / best champions).

op.gg renders this data server-side inside the Next.js RSC flight payload and issues **no XHR** for it,
so a plain HTTP fetch plus payload parsing is enough — no browser needed.

Usage:
  python fetch_opgg.py champions --mode aram-mayhem
  python fetch_opgg.py augments  --mode aram-mayhem
  python fetch_opgg.py report    --mode aram-mayhem
  python fetch_opgg.py invert    --champion 盖伦
  python fetch_opgg.py invert    --champion yasuo --mode arena

Modes: aram-mayhem (海克斯大乱斗), aram-mayhem-classic, aram, arena (斗魂竞技场), ranked-solo-duo.

Metrics, do not conflate them:
  performance = op.gg's own 0-100 impact score    (NOT a win rate)
  pick        = pick/selection rate in percent
  tier        = op.gg bucket, 1 = best ... 5 = worst
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
OUT = Path("out")

RARITY = {1: "Silver", 4: "Gold", 8: "Prismatic"}

CHAMPION_RE = re.compile(
    r'\{"key":"(\w+)","name":"([^"]+)","image_url":"[^"]*","champion_id":(\d+),"id":\d+,"tier":(\d+),"rank":(\d+)\}'
)
AUGMENT_START_RE = re.compile(r'\{"id":\d+,"tier":\d+,"performance":[\d.]+,"popular":[\d.]+')


def fetch(url: str, timeout: int = 180) -> bytes:
    try:
        proc = subprocess.run(
            ["curl", "--compressed", "-sS", "-L", "--max-time", str(timeout), "-A", UA, url],
            capture_output=True,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
        if proc.stderr:
            sys.stderr.write(f"curl failed ({proc.returncode}): {proc.stderr[:200]!r}\n")
    except FileNotFoundError:
        pass
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as res:
        return res.read()


def rsc_payload(html: str) -> str:
    """Concatenate the Next.js flight payload. op.gg's data lives here, not in an API call."""
    parts = []
    for chunk in re.findall(r'self\.__next_f\.push\((\[.*?\])\)\s*</script>', html, re.S):
        try:
            arr = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(arr, list) and len(arr) > 1 and isinstance(arr[1], str):
            parts.append(arr[1])
    return "".join(parts)


def scan_objects(payload: str, start_re: re.Pattern[str]) -> list[dict]:
    """Balanced-brace scan from each match start; nested objects (champion_ids) break naive regex."""
    out = []
    for match in start_re.finditer(payload):
        depth, i, in_str, esc = 0, match.start(), False, False
        while i < len(payload):
            ch = payload[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        out.append(json.loads(payload[match.start():i + 1]))
                    except json.JSONDecodeError:
                        pass
                    break
            i += 1
    return out


def page_html(mode: str, locale: str) -> str:
    url = f"https://op.gg/{locale}/lol/modes/{mode}"
    raw = fetch(url)
    html = raw.decode("utf-8", "replace")
    if "__next_f" not in html:
        raise SystemExit(f"no flight payload at {url} — page layout changed or the request was blocked "
                         f"({len(raw)} bytes). Check the mode slug.")
    return html


def write(name: str, obj) -> Path:
    OUT.mkdir(exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def get_champions(mode: str, locale: str) -> list[dict]:
    payload = rsc_payload(page_html(mode, locale))
    seen: dict[int, dict] = {}
    for key, name, cid, tier, rank in CHAMPION_RE.findall(payload):
        seen[int(cid)] = {"key": key, "name": name, "championId": int(cid),
                          "tier": int(tier), "rank": int(rank)}
    return sorted(seen.values(), key=lambda c: c["rank"])


def get_augments(mode: str, locale: str) -> list[dict]:
    payload = rsc_payload(page_html(mode, locale))
    best: dict[int, dict] = {}
    for obj in scan_objects(payload, AUGMENT_START_RE):
        if "aram-augment" not in (obj.get("largeIcon") or ""):
            continue
        if obj["id"] not in best:
            best[obj["id"]] = obj
    rows = []
    for obj in best.values():
        rows.append({
            "name": obj.get("name"),
            "key": obj.get("key"),
            "rarity": RARITY.get(obj.get("rarity"), str(obj.get("rarity"))),
            "performance": obj.get("performance"),
            "pick": obj.get("popular"),
            "desc": re.sub(r"<[^>]+>", "", obj.get("desc", "")),
            "champions": [c["name"] for c in obj.get("champion_ids", [])],
        })
    return sorted(rows, key=lambda a: -(a["performance"] or 0))


def payload_path(mode: str, kind: str) -> Path:
    return OUT / f"opgg_{mode.replace('-', '_')}_{kind}.json"


def cmd_champions(args) -> None:
    rows = get_champions(args.mode, args.locale)
    if not rows:
        raise SystemExit("no champions parsed — op.gg payload shape changed")
    path = write(payload_path(args.mode, "champions").name, rows)
    print(f"{len(rows)} champions | tiers: " +
          ", ".join(f"T{t}={sum(1 for r in rows if r['tier'] == t)}" for t in sorted({r['tier'] for r in rows})))
    for row in rows[:15]:
        print(f"  {row['rank']:>3}. T{row['tier']} {row['name']}")
    print(f"-> {path}")


def cmd_augments(args) -> None:
    rows = get_augments(args.mode, args.locale)
    if not rows:
        raise SystemExit("no augments parsed — op.gg payload shape changed")
    path = write(payload_path(args.mode, "augments").name, rows)
    by_rarity: dict[str, int] = {}
    for row in rows:
        by_rarity[row["rarity"]] = by_rarity.get(row["rarity"], 0) + 1
    print(f"{len(rows)} augments | " + ", ".join(f"{k}={v}" for k, v in by_rarity.items()))
    for row in rows[:12]:
        print(f"  {row['performance']:>6}  pick {row['pick']:>5}%  [{row['rarity']:<9}] {row['name']}")
    print(f"-> {path}")


def cmd_report(args) -> None:
    champ_file = payload_path(args.mode, "champions")
    aug_file = payload_path(args.mode, "augments")
    if not champ_file.exists() or not aug_file.exists():
        raise SystemExit(f"run `champions` and `augments` for {args.mode} first")
    champs = json.loads(champ_file.read_text(encoding="utf-8"))
    augs = json.loads(aug_file.read_text(encoding="utf-8"))

    for tier in sorted({c["tier"] for c in champs}):
        names = [c["name"] for c in champs if c["tier"] == tier]
        print(f"T{tier} ({len(names)}): {'、'.join(names[:25])}{' …' if len(names) > 25 else ''}")
    print("\nTop augments by performance:")
    for row in augs[:10]:
        print(f"  {row['performance']:>6} [{row['rarity']:<9}] {row['name']:<16} pick {row['pick']}%")
    print("\nTop augments by pick rate:")
    for row in sorted(augs, key=lambda a: -(a["pick"] or 0))[:10]:
        print(f"  {row['pick']:>5}% [{row['rarity']:<9}] {row['name']:<16} perf {row['performance']}")


def cmd_invert(args) -> None:
    aug_file = payload_path(args.mode, "augments")
    if not aug_file.exists():
        raise SystemExit(f"run `augments --mode {args.mode}` first")
    augs = json.loads(aug_file.read_text(encoding="utf-8"))
    needle = args.champion.lower()
    hits = [(a["performance"], a) for a in augs if any(needle in c.lower() for c in a["champions"])]
    if not hits:
        raise SystemExit(f"champion {args.champion!r} is not in any augment's best-fit list for {args.mode}")
    for perf, a in sorted(hits, reverse=True):
        print(f"{perf:>6} [{a['rarity']:<9}] {a['name']:<16} pick {a['pick']}%  {a['desc'][:70]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("champions", cmd_champions), ("augments", cmd_augments), ("report", cmd_report)):
        p = sub.add_parser(name)
        p.add_argument("--mode", default="aram-mayhem")
        p.add_argument("--locale", default="zh-cn", help="zh-cn | en | ko ...")
        p.set_defaults(func=fn)
    p_inv = sub.add_parser("invert", help="which augments fit a given champion")
    p_inv.add_argument("--champion", required=True)
    p_inv.add_argument("--mode", default="aram-mayhem")
    p_inv.add_argument("--locale", default="zh-cn")
    p_inv.set_defaults(func=cmd_invert)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
