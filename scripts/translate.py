#!/usr/bin/env python3
"""Add English headlines to a collection, using Claude for the ones not already cached.

Reads a news.json, fills `titleEnglish` for every article, and keeps a cache in
data/translations.json keyed by a hash of the original title so a headline is
translated once. English headlines are copied as they are. Without an API key
the script still succeeds: cached translations are applied and untranslated
headlines keep their original wording (the site shows the original in that case).

Usage:
  python3 scripts/translate.py --input work/news-candidate.json
Env:
  ANTHROPIC_API_KEY   needed for new translations
  TRANSLATE_MODEL     default claude-haiku-5-5
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "translations.json"
BATCH = 60

SYSTEM = (
    "You translate news headlines into plain, accurate English. Keep names, numbers, publisher tags and punctuation. "
    "Do not add facts, do not editorialise, do not expand abbreviations unless the headline does. If a headline is already "
    "in English, return it unchanged. Return one English headline for every id you are given."
)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def key(title):
    return hashlib.sha256(title.strip().encode("utf-8")).hexdigest()


def load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    return {"schemaVersion": 2, "updatedAt": None, "entries": {}}


def translate_batch(client, model, items):
    schema = {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "en": {"type": "string"}},
                    "required": ["id", "en"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["translations"],
        "additionalProperties": False,
    }
    lines = "\n".join(f"{a['id']}\t{a.get('language', 'und')}\t{a['title']}" for a in items)
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": "Translate each headline. Lines are: id, language code, headline.\n\n" + lines}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("translation request was refused")
    text = next(b.text for b in response.content if b.type == "text")
    return {t["id"]: t["en"].strip() for t in json.loads(text)["translations"] if t.get("en", "").strip()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA / "news.json")
    parser.add_argument("--output", type=Path, help="Defaults to overwriting --input")
    parser.add_argument("--dry-run", action="store_true", help="Apply the cache only; make no API request")
    args = parser.parse_args()
    news = json.loads(args.input.read_text())
    cache = load_cache()
    entries = cache["entries"]
    model = os.environ.get("TRANSLATE_MODEL", "claude-haiku-5-5")
    pending = []
    for a in news["articles"]:
        if a.get("language") == "en" or not a.get("language") or a.get("language") == "und" and a["title"].isascii():
            a["titleEnglish"] = a["title"]
            continue
        hit = entries.get(key(a["title"]))
        if hit:
            a["titleEnglish"] = hit["en"]
        else:
            pending.append(a)
    done = 0
    if pending and not args.dry_run and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
        except ImportError:
            print("anthropic SDK not installed; pip install anthropic", file=sys.stderr)
            return 1
        client = anthropic.Anthropic()
        for i in range(0, len(pending), BATCH):
            batch = pending[i:i + BATCH]
            try:
                out = translate_batch(client, model, batch)
            except Exception as error:  # keep the run alive; untranslated headlines fall back to the original
                print(f"translation batch failed: {type(error).__name__}: {error}", file=sys.stderr)
                continue
            for a in batch:
                en = out.get(a["id"])
                if en:
                    a["titleEnglish"] = en
                    entries[key(a["title"])] = {"en": en, "model": model, "at": now_iso(), "lang": a.get("language")}
                    done += 1
        cache["updatedAt"] = now_iso()
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n")
    elif pending:
        print(f"{len(pending)} headlines have no English yet (no key or dry run); originals will show", file=sys.stderr)
    missing = sum(1 for a in news["articles"] if not a.get("titleEnglish"))
    news["translationSummary"] = {"completedAt": now_iso(), "headlines": len(news["articles"]), "newlyTranslated": done,
                                  "withoutEnglish": missing, "model": model if done else None,
                                  "note": "AI-assisted English headlines; the publisher's original wording remains the reference."}
    out = args.output or args.input
    out.write_text(json.dumps(news, ensure_ascii=False, indent=2) + "\n")
    print(f"english headlines: {len(news['articles']) - missing}/{len(news['articles'])} ({done} newly translated, {len(entries)} cached)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
