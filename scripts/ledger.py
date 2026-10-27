#!/usr/bin/env python3
"""Compare the new collection with the previous one and write the tide ledger.

The ledger records what arrived, what stayed and what departed between the
previous edition and this one, by headline id and by publisher country, and
which configured countries fell silent. Previous editions are kept under
data/editions/. Standard library only.

Usage:
  python3 scripts/ledger.py                 # compare data/news.json with data/editions/latest
  python3 scripts/ledger.py --previous P    # compare with an explicit previous news.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EDITIONS = DATA / "editions"
KEEP_EDITIONS = 14
SUMMARY_KEYS = ("id", "title", "titleEnglish", "url", "publisher", "sourceCountry", "sourceCountryCode", "sourceRegion", "language", "publishedAt", "seenAt")


def signature(title):
    return re.sub(r"[^\w]", "", (title or "").casefold())


def slim(a):
    return {k: a.get(k) for k in SUMMARY_KEYS if k in a}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, help="A previous news.json to compare against")
    parser.add_argument("--current", type=Path, default=DATA / "news.json")
    parser.add_argument("--output", type=Path, default=DATA / "ledger.json")
    parser.add_argument("--archive", action="store_true", help="Also store the current edition under data/editions/")
    args = parser.parse_args()

    current = json.loads(args.current.read_text())
    config = json.loads((DATA / "source-config.json").read_text())
    previous = None
    previous_path = args.previous
    if previous_path is None and EDITIONS.exists():
        candidates = sorted(EDITIONS.glob("*.json"))
        if candidates:
            previous_path = candidates[-1]
    if previous_path and previous_path.exists():
        previous = json.loads(previous_path.read_text())
        if previous.get("generatedAt") == current.get("generatedAt"):
            previous = None  # same edition archived already

    cur = {a["id"]: a for a in current["articles"]}
    cur_sigs = {signature(a["title"]): a["id"] for a in current["articles"]}
    arrived, stayed, departed = [], [], []
    if previous:
        prev = {a["id"]: a for a in previous["articles"]}
        prev_sigs = {signature(a["title"]): a["id"] for a in previous["articles"]}
        for aid, a in cur.items():
            if aid in prev or signature(a["title"]) in prev_sigs:
                stayed.append(aid)
            else:
                arrived.append(aid)
        for pid, a in prev.items():
            if pid not in cur and signature(a["title"]) not in cur_sigs:
                departed.append(slim(a))
    else:
        arrived = list(cur)

    observed = Counter(a["sourceCountryCode"] for a in current["articles"])
    prev_observed = Counter(a["sourceCountryCode"] for a in previous["articles"]) if previous else Counter()
    countries = []
    for c in config["countries"]:
        code = c["code"]
        now, before = observed.get(code, 0), prev_observed.get(code, 0)
        state = "silent" if now == 0 else ("new-voice" if previous and before == 0 else "heard")
        if previous and now == 0 and before > 0:
            state = "fell-silent"
        countries.append({"code": code, "name": c["name"], "region": c["region"], "lat": c["lat"], "lon": c["lon"],
                          "now": now, "before": before, "state": state})

    ledger = {
        "schemaVersion": 1,
        "editionAt": current["generatedAt"],
        "previousAt": previous["generatedAt"] if previous else None,
        "counts": {"now": len(cur), "before": len(previous["articles"]) if previous else 0,
                   "arrived": len(arrived), "stayed": len(stayed), "departed": len(departed)},
        "arrived": arrived,
        "stayed": stayed,
        "departed": departed,
        "countries": countries,
        "notes": [
            "Arrived, stayed and departed compare headline ids and normalised titles between two collections of the same bounded sample.",
            "A departed headline was not re-sampled; it was not necessarily taken down.",
            "A silent country has configured publishers that returned nothing in this sample. It is a gap in our listening, not a silence in the country.",
        ],
    }
    args.output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    print(f"ledger: {len(arrived)} arrived, {len(stayed)} stayed, {len(departed)} departed; previous {ledger['previousAt']}")

    if args.archive:
        EDITIONS.mkdir(exist_ok=True)
        stamp = re.sub(r"[^\dT]", "", current["generatedAt"])[:15]
        archive = {"generatedAt": current["generatedAt"], "articles": [slim(a) for a in current["articles"]]}
        (EDITIONS / f"{stamp}.json").write_text(json.dumps(archive, ensure_ascii=False) + "\n")
        for old in sorted(EDITIONS.glob("*.json"))[:-KEEP_EDITIONS]:
            old.unlink()
        print(f"archived edition {stamp}")


if __name__ == "__main__":
    main()
