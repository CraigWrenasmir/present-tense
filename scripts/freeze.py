#!/usr/bin/env python3
"""Freeze a readings edition against the current headline collection.

Fills each reading's articleIds from its fragments and stores a snapshot of
every cited headline in readings.sourceArticles, so a reading keeps its
evidence even after the collection moves on. Standard library only.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
KEEP = ("id", "title", "titleEnglish", "url", "publisher", "publisherDomain", "publishedAt", "seenAt",
        "dateBasis", "sourceCountry", "sourceCountryCode", "sourceRegion", "sourceLat", "sourceLon", "language")


def main():
    news = json.loads((DATA / "news.json").read_text())
    readings = json.loads((DATA / "readings.json").read_text())
    by_id = {a["id"]: a for a in news["articles"]}
    previous = {a["id"]: a for a in readings.get("sourceArticles", [])}
    cited = []
    for r in readings["readings"]:
        ids = []
        for rung in r["rungs"]:
            for f in rung["fragments"]:
                for aid in f.get("articleIds", []):
                    if aid not in ids:
                        ids.append(aid)
        r["articleIds"] = ids
        cited.extend(i for i in ids if i not in cited)
    snapshot = []
    for aid in cited:
        src = by_id.get(aid) or previous.get(aid)
        if not src:
            raise SystemExit(f"cited headline {aid} is not in news.json or the previous snapshot")
        snapshot.append({k: src[k] for k in KEEP if k in src})
    readings["sourceArticles"] = snapshot
    readings.setdefault("newsGeneratedAt", news["generatedAt"])
    (DATA / "readings.json").write_text(json.dumps(readings, ensure_ascii=False, indent=2) + "\n")
    print(f"froze {len(readings['readings'])} readings with {len(snapshot)} cited headlines")


if __name__ == "__main__":
    main()
