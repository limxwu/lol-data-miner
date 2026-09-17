#!/usr/bin/env python3
"""Fetch authoritative League of Legends client data (Data Dragon + CommunityDragon).

Usage:
  python fetch_cdragon.py versions
  python fetch_cdragon.py lists  [--locale zh_cn]
  python fetch_cdragon.py items  [--locale zh_cn]
  python fetch_cdragon.py notes  <lol.qq.com gicp url or bare docid>
  python fetch_cdragon.py augment <key>          # one augment: name, rarity, description

Network: uses the system `curl` (present on Windows 10+/macOS/modern Linux) and falls back to
urllib. Nothing here needs an API key. All endpoints are public and static.
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
DDRAGON = "https://ddragon.leagueoflegends.com"
CDRAGON = "https://raw.communitydragon.org/latest"
GAME_DATA = f"{CDRAGON}/plugins/rcp-be-lol-game-data/global"
OUT = Path("out")

RARITY = {1: "Silver", 4: "Gold", 8: "Prismatic"}


def fetch(url: str, timeout: int = 120) -> bytes:
    """Return raw bytes. Prefers curl (reliable on Windows), falls back to urllib."""
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
    ctx.verify_mode = ssl.CERT_NONE  # public read-only endpoints; local CA stores are often stale
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as res:
        return res.read()


def fetch_json(url: str):
    return json.loads(fetch(url).decode("utf-8", "replace"))


def ddragon_locale(locale: str) -> str:
    """Data Dragon wants zh_CN / ko_KR; CommunityDragon wants zh_cn / ko_kr."""
    parts = locale.replace("-", "_").split("_")
    return f"{parts[0].lower()}_{parts[1].upper()}" if len(parts) == 2 else locale


def decode_text(raw: bytes) -> str:
    """Patch-note pages from lol.qq.com are GBK; most other sources are UTF-8."""
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def html_to_text(html: str) -> str:
    import html as htmllib

    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|td|section)>", "\n", html)
    html = re.sub(r"(?s)<[^>]+>", "", html)
    html = htmllib.unescape(html).replace("\u00a0", " ")
    html = re.sub(r"[ \t\u3000]+", " ", html)
    return re.sub(r"\n\s*\n+", "\n", html).strip()


def write(name: str, obj) -> Path:
    OUT.mkdir(exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def latest_version() -> str:
    return fetch_json(f"{DDRAGON}/api/versions.json")[0]


def cmd_versions(_args) -> None:
    versions = fetch_json(f"{DDRAGON}/api/versions.json")
    latest = versions[0]
    major, minor = latest.split(".")[:2]
    # 2026 season patch 26.N publishes as DDragon 16.N.x
    print(f"latest DDragon version : {latest}")
    print(f"public patch equivalent: 26.{minor}" if major == "16" else f"public patch equivalent: {major}.{minor} (verify mapping)")
    print(f"recent versions        : {', '.join(versions[:5])}")


def cmd_lists(args) -> None:
    locale = args.locale
    version = latest_version()
    lists = fetch_json(f"{GAME_DATA}/{locale}/v1/augment-lists.json")
    roster = fetch_json(f"{GAME_DATA}/{locale}/v1/cherry-augments.json")
    by_id = {a["augmentNameId"]: a for a in roster}

    summary = {"ddragonVersion": version, "locale": locale, "modes": []}
    for entry in lists:
        keys = [p.rsplit("/", 1)[-1] for p in entry["augmentList"]]
        unknown = [k for k in keys if k not in by_id]
        counts: dict[str, int] = {}
        rows = []
        for key in keys:
            meta = by_id.get(key)
            if not meta:
                continue
            counts[meta["rarity"]] = counts.get(meta["rarity"], 0) + 1
            rows.append({"key": key, "name": meta["nameTRA"], "rarity": meta["rarity"]})
        summary["modes"].append({
            "mode": entry["modeName"],
            "total": len(keys),
            "rarity": {k.replace("k", ""): v for k, v in counts.items()},
            "unresolved": unknown,
            "augments": rows,
        })
        print(f"{entry['modeName']:<10} {len(keys):>4} augments  "
              f"({', '.join(f'{k.replace('k','')}={v}' for k, v in counts.items())})"
              + (f"  [{len(unknown)} unresolved]" if unknown else ""))
    path = write(f"augment-lists_{locale}.json", summary)
    print(f"-> {path}")


def cmd_items(args) -> None:
    locale = args.locale
    version = latest_version()
    sr = fetch_json(f"{DDRAGON}/cdn/{version}/data/{ddragon_locale(locale)}/item.json")["data"]
    client = fetch_json(f"{GAME_DATA}/{locale}/v1/items.json")

    mode_variants = [i for i in client if str(i.get("id", "")).startswith("22") and len(str(i["id"])) == 6]
    prismatic = [i for i in client if str(i.get("id", "")).startswith("228")]

    payload = {
        "ddragonVersion": version,
        "locale": locale,
        "srItems": len(sr),
        "modeVariants": [
            {"id": i["id"], "name": i["name"], "price": i["priceTotal"], "inStore": i.get("inStore", True)}
            for i in sorted(mode_variants, key=lambda x: -x["priceTotal"])
        ],
        "prismaticPool": [{"id": i["id"], "name": i["name"], "price": i["priceTotal"]} for i in prismatic],
    }
    path = write(f"items_{locale}.json", payload)
    top = [i for i in payload["modeVariants"] if i["price"] >= 3000]
    print(f"SR items: {len(sr)} | mode variants: {len(mode_variants)} | prismatic pool: {len(prismatic)}")
    for i in top:
        print(f"  {i['name']:<16} id={i['id']} {i['price']}g")
    print(f"-> {path}")


def cmd_notes(args) -> None:
    target = args.target
    if target.isdigit():
        url = f"https://lol.qq.com/gicp/news/410/{target}.html"
    elif "lol.qq.com/news/detail.shtml" in target:
        raise SystemExit("That route is JS-rendered. Use the static form "
                         "https://lol.qq.com/gicp/news/410/<id>.html (or open in a browser).")
    else:
        url = target
    text = html_to_text(decode_text(fetch(url)))
    OUT.mkdir(exist_ok=True)
    path = OUT / (re.sub(r"\W+", "_", url)[-60:] + ".txt")
    path.write_text(text, encoding="utf-8")
    print(text[:3000])
    print(f"\n-> {path} ({len(text)} chars)")


def cmd_augment(args) -> None:
    locale = args.locale
    roster = fetch_json(f"{GAME_DATA}/{locale}/v1/cherry-augments.json")
    key = args.key.lower()
    hits = [a for a in roster if key in a["augmentNameId"].lower() or key in a["nameTRA"].lower()]
    if not hits:
        raise SystemExit(f"no augment matching {args.key!r}")
    for a in hits[:20]:
        print(f"{a['nameTRA']:<18} [{a['rarity'].replace('k','')}] key={a['augmentNameId']} id={a['id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("versions", help="latest Data Dragon version + patch mapping").set_defaults(func=cmd_versions)

    for name, fn in (("lists", cmd_lists), ("items", cmd_items), ("augment", cmd_augment)):
        p = sub.add_parser(name)
        p.add_argument("--locale", default="zh_cn", help="zh_cn | default (en)")
        p.set_defaults(func=fn)
    sub.choices["augment"].add_argument("key", help="augment key or localized name fragment")

    p_notes = sub.add_parser("notes", help="official CN patch notes -> text")
    p_notes.add_argument("target", help="docid (digits) or full URL")
    p_notes.set_defaults(func=cmd_notes)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
