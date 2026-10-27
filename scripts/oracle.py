#!/usr/bin/env python3
"""Ask Claude to compose a new edition of readings from the current collection.

The oracle brief lives in this file. The output is validated against the
collection before anything is written: every cited headline, book and
trajectory must exist, every reading must end with a 'break' rung, and the
edition must contain between five and eight readings. An invalid, refused or
failed response leaves the previous readings in place.

Usage:
  python3 scripts/oracle.py            # compose and write data/readings.json
  python3 scripts/oracle.py --dry-run  # build the request, make no API call
Env:
  ANTHROPIC_API_KEY   required
  ORACLE_MODEL        default claude-opus-5-5
  ORACLE_EFFORT       default high
  ORACLE_MAX_PER_DAY  default 2 (recorded in data/oracle-state.json)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATE = DATA / "oracle-state.json"
MAX_INPUT_CHARS = 140_000

BRIEF = """You are the oracle of The Present Tense, a site that lays out one day's world headlines as a field and reads them into constellations. You are playing a Glass Bead Game with the news: you look at hundreds of headlines from dozens of countries and propose possible narratives of the present, joining a headline in Lagos to one in Taipei to one in Córdoba.

You will receive the collection: one line per headline with its id, publisher country, publisher, language, time and English headline. You will also receive a library of books and historical trajectories you may draw on, and the lines of the previous edition's readings so you do not repeat them.

