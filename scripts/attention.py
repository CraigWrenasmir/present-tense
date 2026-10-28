#!/usr/bin/env python3
"""What people looked up and talked about: a second register beside the headlines.

Collects, with the standard library only:
- Wikipedia: yesterday's most-viewed articles in each of a set of language editions
  (Wikimedia REST API, open data), with the housekeeping pages removed;
- Bluesky: the public trending topics (public.api.bsky.app, no key);
- Mastodon: trending hashtags on a handful of servers in different languages
  (public endpoints), kept only when used enough to mean something.

Writes data/attention.json. Each source is a separate register and is labelled as
such on the page; none of it is evidence for a narrative, only context. Every
source is fetched with a timeout and skipped on failure, so the file is always
written and never blocks a run.

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
    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "wikipedia": {"date": f"{day:%Y-%m-%d}", "source": "Wikimedia REST API, most-viewed articles per language edition, all access", "languages": wiki},
        "bluesky": {"source": "Bluesky public trending topics", "topics": bluesky()},
        "mastodon": {"source": "Trending hashtags on a few servers, two-day uses", "tags": mastodon()},
        "notes": [
            "A second register beside the headlines: what people looked up and talked about. Context, not evidence.",
            "Wikipedia's lists are by language edition, not by country. Bluesky's list is one platform's own ranking, mostly English. Mastodon's is a few servers.",
        ],
    }
    (DATA / "attention.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(f"attention: {sum(len(w['articles']) for w in wiki)} Wikipedia articles in {len(wiki)} languages, {len(out['bluesky']['topics'])} Bluesky topics, {len(out['mastodon']['tags'])} Mastodon tags")


if __name__ == "__main__":
    main()
