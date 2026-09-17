#!/usr/bin/env python3
"""lolmeta — current-patch League of Legends meta, from public endpoints, in one command.

Call it with an absolute path from ANY working directory:

    python <skill-dir>/scripts/lolmeta.py refresh                 # everything, one shot
    python <skill-dir>/scripts/lolmeta.py invert --champion 提莫   # augment picks for a champion
    python <skill-dir>/scripts/lolmeta.py notes 37096116          # official CN patch notes -> text

Subcommands
    refresh                     versions + op.gg meta + client roster/items, then a summary
    meta                        op.gg champion tier list + augment stats (one page fetch)
    champions | augments        read the meta pull from disk (auto-pulls when missing/stale)
    report                      human-readable summary of the last pull
    invert --champion <name>    which augments fit that champion (auto-pulls if needed)
    lists                       augment roster + rarity per mode (client data)
    items                       item ids, names and mode prices (client data)
    versions                    latest Data Dragon version + public patch mapping
    augment <key>               one augment by key or name fragment
    notes <docid|url>           official CN patch notes as text

Metrics — do not conflate them: `performance` is op.gg's own 0-100 impact score (NOT a win rate),
`pick` is pick rate in percent, `tier` is their bucket with 1 = best.

No dependencies: standard library plus the system `curl` (present on Windows 10+).
"""
from __future__ import annotations

import argparse
import hashlib
import html as htmllib
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp936

SKILL_ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("LOL_DATA_OUT") or (SKILL_ROOT / "out"))
CACHE = OUT / ".cache"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
DDRAGON = "https://ddragon.leagueoflegends.com"
CDRAGON = "https://raw.communitydragon.org/latest"
GAME_DATA = f"{CDRAGON}/plugins/rcp-be-lol-game-data/global"

RARITY = {1: "Silver", 4: "Gold", 8: "Prismatic"}
CLIENT_TTL = 43200  # 12h: client data only changes with the patch, and it is keyed by patch anyway
CHAMPION_RE = re.compile(
    r'\{"key":"(\w+)","name":"([^"]+)","image_url":"[^"]*","champion_id":(\d+),"id":\d+,"tier":(\d+),"rank":(\d+)\}'
)
AUGMENT_START_RE = re.compile(r'\{"id":\d+,"tier":\d+,"performance":[\d.]+,"popular":[\d.]+')

# patch notes live on a static, GBK-encoded route; the pretty URL is JS-only
NOTES_URL = "https://lol.qq.com/gicp/news/410/{}.html"


class FetchError(RuntimeError):
    """Raised with an actionable one-line message; never a bare traceback."""


# --------------------------------------------------------------------------- HTTP

def _curl(url: str, timeout: int) -> bytes | None:
    try:
        proc = subprocess.run(
            ["curl", "--compressed", "-sS", "-L", "--retry", "2", "--retry-delay", "1",
             "--connect-timeout", "8", "--max-time", str(timeout), "-A", UA, url],
            capture_output=True,
        )
    except FileNotFoundError:
        return None
    if proc.returncode == 0 and proc.stdout:
        return proc.stdout
    return None


def _urllib(url: str, timeout: int) -> bytes:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # public read-only endpoints; stale local CA stores are common
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as res:
        return res.read()


