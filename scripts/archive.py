#!/usr/bin/env python3
"""Keep every edition of narratives, so the site can show where we were yesterday.

Copies data/readings.json to data/narratives/<stamp>.json, where the stamp is
the time of the headline collection the edition read (an edition is "the
narratives in the headlines of <that time>"), and rewrites
data/narratives/index.json: one entry per edition, newest first, with each
narrative's id, kicker, line, what it joins and what it continues. Re-running
for the same collection overwrites, so a corrected edition replaces its
earlier version. Standard library only.

Usage:
  python3 scripts/archive.py             # archive the current data/readings.json
  python3 scripts/archive.py --backfill  # also walk git history for earlier editions
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "narratives"


def stamp_of(edition):
    return (edition.get("newsGeneratedAt") or edition["generatedAt"]).replace("-", "").replace(":", "")[:15]


def store(edition):
    OUT.mkdir(exist_ok=True)
    stamp = stamp_of(edition)
    path = OUT / f"{stamp}.json"
    text = json.dumps(edition, ensure_ascii=False, indent=2) + "\n"
    changed = not path.exists() or path.read_text() != text
    if changed:
        path.write_text(text)
    return stamp, changed


def summarise(edition, stamp):
    by = {a["id"]: a for a in edition.get("sourceArticles", [])}
    items = []
    for r in edition["readings"]:
        ids = r.get("articleIds") or []
        items.append({
            "id": r["id"], "kicker": r.get("kicker", ""), "line": r.get("line", ""),
            "events": len(r.get("events") or []), "headlines": len(ids),
            "countries": len({by[i]["sourceCountryCode"] for i in ids if i in by}),
            "continues": r.get("continues") or "",
            "firmness": r.get("firmness") or "",
            "watch": len(r.get("watch") or []),
        })
    return {
        "stamp": stamp, "file": f"data/narratives/{stamp}.json",
        "newsGeneratedAt": edition.get("newsGeneratedAt"), "generatedAt": edition.get("generatedAt"),
        "method": edition.get("method"), "model": edition.get("model"), "promptVersion": edition.get("promptVersion"),
        "narratives": items,
    }


def rebuild_index():
    entries = []
    for path in sorted(OUT.glob("*.json")):
        if path.name == "index.json":
            continue
        edition = json.loads(path.read_text())
        entries.append(summarise(edition, path.stem))
    entries.sort(key=lambda e: e["stamp"], reverse=True)
    (OUT / "index.json").write_text(json.dumps({"editions": entries}, ensure_ascii=False, indent=1) + "\n")
    return entries


def backfill():
    commits = subprocess.run(["git", "log", "--reverse", "--format=%H", "--", "data/readings.json"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    n = 0
    for c in commits:
        text = subprocess.run(["git", "show", f"{c}:data/readings.json"], cwd=ROOT, capture_output=True, text=True).stdout
        if not text:
            continue
        try:
            edition = json.loads(text)
        except ValueError:
            continue
        stamp, changed = store(edition)
        n += changed
        print(f"{c[:7]} -> {stamp}{' (updated)' if changed else ''}")
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backfill", action="store_true")
    args = parser.parse_args()
    if args.backfill:
        backfill()
    edition = json.loads((DATA / "readings.json").read_text())
    stamp, changed = store(edition)
    entries = rebuild_index()
    print(f"archived edition {stamp}{' (updated)' if changed else ' (unchanged)'}; {len(entries)} editions in the index")


if __name__ == "__main__":
    main()
