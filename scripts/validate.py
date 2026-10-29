#!/usr/bin/env python3
"""Check that the public data files agree with each other.

Every reading fragment must cite headlines that exist, books and trajectories
that exist, and every reading must end with a 'break' rung. Exit 1 on failure.
Standard library only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
KINDS = {"observation", "interpretation", "break"}


def is_list(line):
    """True for a line of the form "A, B, C and D": three or more commas, or two commas whose
    middle items are short noun phrases (four words or fewer) and a final "X and Y" of the same kind."""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) >= 4:
        return True
    if len(parts) == 3 and " and " in parts[2]:
        inner = parts[1]
        last = parts[2].split(" and ")[0]
        return len(inner.split()) <= 4 and len(last.split()) <= 4
    return False


def load(name):
    return json.loads((DATA / name).read_text())


def main():
    errors = []
    warnings = []
    news = load("news.json")
    readings = load("readings.json")
    library = load("library.json")
    ledger = load("ledger.json") if (DATA / "ledger.json").exists() else None

    article_ids = {a["id"] for a in news["articles"]}
    saved_ids = {a["id"] for a in readings.get("sourceArticles", [])}
    book_ids = {b["id"] for b in library["books"]}
    traj_ids = {t["id"] for t in library["trajectories"]}

    for a in news["articles"]:
        if not a.get("url", "").startswith("https://"):
            errors.append(f"article {a['id']} has a non-https url")
        if not a.get("title", "").strip():
            errors.append(f"article {a['id']} has an empty title")
    if len(article_ids) != len(news["articles"]):
        errors.append("duplicate article ids in news.json")

    seen_reading_ids = set()
    for r in readings["readings"]:
        rid = r.get("id", "?")
        if rid in seen_reading_ids:
            errors.append(f"duplicate reading id {rid}")
        seen_reading_ids.add(rid)
        for key in ("line", "kicker", "claim", "rungs"):
            if not r.get(key):
                errors.append(f"reading {rid} missing {key}")
        if len(r.get("line", "")) > 140:
            errors.append(f"reading {rid} line is longer than 140 characters")
        rungs = r.get("rungs", [])
        if not rungs or rungs[-1].get("kind") != "break":
            errors.append(f"reading {rid} must end with a 'break' rung")
        if len(rungs) < 3:
            errors.append(f"reading {rid} has fewer than three rungs")
        cited = set()
        for rung in rungs:
            if rung.get("kind") not in KINDS:
                errors.append(f"reading {rid} rung {rung.get('id')} has unknown kind {rung.get('kind')}")
            if not rung.get("fragments"):
                errors.append(f"reading {rid} rung {rung.get('id')} has no fragments")
            for f in rung.get("fragments", []):
                if not f.get("label") or not f.get("text"):
                    errors.append(f"reading {rid} fragment {f.get('id')} missing label or text")
                for aid in f.get("articleIds", []):
                    if aid not in article_ids and aid not in saved_ids:
                        errors.append(f"reading {rid} fragment {f.get('id')} cites unknown article {aid}")
                    cited.add(aid)
                for bid in f.get("bookIds", []):
                    if bid not in book_ids:
                        errors.append(f"reading {rid} fragment {f.get('id')} cites unknown book {bid}")
                for tid in f.get("trajectoryIds", []):
                    if tid not in traj_ids:
                        errors.append(f"reading {rid} fragment {f.get('id')} cites unknown trajectory {tid}")
        if len(cited) < 4:
            errors.append(f"reading {rid} cites fewer than four headlines")
        if "events" in r:
            events = r["events"]
            if len(events) < 3:
                errors.append(f"reading {rid} joins fewer than three events")
            sizes, union = [], set()
            for e in events:
                known = {x for x in e.get("articleIds", []) if x in article_ids or x in saved_ids}
                if not e.get("label", "").strip() or not known:
                    errors.append(f"reading {rid} has an event with no label or no known headline")
                sizes.append(len(known)); union.update(known)
            if union and sizes and max(sizes) * 2 > len(union):
                errors.append(f"reading {rid}: one event holds more than half of its headlines")
        if readings.get("schemaVersion", 2) >= 3:
            spans = [h.get("span") for h in r.get("horizons", [])]
            if spans != ["decade", "half-century", "since-2001", "since-1945"]:
                errors.append(f"reading {rid} horizons must be decade, half-century, since-2001, since-1945 in order")
            for h in r.get("horizons", []):
                if len(h.get("text", "").split()) < 90:
                    errors.append(f"reading {rid} horizon {h.get('span')} is too short")
                for tid in h.get("trajectoryIds", []):
                    if tid not in traj_ids:
                        errors.append(f"reading {rid} horizon {h.get('span')} cites unknown trajectory {tid}")
                for bid in h.get("bookIds", []):
                    if bid not in book_ids:
                        errors.append(f"reading {rid} horizon {h.get('span')} cites unknown book {bid}")
        if "articleIds" in r and set(r["articleIds"]) != cited:
            errors.append(f"reading {rid} articleIds do not match its fragments (run freeze.py)")
        # The line says what the join shows, not the evidence. Editions before 29 Oct 2026 predate
        # this rule, so here it is a warning; oracle.py refuses a new edition that breaks it.
        if is_list(r.get("line", "")):
            warnings.append(f"reading {rid} line is a list rather than a statement of what the join shows")

    if ledger:
        for key in ("editionAt", "arrived", "stayed", "departed"):
            if key not in ledger:
                errors.append(f"ledger.json missing {key}")

    for w in warnings:
        print("△ " + w, file=sys.stderr)
    if errors:
        print("\n".join("✗ " + e for e in errors), file=sys.stderr)
        print(f"{len(errors)} problem(s)", file=sys.stderr)
        return 1
    n_frag = sum(len(f) for r in readings["readings"] for f in [sum([ru.get("fragments", []) for ru in r["rungs"]], [])])
    n_h = sum(len(r.get("horizons", [])) for r in readings["readings"])
    print(f"✓ {len(news['articles'])} headlines, {len(readings['readings'])} readings, {n_frag} fragments, {n_h} horizons, {len(book_ids)} books, {len(traj_ids)} trajectories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