def fetch(url: str, timeout: int = 45, cache_ttl: int = 0, allow_stale: bool = False) -> bytes:
    """GET with a disk cache.

    `cache_ttl=0` bypasses the TTL check; negative caches forever. `allow_stale=True` falls back to a
    previously cached copy when the network fails, so one slow host degrades a field instead of the
    whole command.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".bin")
    if cache_ttl != 0 and key.exists():
        age = time.time() - key.stat().st_mtime
        if cache_ttl < 0 or age < cache_ttl:
            return key.read_bytes()
    try:
        raw = _curl(url, timeout)
        if raw is None:
            raw = _urllib(url, timeout)
    except Exception as exc:  # noqa: BLE001 - surfaced as an actionable message
        if allow_stale and key.exists():
            sys.stderr.write(f"warn: network failed, using cached copy for {url.rsplit('/', 1)[-1]}\n")
            return key.read_bytes()
        raise FetchError(f"network failed for {url}: {type(exc).__name__}: {exc}") from exc
    key.write_bytes(raw)
    return raw


def fetch_json(url: str, timeout: int = 45, cache_ttl: int = 0, allow_stale: bool = False):
    try:
        return json.loads(fetch(url, timeout, cache_ttl, allow_stale).decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise FetchError(f"{url} did not return JSON ({exc}). Endpoint may have moved.") from exc


def decode_text(raw: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|td|section)>", "\n", html)
    html = re.sub(r"(?s)<[^>]+>", "", html)
    html = htmllib.unescape(html).replace("\u00a0", " ")
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t\u3000]+", " ", html)).strip()


def norm_locale(locale: str) -> str:
    """CommunityDragon wants zh_cn (underscore, lowercase)."""
    return locale.replace("-", "_").lower()


def opgg_locale(locale: str) -> str:
    """op.gg wants zh-cn (hyphen, lowercase)."""
    return locale.replace("_", "-").lower()


def ddragon_locale(locale: str) -> str:
    """Data Dragon wants zh_CN (underscore, region uppercase)."""
    parts = norm_locale(locale).split("_")
    return f"{parts[0]}_{parts[1].upper()}" if len(parts) == 2 else locale


def save(name: str, obj) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- parsers (shared, no network)

def rsc_payload(html: str) -> str:
    """op.gg ships its data inside the Next.js flight payload and issues no XHR for it."""
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
    """Balanced-brace scan; nested objects (champion_ids) defeat naive regex."""
    found = []
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
                        found.append(json.loads(payload[match.start():i + 1]))
                    except json.JSONDecodeError:
                        pass
                    break
            i += 1
    return found


def parse_champions(payload: str) -> list[dict]:
    seen: dict[int, dict] = {}
    for key, name, cid, tier, rank in CHAMPION_RE.findall(payload):
        seen[int(cid)] = {"key": key, "name": name, "championId": int(cid),
                          "tier": int(tier), "rank": int(rank)}
    return sorted(seen.values(), key=lambda c: c["rank"])


def parse_augments(payload: str) -> list[dict]:
    best: dict[int, dict] = {}
    for obj in scan_objects(payload, AUGMENT_START_RE):
        if "aram-augment" not in (obj.get("largeIcon") or ""):
            continue
        best.setdefault(obj["id"], obj)
    rows = [{
        "name": o.get("name"),
        "key": o.get("key"),
        "rarity": RARITY.get(o.get("rarity"), str(o.get("rarity"))),
        "performance": o.get("performance"),
        "pick": o.get("popular"),
        "desc": re.sub(r"<[^>]+>", "", o.get("desc", "")),
        "champions": [c["name"] for c in o.get("champion_ids", [])],
        "championKeys": [c.get("key") for c in o.get("champion_ids", []) if c.get("key")],
    } for o in best.values()]
    return sorted(rows, key=lambda a: -(a["performance"] or 0))


# --------------------------------------------------------------------------- pulls

def opgg_page(mode: str, locale: str, ttl: int) -> str:
    url = f"https://op.gg/{opgg_locale(locale)}/lol/modes/{mode}"
    html = fetch(url, timeout=60, cache_ttl=ttl, allow_stale=True).decode("utf-8", "replace")
    if "__next_f" not in html:
        raise FetchError(
            f"op.gg returned a page without its data payload at {url}. Either the mode slug is wrong "
            f"or the request was blocked — retry, or fall back to client data (lists/items).")
    return html


def pull_meta(mode: str, locale: str, ttl: int, force: bool = False,
              version: str | None = None, version_getter=None) -> dict:
    """One page fetch -> both datasets. This is the whole reason `meta` exists.

    The cache is stamped with the Data Dragon version, so a patch bump invalidates it immediately
    instead of letting a 15-minute TTL hand back last patch's tier list. Within one patch the data is
    still refreshed on `ttl` because op.gg recomputes continuously.
    """
    champ_file = OUT / cache_name(mode, "champions")
    aug_file = OUT / cache_name(mode, "augments")
    stamp_file = OUT / cache_name(mode, "stamp")
    if version is None:
        version = version_getter() if version_getter else get_version(ttl)
    if not force and champ_file.exists() and aug_file.exists():
        age = time.time() - min(champ_file.stat().st_mtime, aug_file.stat().st_mtime)
        stamped = read_json(stamp_file)
        same_patch = bool(version) and (stamped or {}).get("ddragonVersion") == version
        if (ttl < 0 or age < ttl) and (same_patch or not version):
            return {"champions": json.loads(champ_file.read_text(encoding="utf-8")),
                    "augments": json.loads(aug_file.read_text(encoding="utf-8")),
                    "fromCache": True, "age": age, "patch": patch_label(version), "stale": False}
    payload = rsc_payload(opgg_page(mode, locale, -1 if force else ttl))
    champions, augments = parse_champions(payload), parse_augments(payload)
    if not champions or not augments:
        raise FetchError("op.gg payload parsed to zero rows — page layout changed. "
                         "Re-check the mode slug, or report the change.")
    save(champ_file.name, champions)
    save(aug_file.name, augments)
    save(stamp_file.name, {"ddragonVersion": version, "fetchedAt": time.time(), "mode": mode})
    return {"champions": champions, "augments": augments, "fromCache": False,
            "patch": patch_label(version), "stale": False}


def cache_name(mode: str, kind: str) -> str:
    return f"opgg_{mode.replace('-', '_')}_{kind}.json"


def get_version(ttl: int) -> str | None:
    try:
        return fetch_json(f"{DDRAGON}/api/versions.json", 30, ttl, allow_stale=True)[0]
    except FetchError:
        return None


def patch_label(version: str | None) -> str | None:
    if not version:
        return None
    major, minor = version.split(".")[:2]
    return f"26.{minor}" if major == "16" else f"{major}.{minor}"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def pull_client(locale: str, ttl: int, version: str | None = None, force: bool = False,
                with_items: bool = False, version_getter=None) -> dict:
    """Client roster, plus items only when asked.

    Two deliberate choices, both driven by measurement:
    - **items.json is opt-in.** It is 680 KB and CommunityDragon serves it at 11-90 KB/s from CN
      (18 s / 8 s / 45 s timeout on three consecutive tries), so it must never sit in the default path.
    - **the cache is keyed by patch, not by clock.** Client data only changes when the patch does, so a
      successful pull stays valid for the whole patch instead of expiring every 15 minutes.

    Every source still degrades on its own, and an item pull failure reuses whatever the last
    successful pull of the same patch produced.
    """
    if version is None:
        version = version_getter() if version_getter else get_version(ttl)
    cache_file = OUT / f"client_{norm_locale(locale)}.json"
    cached = read_json(cache_file)
    same_patch = cached if (cached and cached.get("ddragonVersion") == version) else None
    if same_patch and not force:
        fresh = ttl < 0 or (time.time() - cache_file.stat().st_mtime) < ttl
        if fresh and (same_patch.get("modeVariants") or not with_items):
            return same_patch

    def grab(url: str, timeout: int):
        try:
            return fetch_json(url, timeout, ttl, allow_stale=True)
        except FetchError as exc:
            sys.stderr.write(f"warn: {url.rsplit('/', 1)[-1]} unavailable ({exc})\n")
            return None

    jobs = {
        "lists": (f"{GAME_DATA}/{norm_locale(locale)}/v1/augment-lists.json", 30),
        "roster": (f"{GAME_DATA}/{norm_locale(locale)}/v1/cherry-augments.json", 45),
    }
    if with_items:
        jobs["clientItems"] = (f"{GAME_DATA}/{norm_locale(locale)}/v1/items.json", 150)
    if version:
        jobs["srItems"] = (f"{DDRAGON}/cdn/{version}/data/{ddragon_locale(locale)}/item.json", 60)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(grab, url, timeout) for name, (url, timeout) in jobs.items()}
        got = {name: fut.result() for name, fut in futures.items()}

    missing = [name for name, value in got.items() if value is None] + ([] if version else ["version"])
    roster = got.get("roster") or []
    client_items = got.get("clientItems") or []

    by_id = {a["augmentNameId"]: a for a in roster}
    modes = []
    for entry in got.get("lists") or []:
        keys = [p.rsplit("/", 1)[-1] for p in entry["augmentList"]]
        counts: dict[str, int] = {}
        rows = []
        for key in keys:
            meta = by_id.get(key)
            if not meta:
                continue
            counts[meta["rarity"]] = counts.get(meta["rarity"], 0) + 1
            rows.append({"key": key, "name": meta["nameTRA"], "rarity": meta["rarity"]})
        modes.append({"mode": entry["modeName"], "total": len(keys),
                      "rarity": {k.replace("k", ""): v for k, v in counts.items()},
                      "augments": rows})

    variants = [i for i in client_items if str(i.get("id", "")).startswith("22") and len(str(i["id"])) == 6]
    prismatic = [i for i in client_items if str(i.get("id", "")).startswith("228")]
    keep = same_patch or {}
    variants_payload = ([{"id": i["id"], "name": i["name"], "price": i["priceTotal"]}
                         for i in sorted(variants, key=lambda x: -x["priceTotal"])]
                        if variants else keep.get("modeVariants", []))
    prismatic_payload = ([{"id": i["id"], "name": i["name"], "price": i["priceTotal"]} for i in prismatic]
                         if prismatic else keep.get("prismaticPool", []))
    sr_count = len((got.get("srItems") or {}).get("data", {})) or keep.get("srItemCount", 0)

    payload = {
        "ddragonVersion": version,
        "locale": norm_locale(locale),
        "srItemCount": sr_count,
        "modes": modes or keep.get("modes", []),
        "modeVariants": variants_payload,
        "prismaticPool": prismatic_payload,
        "unavailable": missing,
    }
    save(f"client_{norm_locale(locale)}.json", payload)
    return payload


# --------------------------------------------------------------------------- commands

def cmd_refresh(args) -> None:
    """The one command a fresh session needs.

    Patch first (Data Dragon is fast: ~0.4 s measured, 1.5 MB/s from CN), then op.gg and the client
    roster are pulled **concurrently** — they are independent hosts, and previously they were two
    sequential waits. Items are opt-in: `items.json` is 680 KB served at 11-90 KB/s by
    CommunityDragon from CN (18 s / 8 s / timeout on three tries), so it would dominate every run.
    """
    started = time.time()
    print(f"# league patch pull — mode={args.mode} locale={args.locale}\n")

    version = get_version(args.cache_ttl)
    patch = patch_label(version)
    print(f"patch        : {patch}  (Data Dragon {version})" if version
          else "patch        : unknown — Data Dragon unavailable")

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_client = pool.submit(pull_client, args.locale, args.client_ttl, version, args.force,
                               args.with_items)
        f_meta = pool.submit(pull_meta, args.mode, args.locale, args.cache_ttl, args.force)
        try:
            client = f_client.result()
        except FetchError as exc:
            client = {"modes": [], "modeVariants": [], "prismaticPool": [], "srItemCount": 0,
                      "unavailable": [f"client data ({exc})"]}
        try:
            meta, meta_error = f_meta.result(), None
        except FetchError as exc:
            meta, meta_error = None, exc

    for mode in client["modes"]:
        if mode["mode"] in ("KIWI", "CHERRY"):
            r = mode["rarity"]
            print(f"roster {mode['mode']:<7}: {mode['total']} augments "
                  f"(Silver {r.get('Silver', 0)} / Gold {r.get('Gold', 0)} / Prismatic {r.get('Prismatic', 0)})")
    if client["modeVariants"]:
        print(f"items        : {client['srItemCount']} SR | {len(client['modeVariants'])} mode variants "
              f"| {len(client['prismaticPool'])} prismatic"
              + ("" if args.with_items else "   (`items` to refresh; skipped by default)"))
    else:
        print("items        : not pulled — run `items` when you need prices "
              "(CommunityDragon is slow from CN, so it is opt-in)")
    if client["unavailable"]:
        print(f"! partial pull: {', '.join(client['unavailable'])} unavailable — "
              f"answer without those numbers and say they are missing")

    if meta_error is not None:
        print(f"\n! op.gg unavailable — continuing with client data only.\n  {meta_error}")
    else:
        champs, augs = meta["champions"], meta["augments"]
        print(f"tier list    : {len(champs)} champions, tiers " +
              "/".join(f"T{t}={sum(1 for c in champs if c['tier'] == t)}" for t in sorted({c['tier'] for c in champs})))
        print(f"augment stats: {len(augs)} augments" + ("  (from local cache)" if meta["fromCache"] else ""))
        print("\nTop augments by performance:")
        for row in augs[:8]:
            print(f"  {row['performance']:>6}  [{row['rarity']:<9}] {row['name']:<16} pick {row['pick']}%")
        print("\nTier 1 champions: " + "、".join(c["name"] for c in champs if c["tier"] == 1))

    print(f"\nfiles       : {OUT}")
    print(f"elapsed     : {time.time() - started:.1f}s")
    print("\nNext: `invert --champion <name>` for champion-specific augments; "
          "`notes <docid>` for this patch's official changes.")


def cmd_meta(args) -> None:
    meta = pull_meta(args.mode, args.locale, args.cache_ttl, force=args.force)
    champs, augs = meta["champions"], meta["augments"]
    print(f"{len(champs)} champions · {len(augs)} augments" + ("  (cache)" if meta["fromCache"] else ""))
    for row in augs[:10]:
        print(f"  {row['performance']:>6}  [{row['rarity']:<9}] {row['name']}")


def cmd_report(args) -> None:
    meta = pull_meta(args.mode, args.locale, args.cache_ttl)
    champs, augs = meta["champions"], meta["augments"]
    for tier in sorted({c["tier"] for c in champs}):
        names = [c["name"] for c in champs if c["tier"] == tier]
        print(f"T{tier} ({len(names)}): {'、'.join(names[:25])}{' …' if len(names) > 25 else ''}")
    print("\nBy performance:")
    for row in augs[:10]:
        print(f"  {row['performance']:>6} [{row['rarity']:<9}] {row['name']:<16} pick {row['pick']}%")
    print("\nBy pick rate:")
    for row in sorted(augs, key=lambda a: -(a["pick"] or 0))[:10]:
        print(f"  {row['pick']:>5}% [{row['rarity']:<9}] {row['name']:<16} perf {row['performance']}")


def champion_aliases(locale: str, ttl: int) -> dict[str, str]:
    """Map every name a player might type -> canonical champion key.

    op.gg labels champions with their *title* (迅捷斥候) while players say the *name* (提莫) and the
    English key (teemo). Accepting all three is the difference between one call and three failures.
    """
    version = fetch_json(f"{DDRAGON}/api/versions.json", cache_ttl=ttl)[0]
    data = fetch_json(f"{DDRAGON}/cdn/{version}/data/{ddragon_locale(locale)}/champion.json",
                      cache_ttl=ttl)["data"]
    alias: dict[str, str] = {}
    for key, champ in data.items():
        for candidate in (key, champ.get("name", ""), champ.get("title", "")):
            if candidate:
                alias[candidate.strip().lower()] = key.lower()
    return alias


def cmd_invert(args) -> None:
    meta = pull_meta(args.mode, args.locale, args.cache_ttl)  # auto-pulls when missing or stale
    augs = meta["augments"]
    if not augs or "championKeys" not in augs[0]:  # older cache layout
        meta = pull_meta(args.mode, args.locale, args.cache_ttl, force=True)
        augs = meta["augments"]

    needle = args.champion.strip().lower()
    resolved = champion_aliases(args.locale, args.cache_ttl).get(needle)
    if resolved is None and not any(needle in n.lower() for a in augs for n in a["champions"]):
        raise FetchError(
            f"unknown champion {args.champion!r}. Use the champion name (提莫), their title (迅捷斥候), "
            f"or the English key (teemo).")

    hits = [a for a in augs
            if (resolved and resolved in a.get("championKeys", []))
            or any(needle in n.lower() for n in a["champions"])]
    if not hits:
        raise FetchError(
            f"op.gg has no augment flagged for {args.champion!r} in {args.mode}. It only tags champions "
            f"it has data for — this champion is either off-meta here or genuinely unremarkable on every "
            f"augment. Fall back to `report` and reason from the champion's kit.")
    print(f"{args.champion} — {len(hits)} flagged augments in {args.mode}:")
    for a in sorted(hits, key=lambda x: -(x["performance"] or 0)):
        print(f"  {a['performance']:>6} [{a['rarity']:<9}] {a['name']:<16} pick {a['pick']:>5}%  {a['desc'][:64]}")


def cmd_brief(args) -> None:
    """Patch + tier + one champion's augments in a single call: the 'write me a guide' entry point."""
    version = get_version(args.cache_ttl)
    meta = pull_meta(args.mode, args.locale, args.cache_ttl)

    needle = args.champion.strip().lower()
    aliases = champion_aliases(args.locale, args.cache_ttl)
    resolved = aliases.get(needle)
    champ = next((c for c in meta["champions"]
                  if c["key"].lower() == resolved or needle in c["name"].lower()), None)

    print(f"patch  : {patch_label(version)}  (Data Dragon {version})" if version else "patch  : unknown")
    print(f"mode   : {args.mode}")
    if champ:
        print(f"tier   : T{champ['tier']}  (rank {champ['rank']}/"
              f"{len(meta['champions'])} in this mode — op.gg order, 1 = best)")
    else:
        print(f"tier   : {args.champion} not found in the op.gg tier list for {args.mode}")

    hits = [a for a in meta["augments"]
            if (resolved and resolved in a.get("championKeys", []))
            or any(needle in n.lower() for n in a["champions"])]
    if not hits:
        print(f"\nop.gg flags no augment for {args.champion!r} in this mode — reason from the champion's kit "
              f"instead, and say the data is missing.")
        return
    print(f"\n{args.champion} — {len(hits)} flagged augments (op.gg performance, not win rate):")
    for a in sorted(hits, key=lambda x: -(x["performance"] or 0)):
        print(f"  {a['performance']:>6} [{a['rarity']:<9}] {a['name']:<16} pick {a['pick']:>5}%  {a['desc'][:60]}")


