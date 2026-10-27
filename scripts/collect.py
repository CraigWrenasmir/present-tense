#!/usr/bin/env python3
"""Collect a bounded, geographically varied sample of GDELT headline metadata.

Python standard library only. This never requests a publisher's article body.
GDELT GAL dates are publication OR first-observed dates, not verified event dates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import html
import io
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "PresentTensePrototype/1.0 (GDELT metadata research; no article scraping)"
MAX_UNCOMPRESSED = 35_000_000


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch(url, limits):
    """Two bounded attempts for temporary errors; 404 is a normal missing minute."""
    for attempt in range(2):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=limits["requestTimeoutSeconds"]) as response:
                data = response.read(limits["maxDownloadBytes"] + 1)
                if len(data) > limits["maxDownloadBytes"]:
                    raise ValueError("Download exceeds configured byte limit")
                return data
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt:
                raise
            time.sleep(3)
        except (TimeoutError, urllib.error.URLError):
            if attempt:
                raise
            time.sleep(2)
    raise RuntimeError("No response")


def decode_gal(data):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as source:
        raw = source.read(MAX_UNCOMPRESSED + 1)
    if len(raw) > MAX_UNCOMPRESSED:
        raise ValueError("Decompressed data exceeds safe limit")
    records = []
    for line in raw.decode("utf-8").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
        except (ValueError, TypeError):
            continue
    return records


def safe_url(raw):
    if not isinstance(raw, str) or len(raw) > 3000:
        return None
    try:
        parsed = urllib.parse.urlsplit(raw.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        if any(ord(c) < 32 for c in raw):
            return None
        query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path,
                                      urllib.parse.urlencode(query), ""))
    except ValueError:
        return None


def clean_text(raw):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", html.unescape(str(raw or "")))).strip()


TOPICS = {
    "Environment": r"climat|flood|wildfire|drought|emission|biodivers|hurricane|typhoon|rainfall|aquecimento|enchente|incêndio|sécheresse|inondation|气候|洪水|台風|気候",
    "Technology": r"\bAI\b|artificial intelligence|semiconductor|robot|software|cyber|inteligência artificial|人工智能|半导体|半導体",
    "Economy": r"econom|inflation|tariff|trade|bank|stock|market|budget|interest rate|invest|emploi|mercado|comércio|inflación|经济|经济|金融|市場|株価",
    "Politics": r"elect|presiden|parliament|minister|government|congress|diploma|protest|ceasefire|war\b|militar|vote|gouvernement|eleiç|elecció|polític|政府|大統領|選挙|选举",
    "Culture": r"music|concert|film|cinema|art\b|artist|museum|novel|theatre|theater|festival|singer|album|música|cultura|cinéma|电影|音乐|音楽|映画",
    "Science": r"scien|research|spacecraft|astronom|quantum|telescope|nasa|scientifi|pesquisa|科学|宇宙|研究",
    "Sport": r"football|soccer|cricket|tennis|olympic|league|match|futebol|brasileir|nba|athlet|champion|rugby|baseball|サッカー|野球|足球",
}


def classify(title):
    matches = [topic for topic, pattern in TOPICS.items() if re.search(pattern, title, re.I)]
    return matches[:2] or ["Society"]


def country_for(host, countries):
    # Longest suffix wins; never infer national origin just from a ccTLD.
    matches = [(len(domain), country, domain) for country in countries for domain in country["domains"]
               if host == domain or host.endswith("." + domain)]
    return max(matches, key=lambda row: row[0])[1:] if matches else (None, None)


def normalise(record, origin, seen_at, config, ingested_at):
    url = safe_url(record.get("url"))
    title = clean_text(record.get("title"))
    if not url or len(title) < 16 or len(title) > 700:
        return None
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname.removeprefix("www.")
    country, domain = country_for(host, config["countries"])
    if not country:
        return None
    if host in config.get("excludedDomains", []) or any(host.endswith("." + d) for d in config.get("excludedDomains", [])):
        return None
    # Index/author/tag pages are not news stories, even if the upstream crawler saw them.
    if parsed.path in ("", "/") or re.search(r"/(authors?|autor(?:es)?|auteurs?|kirjoittaja|tac-gia|tags?|topics?|category|categories|seccao|search|about|contact)(/|$)", parsed.path, re.I):
        return None
    if re.search(r"^(Scoop Media - New Zealand news|Breaking News|Latest News|Home Page|News Headlines)$", title, re.I):
        return None
    if re.search(r"/(list_partner|list|archive|archives)(/|$)", parsed.path, re.I) or parsed.path.rstrip("/") in ("/goodfood", "/news", "/latest-news"):
        return None
    if re.search(r"最新ニュース\s*[|｜]|Χρήσιμα Τηλέφωνα|Recipes, Restaurant Reviews, Food Guides", title, re.I):
        return None
    # Service directories, price tickers and programme homepages are not articles.
    # Keep dated podcast episodes and reported stories about these subjects.
    if re.search(r"/(foodie/restaurants|service/categories|infos-services)(/|$)", parsed.path, re.I):
        return None
    if host.endswith("radiofrance.fr") and re.fullmatch(r"/[^/]+/podcasts/[^/]+/?", parsed.path):
        return None
    if host.endswith("hurriyet.com.tr") and re.match(r"/(borsa/hisse-fiyatlari|kripto)/", parsed.path):
        return None
    if host.endswith("cnbc.com") and len([part for part in parsed.path.split("/") if part]) <= 1:
        return None
    if re.search(r"Actualités et info en direct|^Εφημερίες Νοσοκομείων\s*[-–]|^Tabela e Jogos do", title, re.I):
        return None
    captured = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
    # A concrete old date in an article URL outranks ambiguous first-seen metadata.
    path_date = re.search(r"/(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?:[/_.-]|$)", parsed.path)
    if path_date:
        try:
            stated_date = datetime(*map(int, path_date.groups()), tzinfo=timezone.utc)
            if stated_date < captured - timedelta(days=4):
                return None
        except ValueError:
            pass
    stale_season = re.match(r"\s*(20\d{2})\s+(?:March Madness|NFL season|NBA season|World Cup|Olympics)", title, re.I)
    if stale_season and int(stale_season.group(1)) < captured.year:
        return None
    date = None
    try:
        date = datetime.fromisoformat(str(record.get("date", "")).replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        # Exclude stale archive discoveries and implausible future metadata.
        if date < captured - timedelta(days=3) or date > captured + timedelta(hours=3):
            return None
        date = date.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, TypeError):
        date = None
    publisher = clean_text(record.get("outletName")) or host
    return {
        "id": "n-" + hashlib.sha256(url.encode()).hexdigest()[:14],
        "title": title, "url": url, "publisher": publisher, "publisherDomain": host,
        "publishedAt": date, "dateBasis": "published-or-first-seen", "seenAt": seen_at,
        "sourceCountry": country["name"], "sourceCountryCode": country["code"],
        "sourceRegion": country["region"], "sourceLat": country["lat"], "sourceLon": country["lon"],
        "sourceLocationBasis": "curated publisher-country attribution; approximate national marker",
        "language": {"un": "und", "iw": "he"}.get(clean_text(record.get("lang")), clean_text(record.get("lang")) or "und"), "topics": classify(title),
        "topicBasis": "headline keyword heuristic", "ingestedAt": ingested_at,
        "feed": origin, "sourceId": domain,
    }


def select_diverse(articles, limits):
    """Round-robin countries and publishers, preserving the newest available metadata."""
    articles.sort(key=lambda row: row["publishedAt"] or row["seenAt"] or "", reverse=True)
    pools = defaultdict(lambda: defaultdict(deque))
    seen_urls, seen_titles = set(), set()
    for article in articles:
        signature = re.sub(r"[^\w]", "", article["title"].casefold())
        if article["url"] in seen_urls or signature in seen_titles:
            continue
        seen_urls.add(article["url"])
        seen_titles.add(signature)
        pools[article["sourceCountryCode"]][article["sourceId"]].append(article)
    country_counts, publisher_counts = Counter(), Counter()
    selected = []
    while len(selected) < limits["maxArticles"]:
        added = False
        for code in sorted(pools):
            if country_counts[code] >= limits["maxPerCountry"]:
                continue
            eligible = [key for key, rows in pools[code].items()
                        if rows and publisher_counts[key] < limits["maxPerPublisher"]]
            if not eligible:
                continue
            key = min(eligible, key=lambda value: publisher_counts[value])
            selected.append(pools[code][key].popleft())
            country_counts[code] += 1
            publisher_counts[key] += 1
            added = True
            if len(selected) >= limits["maxArticles"]:
                break
        if not added:
            break
    return sorted(selected, key=lambda row: row["publishedAt"] or "", reverse=True)


def timestamp_from_name(name):
    match = re.search(r"(20\d{12})\.gal", name)
    return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if match else now_iso()


def collect_sample(anchor, offset, limits):
    target = anchor - timedelta(minutes=offset)
    # GAL's minute files cluster just after quarter-hour updates. Try two slots only.
    errors = []
    for minute in (2, 3):
        timestamp = target.replace(minute=(target.minute // 15) * 15 + minute, second=0)
        url = "https://data.gdeltproject.org/gdeltv3/gal/" + timestamp.strftime("%Y%m%d%H%M%S") + ".gal.json.gz"
        try:
            records = decode_gal(fetch(url, limits))
            return records, {"url": url, "status": "ok", "recordCount": len(records),
                             "observedAt": timestamp.isoformat().replace("+00:00", "Z")}
        except Exception as error:
            errors.append(f"{type(error).__name__}: {error}")
    return [], {"url": url, "status": "unavailable", "recordCount": 0, "error": "; ".join(errors),
                "observedAt": timestamp.isoformat().replace("+00:00", "Z")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "data/source-config.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/news.json")
    parser.add_argument("--input-gal", type=Path, action="append", default=[], help="Reproduce a snapshot from a local downloaded GAL gzip (repeatable)")
    parser.add_argument("--max-items", type=int, help="Override article ceiling, 80–800")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    limits = dict(config["limits"])
    if args.max_items is not None:
        if not 80 <= args.max_items <= 800:
            parser.error("--max-items must be between 80 and 800")
        limits["maxArticles"] = args.max_items
    started = now_iso()
    records_with_sources, fetches = [], []
    if args.input_gal:
        for path in args.input_gal:
            records = decode_gal(path.read_bytes())
            url = "https://data.gdeltproject.org/gdeltv3/gal/" + path.name
            meta = {"url": url, "status": "ok", "recordCount": len(records), "observedAt": timestamp_from_name(path.name)}
            fetches.append(meta)
            records_with_sources.extend((row, meta) for row in records)
    else:
        # Latest verified GDELT batch is the time anchor, never a fabricated dataset date.
        try:
            latest = fetch("https://data.gdeltproject.org/gdeltv2/lastupdate.txt", limits).decode("utf-8")
            match = re.search(r"/(20\d{12})\.", latest)
            if not match:
                raise ValueError("No batch timestamp in GDELT update index")
            anchor = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc) - timedelta(minutes=15)
        except Exception as error:
            print(f"Collection not changed: latest GDELT index unavailable ({error})", file=sys.stderr)
            return 1
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(collect_sample, anchor, offset, limits) for offset in limits["sampleOffsetsMinutes"]]
            for future in as_completed(futures):
                records, meta = future.result()
                print(f"GAL sample {meta['observedAt']}: {meta['status']} ({len(records)} metadata rows)", flush=True)
                fetches.append(meta)
                records_with_sources.extend((row, meta) for row in records)
    ingested = now_iso()
    normalised = [article for row, meta in records_with_sources
                  if (article := normalise(row, meta["url"], meta["observedAt"], config, ingested))]
    articles = select_diverse(normalised, limits)
    countries = {row["sourceCountryCode"] for row in articles}
    if len(articles) < limits["minimumArticles"] or len(countries) < limits["minimumCountries"]:
        print(f"Collection not changed: only {len(articles)} eligible stories / {len(countries)} countries; below publication floor.", file=sys.stderr)
        return 1
    counts = Counter(row["sourceId"] for row in articles)
    sources = [{"id": domain, "name": domain, "url": "https://" + domain,
                "kind": "gdelt-gal", "country": country["name"], "region": country["region"],
                "status": "observed" if counts[domain] else "not-observed-in-sample",
                "itemCount": counts[domain], "lastCheckedAt": ingested}
               for country in config["countries"] for domain in country["domains"]]
    snapshot = {"schemaVersion": 1, "generatedAt": ingested, "collectionStartedAt": started,
                "mode": "snapshot", "provider": "GDELT Article List (GAL)", "articles": articles,
                "sources": sources, "fetches": fetches,
                "coverage": {"eligibleMetadataRows": len(normalised), "sampledMetadataRows": len(records_with_sources),
                             "countries": len(countries), "publishers": len(counts),
                             "regionCounts": dict(Counter(a["sourceRegion"] for a in articles))},
                "notes": ["A bounded sample of GDELT metadata, not a census of the world or public opinion.",
                          "Dates may be publication dates or GDELT first-seen dates; they are not verified event dates.",
                          config["countryAttribution"],
                          "Original headlines and links only. No article bodies, images or summaries are copied.",
                          "Topic labels use headline keyword rules and can be incomplete, especially across languages.",
                          "An unobserved publisher means absent from these samples, not an unavailable website.",
                          "Country and publisher quotas reduce dominance but do not establish representativeness."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(args.output)
    print(f"Saved {len(articles)} headlines / {len(countries)} countries / {len(counts)} publishers to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