Compose an edition of readings. Each reading has:
- line: one sentence the oracle speaks. Compressed, declarative, slightly strange, plain words. A claim, not a topic. Under 110 characters. No colon-headlines, no questions, no hedging, no cleverness for its own sake.
- kicker: three words in capitals separated by " / ".
- claim: two to four sentences that commit to the interpretation and say why it matters. Written for an intelligent general reader. No disclaimers.
- rungs: three to five rungs, in this order: one or two of kind "observation" (what is in the headlines, across countries), one or two of kind "interpretation" (the oracle's move: what the pattern might mean, what it rhymes with), and always, last, exactly one of kind "break" labelled "Break this reading" that makes the strongest honest case against the reading: a sampling objection, a rival explanation, a reason the pattern is an artefact of the collection or of English, or a claim that the oracle has mistaken a normal thing for a new thing. The break rung must be substantive and specific, not a generic caveat.
- each rung has one to three fragments. A fragment has a short label, a text of two to five sentences, and the ids of the headlines it rests on (observation and interpretation fragments cite at least one; break fragments may cite none). The text names publishers and countries and quotes headlines in paraphrase; it does not invent facts that are not in a headline. It may notice what a headline withholds.
- bookIds and trajectoryIds: cite a book or a trajectory only when it changes how the fragment reads. Most fragments should cite none. Never more than two per fragment.
- horizons: after the rungs, "How we got here". Exactly four, in this order, with span "decade" (the past ten years), "half-century" (the past fifty years), "since-2001" (since September 2001) and "since-1945" (since the end of the Second World War). Each has a lens of two or three capitalised words separated by " / " naming the kinds of history it draws on (for example "OIL / REVOLUTION / ALLIANCE", "DEMOGRAPHY / SQUARE / HOUSE", "CAPITAL / DISCLOSURE / WATER"), and a text of 130 to 200 words. A horizon places this day's pattern on a longer trajectory: sociological, economic, demographic, migratory, environmental, technological, legal or intellectual, whichever genuinely explain how the present arrived. Name dates, laws, prices, flows of people, institutions, books and the people who wrote them. Be concrete and specific to the reading's countries and headlines; connect at least once in each horizon back to a specific headline in the reading. Do not write a general history of the period. Do not claim authority: a horizon is a trajectory, not a verdict, and it may say where the trajectory is contested. Each horizon cites one to four trajectories and zero to two books from the library, chosen because they are the moments and arguments the text actually stands on; if the library lacks the moment you need, name it in the text and cite nothing. Use only facts you are confident of; where the decade's recent events are known to you only from the headlines, say "by these headlines".

Rules of the game:
- Prefer connections that cross countries, languages and registers: a market story with a church story, a sport story with a protest story, a material object that appears in several roles. Framing comparisons (how different countries report the same event) are one kind of reading, not the only kind. Vary the kinds across the edition.
- Commit. The structure already contains the doubt (the break rung). Do not write "this does not establish" or "may or may not" inside fragments.
- Use only headline ids from the collection. Use only book and trajectory ids from the library.
- Each reading should cite between six and twenty-five headlines across at least four countries.
- Do not repeat the previous edition's lines or claims. If a thread continues, say what has changed.
- Write in plain British English. Use hyphens, never dashes. Capitalise proper nouns only.
- Across the edition the horizons must not repeat each other: if two readings share a decade, they must read it through different lenses and different moments.

Return JSON matching the schema. Compose between five and eight readings."""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


SCHEMA = {
    "type": "object",
    "properties": {
        "readings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "kebab-case, unique"},
                    "line": {"type": "string"},
                    "kicker": {"type": "string"},
                    "claim": {"type": "string"},
                    "rungs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "kind": {"type": "string", "enum": ["observation", "interpretation", "break"]},
                                "label": {"type": "string"},
                                "fragments": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "label": {"type": "string"},
                                            "text": {"type": "string"},
                                            "articleIds": {"type": "array", "items": {"type": "string"}},
                                            "bookIds": {"type": "array", "items": {"type": "string"}},
                                            "trajectoryIds": {"type": "array", "items": {"type": "string"}},
                                        },
                                        "required": ["id", "label", "text", "articleIds", "bookIds", "trajectoryIds"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["id", "kind", "label", "fragments"],
                            "additionalProperties": False,
                        },
                    },
                },
                "horizons": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "span": {"type": "string", "enum": ["decade", "half-century", "since-2001", "since-1945"]},
                            "label": {"type": "string"},
                            "lens": {"type": "string"},
                            "text": {"type": "string"},
                            "trajectoryIds": {"type": "array", "items": {"type": "string"}},
                            "bookIds": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["span", "label", "lens", "text", "trajectoryIds", "bookIds"],
                        "additionalProperties": False,
                    },
                },
                "required": ["id", "line", "kicker", "claim", "rungs", "horizons"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["readings"],
    "additionalProperties": False,
}


def build_request(news, library, previous):
    lines = []
    for a in news["articles"]:
        t = (a.get("titleEnglish") or a["title"]).replace("\n", " ").strip()
        lines.append(f"{a['id']} | {a['sourceCountry']} | {a['publisher']} | {a.get('language', 'und')} | {(a.get('publishedAt') or a.get('seenAt') or '')[:16]} | {t}")
    collection = "\n".join(lines)
    if len(collection) > MAX_INPUT_CHARS:
        collection = collection[:MAX_INPUT_CHARS]
    books = "\n".join(f"{b['id']} | {b['author']}, {b['title']} ({b['year']}) | asks: {b['question']}" for b in library["books"])
    trajs = "\n".join(f"{t['id']} | {t['when']} | {t['title']} | {t['note']}" for t in sorted(library["trajectories"], key=lambda t: (re.search(r"\d{4}", t["when"]) or re.search(r"\d{4}", "0000")).group(0)))
    prev = "\n".join(f"- {r['line']}" for r in (previous or {}).get("readings", [])) or "(none)"
    user = (
        f"THE COLLECTION, gathered {news['generatedAt']} ({len(news['articles'])} headlines):\n{collection}\n\n"
        f"THE LIBRARY, books:\n{books}\n\nTHE LIBRARY, trajectories:\n{trajs}\n\n"
        f"THE PREVIOUS EDITION'S LINES:\n{prev}\n\nCompose this edition."
    )
    return user


def validate(edition, news, library):
    ids = {a["id"] for a in news["articles"]}
    books = {b["id"] for b in library["books"]}
    trajs = {t["id"] for t in library["trajectories"]}
    problems = []
    readings = edition.get("readings", [])
    if not 5 <= len(readings) <= 8:
        problems.append(f"{len(readings)} readings (need 5 to 8)")
    seen = set()
    for r in readings:
        if r["id"] in seen:
            problems.append(f"duplicate reading id {r['id']}")
        seen.add(r["id"])
        rungs = r["rungs"]
        if not rungs or rungs[-1]["kind"] != "break" or sum(1 for x in rungs if x["kind"] == "break") != 1:
            problems.append(f"{r['id']}: must end with exactly one break rung")
        cited, countries = set(), set()
        for rung in rungs:
            if not rung["fragments"]:
                problems.append(f"{r['id']}/{rung['id']}: no fragments")
            for f in rung["fragments"]:
                bad = [x for x in f["articleIds"] if x not in ids]
                if bad:
                    problems.append(f"{r['id']}/{f['id']}: unknown headline ids {bad[:3]}")
                if rung["kind"] != "break" and not f["articleIds"]:
                    problems.append(f"{r['id']}/{f['id']}: cites nothing")
                for b in f["bookIds"]:
                    if b not in books:
                        problems.append(f"{r['id']}/{f['id']}: unknown book {b}")
                for t in f["trajectoryIds"]:
                    if t not in trajs:
                        problems.append(f"{r['id']}/{f['id']}: unknown trajectory {t}")
                cited.update(x for x in f["articleIds"] if x in ids)
        by = {a["id"]: a for a in news["articles"]}
        countries = {by[x]["sourceCountryCode"] for x in cited}
        if len(cited) < 6 or len(countries) < 4:
            problems.append(f"{r['id']}: cites {len(cited)} headlines from {len(countries)} countries (need 6 and 4)")
        for key in ("line", "kicker", "claim"):
            if not r.get(key, "").strip():
                problems.append(f"{r['id']}: empty {key}")
        spans = [h.get("span") for h in r.get("horizons", [])]
        if spans != ["decade", "half-century", "since-2001", "since-1945"]:
            problems.append(f"{r['id']}: horizons must be decade, half-century, since-2001, since-1945 in order (got {spans})")
        for h in r.get("horizons", []):
            words = len(h.get("text", "").split())
            if words < 90:
                problems.append(f"{r['id']}/{h.get('span')}: horizon too short ({words} words)")
            if not h.get("trajectoryIds"):
                problems.append(f"{r['id']}/{h.get('span')}: horizon cites no trajectory")
            for t in h.get("trajectoryIds", []):
                if t not in trajs:
                    problems.append(f"{r['id']}/{h.get('span')}: unknown trajectory {t}")
            for b in h.get("bookIds", []):
                if b not in books:
                    problems.append(f"{r['id']}/{h.get('span')}: unknown book {b}")
        if len(r.get("line", "")) > 140:
            problems.append(f"{r['id']}: line too long")
    return problems


def allowed_today():
    state = json.loads(STATE.read_text()) if STATE.exists() else {"day": None, "attempts": 0, "history": []}
    today = now_iso()[:10]
    if state.get("day") != today:
        state = {"day": today, "attempts": 0, "history": state.get("history", [])[-30:]}
    cap = int(os.environ.get("ORACLE_MAX_PER_DAY", "2"))
    return state, state["attempts"] < cap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    news = json.loads((DATA / "news.json").read_text())
    library = json.loads((DATA / "library.json").read_text())
    previous = json.loads((DATA / "readings.json").read_text()) if (DATA / "readings.json").exists() else None
    model = os.environ.get("ORACLE_MODEL", "claude-opus-5-5")
    effort = os.environ.get("ORACLE_EFFORT", "high")
    user = build_request(news, library, previous)
    if args.dry_run:
        print(f"dry run: {len(user):,} characters of input for {model}; no request made")
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; readings unchanged", file=sys.stderr)
        return 1
    state, ok = allowed_today()
    if not ok:
        print(f"oracle already ran {state['attempts']} time(s) today; readings unchanged", file=sys.stderr)
        return 1
    state["attempts"] += 1
    state["history"].append({"at": now_iso(), "model": model, "outcome": "started"})
    STATE.write_text(json.dumps(state, indent=1) + "\n")
    try:
        import anthropic
    except ImportError:
        print("anthropic SDK not installed; pip install anthropic", file=sys.stderr)
        return 1
    client = anthropic.Anthropic()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=64000,
            system=BRIEF,
            thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": user}],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.RateLimitError as error:
        return fail(state, f"rate limited: {error}")
    except anthropic.APIStatusError as error:
        return fail(state, f"API error {error.status_code}: {error.message}")
    except anthropic.APIConnectionError as error:
        return fail(state, f"connection error: {error}")
    if response.stop_reason == "refusal":
        return fail(state, "the request was refused")
    if response.stop_reason == "max_tokens":
        return fail(state, "the response was cut off")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        edition = json.loads(text)
    except ValueError as error:
        return fail(state, f"response was not JSON: {error}")
    problems = validate(edition, news, library)
    if problems:
        return fail(state, "edition rejected: " + "; ".join(problems[:8]))
    out = {
        "schemaVersion": 3,
        "generatedAt": now_iso(),
        "newsGeneratedAt": news["generatedAt"],
        "method": "claude-api",
        "model": response.model,
        "promptVersion": "oracle-2",
        "usage": {"input": response.usage.input_tokens, "output": response.usage.output_tokens},
        "notes": [
            "Edition composed by Claude from the collected headlines, reading titles and metadata only.",
            "Each reading commits to a claim. The last rung of every reading argues against it. Read both.",
            "Connections are the oracle's, not the publishers'. Follow any headline to the original report before repeating it.",
            "Each reading ends with 'How we got here': four horizons, the past decade, the past fifty years, since September 2001 and since 1945, that place the day's pattern on longer trajectories. They are a trajectory, not a verdict.",
            "Books and trajectories appear only where they change how a fragment or a horizon reads.",
        ],
        "readings": edition["readings"],
    }
    (DATA / "readings.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    state["history"][-1]["outcome"] = "ok"
    state["history"][-1]["usage"] = out["usage"]
    STATE.write_text(json.dumps(state, indent=1) + "\n")
    print(f"composed {len(out['readings'])} readings with {model}; {out['usage']['input']} in / {out['usage']['output']} out tokens")
    return 0


def fail(state, message):
    state["history"][-1]["outcome"] = message[:200]
    STATE.write_text(json.dumps(state, indent=1) + "\n")
    print(f"oracle: {message}; readings unchanged", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