MODE_CODE = {"aram-mayhem": "KIWI", "aram-mayhem-classic": "KIWI_JADE", "arena": "CHERRY"}


def cmd_verify(args) -> None:
    """Check names from a guide against the client roster before repeating them.

    Search results, videos and community guides name augments that often do not exist — measured on
    patch 26.18, half of the names in a typical "self-destruct comp" write-up were invented. Arena
    (CHERRY) and ARAM Mayhem (KIWI) pools are also routinely confused with each other.
    """
    import difflib

    version = get_version(args.cache_ttl)
    client = pull_client(args.locale, args.client_ttl, version=version, with_items=args.with_items)
    wanted = MODE_CODE.get(args.mode, args.mode.upper())

    pool = next((m for m in client["modes"] if m["mode"] == wanted), None)
    in_mode = {a["name"] for a in (pool or {}).get("augments", [])}
    elsewhere = {m["mode"]: {a["name"] for a in m["augments"]} for m in client["modes"]}
    items = {i["name"] for i in client.get("modeVariants", [])} | \
            {i["name"] for i in client.get("prismaticPool", [])}

    print(f"verifying against {wanted} ({len(in_mode)} augments)"
          + (f" + {len(items)} mode items" if items else "  (items not loaded; --with-items to include)"))
    unknown = 0
    for term in args.terms:
        if term in in_mode:
            print(f"  ok      {term}")
            continue
        other = [m for m, names in elsewhere.items() if term in names]
        if other:
            print(f"  MISLEAD {term} — exists in {', '.join(other)}, NOT in {wanted}. "
                  f"A guide is describing a different mode.")
            continue
        if term in items:
            print(f"  ok      {term} (item)")
            continue
        unknown += 1
        near = difflib.get_close_matches(term, sorted(in_mode | items), n=3, cutoff=0.4)
        hint = f" closest real names: {' / '.join(near)}" if near else ""
        print(f"  NOT FOUND {term} — not in {wanted} or any mode's roster.{hint}")
    print(f"\n{len(args.terms) - unknown}/{len(args.terms)} verified. "
          f"Never repeat a name that fails this check — the guide invented it.")


