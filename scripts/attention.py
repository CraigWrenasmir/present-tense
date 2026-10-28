#!/usr/bin/env python3
"""What people looked up and talked about: a second register beside the headlines.

Collects, with the standard library only:
- Wikipedia: yesterday's most-viewed articles in each of a set of language editions
  (Wikimedia REST API, open data), with the housekeeping pages removed;
- Bluesky: the public trending topics (public.api.bsky.app, no key);
- Mastodon: trending hashtags on a handful of servers in different languages
  (public endpoints), kept only when used enough to mean something.

Every Wikipedia page is resolved to one subject across languages through its
Wikidata item (interlanguage links), with an English title, a one-line
description and English aliases, so "Elecciones generales de Brasil de 2026"
and "2026 Brazilian general election" count as one subject reached for in two
editions. The aliases let the site match subjects to the narratives' headlines
("Lula" for Luiz Inácio Lula da Silva). Lookups are cached in
data/attention-cache.json.

Writes data/attention.json (current), data/attention/<day>.json (one per
Wikipedia day, kept) and data/attention/index.json. Each source is a separate
register and is labelled as such on the page; none of it is evidence for a
narrative, only context. Every source is fetched with a timeout and skipped on
failure, so the file is always written and never blocks a run.

Usage: python3 scripts/attention.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UA = "PresentTense/1.0 (https://github.com/CraigWrenasmir/present-tense)"

# Language editions, chosen to match the countries the headline collection covers.
WIKIS = [
    ("en", "English"), ("es", "Spanish"), ("pt", "Portuguese"), ("fr", "French"), ("de", "German"), ("it", "Italian"),
    ("ru", "Russian"), ("uk", "Ukrainian"), ("pl", "Polish"), ("tr", "Turkish"), ("ar", "Arabic"), ("fa", "Persian"),
    ("he", "Hebrew"), ("hi", "Hindi"), ("bn", "Bengali"), ("id", "Indonesian"), ("vi", "Vietnamese"), ("th", "Thai"),
    ("zh", "Chinese"), ("ja", "Japanese"), ("ko", "Korean"), ("nl", "Dutch"), ("sv", "Swedish"), ("fi", "Finnish"),
    ("el", "Greek"), ("sw", "Swahili"), ("ms", "Malay"), ("tl", "Tagalog"),
]
TOP_N = 15
SKIP_PREFIXES = ("Special:", "Wikipedia:", "Wikipédia:", "Portal:", "Help:", "File:", "Category:", "Template:", "Talk:", "User:",
                 "Especial:", "Spezial:", "Spécial:", "Speciale:", "Служебная:", "Спеціальна:", "Specjalna:", "Özel:", "خاص:", "ویژه:",
                 "מיוחד:", "विशेष:", "বিশেষ:", "Istimewa:", "Đặc_biệt:", "พิเศษ:", "特殊:", "特別:", "특수:", "Speciaal:", "Special:",
                 "Toiminnot:", "Ειδικό:", "Maalum:", "Khas:", "Natatangi:", "Wikipedia_talk:", "Portail:", "Portada", "Hauptseite")
SKIP_EXACT = {"Main_Page", "Wikipedia:Portada", "Wikipédia:Accueil_principal", "Wikipedia:Hauptseite", "Pagina_principale",
              "Заглавная_страница", "Головна_сторінка", "Wikipedia:Strona_główna", "Anasayfa", "الصفحة_الرئيسية", "صفحهٔ_اصلی",
              "עמוד_ראשי", "मुखपृष्ठ", "প্রধান_পাতা", "Halaman_Utama", "Trang_Chính", "หน้าหลัก", "Wikipedia:首页", "メインページ",
              "위키백과:대문", "Hoofdpagina", "Portal:Huvudsida", "Wikipedia:Etusivu", "Πύλη:Κύρια", "Mwanzo", "Laman_Utama",
              "Unang_Pahina", "-", "Wikipedia:Featured_articles", "Cleopatra", "Deaths_in_2026", "Deaths_in_2025", "XXX",
              "Pornhub", "XHamster", "XVideos", "YouTube", "WhatsApp", "Facebook", "Instagram", "Google", "Bing"}
MASTODON = [("mastodon.social", "English"), ("mstdn.jp", "Japanese"), ("piaille.fr", "French"), ("chaos.social", "German"),
            ("mastodon.uno", "Italian"), ("mastodon.cl", "Spanish"), ("masto.pt", "Portuguese"), ("mastodon.online", "English")]
MASTODON_MIN_USES = 60  # across the last two days on that server; below this a tag is a game or a handful of people


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


CACHE = DATA / "attention-cache.json"
WD_URL = "https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=labels|aliases|descriptions&languages=en&ids="
STOP_ALIASES = {"the", "and", "list", "lists", "film", "song", "album", "series", "state", "states", "united", "republic", "president", "election", "elections"}


def load_cache():
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def save_cache(cache, today):
    # keep entries used in the last 90 days
    keep = {k: v for k, v in cache.items() if (v.get("used") or today) >= (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")}
    CACHE.write_text(json.dumps(keep, ensure_ascii=False, sort_keys=True) + "\n")


def resolve_pages(code, titles, cache, today):
    """Map each title in one language edition to its Wikidata item and English title, through the interlanguage links."""
    todo = [t for t in titles if f"{code}:{t}" not in cache]
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        url = (f"https://{code}.wikipedia.org/w/api.php?action=query&format=json&prop=langlinks|pageprops&lllang=en&lllimit=max"
               f"&ppprop=wikibase_item&redirects=1&titles={urllib.parse.quote('|'.join(chunk))}")
        try:
            q = get(url).get("query", {})
        except Exception as error:  # noqa: BLE001
            print(f"attention: resolve {code}: {error}", file=sys.stderr)
            continue
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
        by_title = {p.get("title"): p for p in q.get("pages", {}).values()}
        for t in chunk:
            final = redir.get(norm.get(t, t), norm.get(t, t))
            page = by_title.get(final) or by_title.get(final.replace("_", " ")) or by_title.get(t.replace("_", " "))
            entry = {"used": today}
            if page:
                entry["qid"] = (page.get("pageprops") or {}).get("wikibase_item")
                ll = page.get("langlinks") or []
                entry["en"] = ll[0].get("*") if ll else (page.get("title") if code == "en" else None)
            cache[f"{code}:{t}"] = entry
    for t in titles:
        cache.setdefault(f"{code}:{t}", {"used": today})["used"] = today


def resolve_items(qids, cache, today):
    """English label, description and aliases for Wikidata items, cached under wd:Q..."""
    todo = [q for q in qids if q and f"wd:{q}" not in cache]
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        try:
            ents = get(WD_URL + "|".join(chunk)).get("entities", {})
        except Exception as error:  # noqa: BLE001
            print(f"attention: wikidata: {error}", file=sys.stderr)
            continue
        for q, e in ents.items():
            label = ((e.get("labels") or {}).get("en") or {}).get("value")
            desc = ((e.get("descriptions") or {}).get("en") or {}).get("value")
            aliases = [a["value"] for a in ((e.get("aliases") or {}).get("en") or [])]
            cache[f"wd:{q}"] = {"label": label, "description": desc, "aliases": aliases[:24], "used": today}
    for q in qids:
        if q and f"wd:{q}" in cache:
            cache[f"wd:{q}"]["used"] = today


def subjects_of(languages, cache):
    """Group the per-language lists into subjects, one per Wikidata item, ordered by how many editions reached for them."""
    groups = {}
    for l in languages:
        for a in l["articles"]:
            c = cache.get(f"{l['language']}:{a['title'].replace(' ', '_')}") or {}
            key = c.get("qid") or f"{l['language']}:{a['title']}"
            g = groups.setdefault(key, {"key": key, "qid": c.get("qid"), "title": None, "description": None, "aliases": [], "languages": [], "views": 0})
            g["languages"].append({"language": l["language"], "languageName": l["languageName"], "title": a["title"], "views": a["views"], "url": a["url"]})
            g["views"] += a["views"]
            if not g["title"] and c.get("en"):
                g["title"] = c["en"]
    for g in groups.values():
        wd = cache.get(f"wd:{g['qid']}") if g.get("qid") else None
        if wd:
            g["title"] = g["title"] or wd.get("label")
            g["description"] = wd.get("description")
            seen = {(g["title"] or "").lower()}
            # a nickname in quotes inside an alias ('Luiz Inácio "Lula" da Silva') is how headlines name the person
            import re
            quoted = [m for al in (wd.get("aliases") or []) for m in re.findall(r'"([^"]{3,30})"', al)]
            for al in quoted + list(wd.get("aliases") or []):
                k = al.lower().strip()
                if len(k) >= 4 and k not in seen and k not in STOP_ALIASES and not k.isdigit():
                    g["aliases"].append(al); seen.add(k)
        if not g["title"]:
            g["title"] = g["languages"][0]["title"]
        # people are usually in headlines by surname: add it as an alias when the description says this is a person
        desc = (g.get("description") or "").lower()
        if any(w in desc for w in ("politician", "president", "footballer", "player", "singer", "actor", "actress", "minister", "journalist", "businessman", "businessperson", "writer", "rapper", "musician", "coach", "manager", "prime minister", "senator", "governor", "activist", "entrepreneur", "chief executive")):
            parts = g["title"].replace("(", " ").split()
            last = parts[-1] if parts else ""
            if len(last) >= 4 and last.lower() not in STOP_ALIASES and last.lower() not in {a.lower() for a in g["aliases"]} and last.lower() != g["title"].lower():
                g["aliases"].append(last)
        g["editions"] = len({x["language"] for x in g["languages"]})
        g["languages"].sort(key=lambda x: -x["views"])
        g["url"] = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(g['title'].replace(' ', '_'))}" if g.get("qid") and any(x["language"] == "en" for x in g["languages"]) or (g.get("qid") and g["title"] and g["title"] == (cache.get(f"wd:{g['qid']}") or {}).get("label")) else g["languages"][0]["url"]
    out = sorted(groups.values(), key=lambda g: (-g["editions"], -g["views"]))
    return out


def wikipedia(day):
    out = []
    for code, name in WIKIS:
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{code}.wikipedia/all-access/{day:%Y/%m/%d}"
        try:
            items = get(url)["items"][0]["articles"]
        except Exception as error:  # noqa: BLE001
            print(f"attention: wikipedia {code} {day:%Y-%m-%d}: {error}", file=sys.stderr)
            if "404" in str(error) and not out:
                return []  # the day is not published yet; the caller tries the day before
            continue
        arts = []
        for a in items:
            t = a["article"]
            if t in SKIP_EXACT or t.startswith(SKIP_PREFIXES) or ":" in t.split("_")[0] and not t.startswith("20"):
                continue
            arts.append({"title": t.replace("_", " "), "views": a["views"], "url": f"https://{code}.wikipedia.org/wiki/{urllib.parse.quote(t)}"})
            if len(arts) >= TOP_N:
                break
        out.append({"language": code, "languageName": name, "project": f"{code}.wikipedia", "articles": arts})
    return out


def bluesky():
    try:
        d = get("https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics?limit=25")
    except Exception as error:  # noqa: BLE001
        print(f"attention: bluesky: {error}", file=sys.stderr)
        return []
    return [{"topic": t.get("topic", ""), "url": "https://bsky.app" + t["link"] if t.get("link", "").startswith("/") else t.get("link", "")}
            for t in d.get("topics", []) if t.get("topic")]


def mastodon():
    out = []
    for server, lang in MASTODON:
        try:
            tags = get(f"https://{server}/api/v1/trends/tags?limit=20", timeout=12)
        except Exception as error:  # noqa: BLE001
            print(f"attention: mastodon {server}: {error}", file=sys.stderr)
            continue
        for t in tags:
            uses = sum(int(h.get("uses", 0)) for h in t.get("history", [])[:2])
            if uses >= MASTODON_MIN_USES:
                out.append({"tag": t["name"], "uses": uses, "server": server, "language": lang, "url": t.get("url") or f"https://{server}/tags/{t['name']}"})
    # the same tag trends across servers at once (hashtag games mostly); merge by tag
    merged = {}
    for t in out:
        m = merged.setdefault(t["tag"].lower(), {"tag": t["tag"], "uses": 0, "servers": [], "languages": [], "url": t["url"]})
        m["uses"] += t["uses"]; m["servers"].append(t["server"])
        if t["language"] not in m["languages"]:
            m["languages"].append(t["language"])
    out = sorted(merged.values(), key=lambda x: -x["uses"])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="Wikipedia day (UTC), default yesterday")
    args = parser.parse_args()
    if args.date:
        day = datetime.strptime(args.date, "%Y-%m-%d"); wiki = wikipedia(day)
    else:
        # Wikimedia publishes a day's top lists some hours after it ends; take yesterday if it is there, else the day before.
        for back in (1, 2):
            day = datetime.now(timezone.utc) - timedelta(days=back)
            wiki = wikipedia(day)
            if wiki:
                break
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache = load_cache()
    for l in wiki:
        resolve_pages(l["language"], [a["title"].replace(" ", "_") for a in l["articles"]], cache, today)
    resolve_items(sorted({(cache.get(f"{l['language']}:{a['title'].replace(' ', '_')}") or {}).get("qid") for l in wiki for a in l["articles"]} - {None}), cache, today)
    subjects = subjects_of(wiki, cache)
    save_cache(cache, today)
    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "wikipedia": {"date": f"{day:%Y-%m-%d}", "source": "Wikimedia REST API, most-viewed articles per language edition, all access; subjects resolved through Wikidata", "languages": wiki, "subjects": subjects},
        "bluesky": {"source": "Bluesky public trending topics", "topics": bluesky()},
        "mastodon": {"source": "Trending hashtags on a few servers, two-day uses", "tags": mastodon()},
        "notes": [
            "A second register beside the headlines: what people looked up and talked about. Context, not evidence.",
            "Wikipedia's lists are by language edition, not by country. Bluesky's list is one platform's own ranking, mostly English. Mastodon's is a few servers.",
        ],
    }
    (DATA / "attention.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    # history: one file per Wikipedia day, and an index with each day's most cross-lingual subjects
    hist = DATA / "attention"; hist.mkdir(exist_ok=True)
    if wiki:
        (hist / f"{day:%Y-%m-%d}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    days = []
    for p in sorted(hist.glob("*.json")):
        if p.name == "index.json":
            continue
        d = json.loads(p.read_text())
        subs = (d.get("wikipedia") or {}).get("subjects") or []
        days.append({"date": p.stem, "file": f"data/attention/{p.name}", "languages": len((d.get("wikipedia") or {}).get("languages") or []),
                     "top": [{"title": g["title"], "editions": g["editions"], "views": g["views"], "url": g["url"]} for g in subs[:8]]})
    days.sort(key=lambda d: d["date"], reverse=True)
    (hist / "index.json").write_text(json.dumps({"days": days}, ensure_ascii=False, indent=1) + "\n")
    print(f"attention: {sum(len(w['articles']) for w in wiki)} Wikipedia articles in {len(wiki)} languages -> {len(subjects)} subjects ({sum(1 for g in subjects if g['editions'] > 1)} in more than one edition); {len(out['bluesky']['topics'])} Bluesky topics, {len(out['mastodon']['tags'])} Mastodon tags; {len(days)} days kept")


if __name__ == "__main__":
    main()