def cmd_champions(args) -> None:
    for c in pull_meta(args.mode, args.locale, args.cache_ttl)["champions"]:
        print(f"{c['rank']:>3} T{c['tier']} {c['name']}")


def cmd_augments(args) -> None:
    for a in pull_meta(args.mode, args.locale, args.cache_ttl)["augments"]:
        print(f"{a['performance']:>6} [{a['rarity']:<9}] {a['name']:<16} pick {a['pick']}%")


def cmd_lists(args) -> None:
    payload = pull_client(args.locale, args.client_ttl)
    for mode in payload["modes"]:
        r = mode["rarity"]
        print(f"{mode['mode']:<10} {mode['total']:>4} augments  "
              f"(Silv {r.get('Silver', 0)} / Gold {r.get('Gold', 0)} / Pris {r.get('Prismatic', 0)})")
    print(f"-> {OUT / f'client_{norm_locale(args.locale)}.json'}")


def cmd_items(args) -> None:
    payload = pull_client(args.locale, args.client_ttl, force=args.force, with_items=True)
    if not payload["modeVariants"]:
        raise FetchError(f"client item data unavailable this run ({', '.join(payload['unavailable']) or 'unknown'}). "
                         f"CommunityDragon is slow from CN (~11-90 KB/s for 680 KB) — retry, or re-run with "
                         f"--force. Roster and patch data are unaffected.")
    print(f"SR items: {payload['srItemCount']} | mode variants: {len(payload['modeVariants'])} "
          f"| prismatic pool: {len(payload['prismaticPool'])}")
    for item in [i for i in payload["modeVariants"] if i["price"] >= 3000]:
        print(f"  {item['name']:<16} id={item['id']} {item['price']}g")
    print(f"-> {OUT / f'client_{norm_locale(args.locale)}.json'}")


def cmd_versions(_args) -> None:
    versions = fetch_json(f"{DDRAGON}/api/versions.json", cache_ttl=900)
    major, minor = versions[0].split(".")[:2]
    patch = f"26.{minor}" if major == "16" else f"{major}.{minor} (verify mapping)"
    print(f"latest DDragon version : {versions[0]}")
    print(f"public patch equivalent: {patch}")
    print(f"recent                 : {', '.join(versions[:5])}")


def cmd_augment(args) -> None:
    roster = fetch_json(f"{GAME_DATA}/{norm_locale(args.locale)}/v1/cherry-augments.json", cache_ttl=args.cache_ttl)
    needle = args.key.lower()
    hits = [a for a in roster if needle in a["augmentNameId"].lower() or needle in a["nameTRA"].lower()]
    if not hits:
        raise FetchError(f"no augment matches {args.key!r}")
    for a in hits[:20]:
        print(f"{a['nameTRA']:<18} [{a['rarity'].replace('k', '')}] key={a['augmentNameId']}")


def cmd_notes(args) -> None:
    target = args.target
    if target.isdigit():
        url = NOTES_URL.format(target)
    elif "detail.shtml" in target:
        raise FetchError("that route is JS-rendered. Use the static form "
                         f"{NOTES_URL.format('<id>')} (or open it in a browser).")
    else:
        url = target
    text = html_to_text(decode_text(fetch(url, cache_ttl=args.cache_ttl)))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"notes_{target if target.isdigit() else 'page'}.txt"
    path.write_text(text, encoding="utf-8")
    print(text[:2500])
    print(f"\n-> {path} ({len(text)} chars)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p, need_mode=True):
        if need_mode:
            p.add_argument("--mode", default="aram-mayhem",
                           help="aram-mayhem | aram-mayhem-classic | aram | arena | ranked-solo-duo")
        p.add_argument("--locale", default="zh-cn", help="zh-cn | en | ko | ja")
        p.add_argument("--out", help="output directory (default: <skill>/out, or $LOL_DATA_OUT)")

    p_refresh = sub.add_parser("refresh", help="pull everything and print a summary")
    common(p_refresh)
    p_refresh.add_argument("--cache-ttl", type=int, default=900, help="seconds; 0 bypasses cache")
    p_refresh.add_argument("--client-ttl", type=int, default=CLIENT_TTL,
                           help="seconds for client data (roster); keyed by patch too")
    p_refresh.add_argument("--with-items", action="store_true",
                           help="also pull the 680KB item table (slow from CN; `items` does this too)")
    p_refresh.add_argument("--force", action="store_true")
    p_refresh.set_defaults(func=cmd_refresh)

    p_brief = sub.add_parser("brief", help="patch + tier + augments for one champion, in one call")
    p_brief.add_argument("--champion", required=True)
    common(p_brief)
    p_brief.add_argument("--cache-ttl", type=int, default=900)
    p_brief.set_defaults(func=cmd_brief)

    for name, fn in (("meta", cmd_meta), ("report", cmd_report), ("champions", cmd_champions),
                     ("augments", cmd_augments)):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--cache-ttl", type=int, default=900)
        p.add_argument("--force", action="store_true")
        p.set_defaults(func=fn)

    p_inv = sub.add_parser("invert", help="augments flagged for one champion")
    p_inv.add_argument("--champion", required=True)
    common(p_inv)
    p_inv.add_argument("--cache-ttl", type=int, default=900)
    p_inv.set_defaults(func=cmd_invert)

    for name, fn in (("lists", cmd_lists), ("items", cmd_items)):
        p = sub.add_parser(name)
        common(p, need_mode=False)
        p.add_argument("--cache-ttl", type=int, default=900)
        p.add_argument("--client-ttl", type=int, default=CLIENT_TTL)
        if fn is cmd_items:
            p.add_argument("--force", action="store_true")
        p.set_defaults(func=fn)

    p_ver = sub.add_parser("versions", help="latest Data Dragon version + patch mapping")
    p_ver.add_argument("--out", help="output directory (unused; accepted for CLI symmetry)")
    p_ver.add_argument("--cache-ttl", type=int, default=900)
    p_ver.set_defaults(func=cmd_versions)

    p_verify = sub.add_parser("verify",
                              help="check augment/item names from a guide against the client roster")
    p_verify.add_argument("terms", nargs="+", help="names to verify, e.g. 自我毁灭 小丑学院")
    common(p_verify)
    p_verify.add_argument("--cache-ttl", type=int, default=900)
    p_verify.add_argument("--client-ttl", type=int, default=CLIENT_TTL)
    p_verify.add_argument("--with-items", action="store_true", help="also check item names")
    p_verify.set_defaults(func=cmd_verify)

    p_aug = sub.add_parser("augment", help="look up one augment by key or name fragment")
    p_aug.add_argument("key")
    common(p_aug, need_mode=False)
    p_aug.add_argument("--cache-ttl", type=int, default=900)
    p_aug.set_defaults(func=cmd_augment)

    p_notes = sub.add_parser("notes", help="official CN patch notes -> text")
    p_notes.add_argument("target")
    p_notes.add_argument("--locale", default="zh_cn")
    p_notes.add_argument("--cache-ttl", type=int, default=900)
    p_notes.add_argument("--out")
    p_notes.set_defaults(func=cmd_notes)

    args = parser.parse_args()
    global OUT, CACHE
    if getattr(args, "out", None):
        OUT = Path(args.out)
        CACHE = OUT / ".cache"
    try:
        args.func(args)
    except FetchError as exc:
        sys.stderr.write(f"error: {exc}\n")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
