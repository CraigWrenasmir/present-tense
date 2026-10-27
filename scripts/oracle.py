#!/usr/bin/env python3
"""Ask Claude to compose a new edition of readings from the current collection.

The writing brief lives in this file. The output is validated against the
collection before anything is written: every cited headline, book and
trajectory must exist, every reading must end with a 'break' rung, and the
edition must contain five readings (four to six accepted). An invalid, refused or
failed response leaves the previous readings in place.

The request goes through the Message Batches API, which runs the same model at
half the price. A run submits the batch, waits up to ORACLE_WAIT_MINUTES for it,
and if it has not finished leaves it pending in data/oracle-pending.json for the
next run to collect. The collection the batch was asked about is stored with it,
so the readings are frozen against the headlines they actually read.

Usage:
  python3 scripts/oracle.py            # collect a pending edition, or submit a new one and wait
  python3 scripts/oracle.py --collect  # only collect a pending edition (no submission)
  python3 scripts/oracle.py --submit   # only submit (no waiting)
  python3 scripts/oracle.py --dry-run  # build the request, make no API call
  python3 scripts/oracle.py --recover BATCH_ID  # adopt a finished batch against the current collection
                                       # (for an edition the validator wrongly refused; data/news.json
                                       # must still be the collection that batch was asked about)
Env:
  ANTHROPIC_API_KEY     required
  ORACLE_MODEL          default claude-opus-5-5
  ORACLE_EFFORT         default high
  ORACLE_MAX_PER_DAY    default 2 submissions (recorded in data/oracle-state.json)
  ORACLE_WAIT_MINUTES   default 25
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATE = DATA / "oracle-state.json"
PENDING = DATA / "oracle-pending.json"
KEEP = ("id", "title", "titleEnglish", "url", "publisher", "publisherDomain", "publishedAt", "seenAt",
        "dateBasis", "sourceCountry", "sourceCountryCode", "sourceRegion", "sourceLat", "sourceLon", "language")
MAX_INPUT_CHARS = 140_000

BRIEF = """You write the narratives of The Present Tense, a site that lays out one day's world headlines as a field and shows, along the bottom of the page, the narratives that run through them. You look at hundreds of headlines from dozens of countries and describe, in plain language, patterns that connect headlines across countries: a story in Lagos with one in Taipei with one in Córdoba.

You will receive the collection: one line per headline with its id, publisher country, publisher, language, time and English headline. You will also receive a library of books and historical trajectories you may draw on, and the lines of the previous edition's narratives so you do not repeat them.

Compose an edition of narratives. Each narrative has:
- line: one plain sentence that says what is happening across these headlines. Descriptive and specific: who, what, where. A reader should know what the narrative is about from the line alone, before opening it. At most 110 characters, counted strictly; shorten by dropping a clause, not by compressing into an image. No metaphor, no aphorism, no wordplay, no paradox, no colon-headlines, no questions, no hedging. Write "Savers in Kenya, China and Indonesia are moving money out of reach of the tax office, and governments are offering amnesties", not "Money is slipping into dollars, gold and trusts, and the state is answering with discounts".
- kicker: three plain words in capitals separated by " / " that name the subjects of the narrative, for example "TAX / SAVINGS / AMNESTY" or "DATA CENTRES / LAND / WATER". Subjects, not images.
- claim: two to four sentences that say what connects the headlines and why it matters. Written for an intelligent general reader in plain descriptive prose. Commit to the interpretation. No disclaimers, and no closing flourish: do not end a paragraph on an epigram or a line designed to be quoted.
- rungs: three to five rungs, in this order: one or two of kind "observation" (what the headlines say, across countries), one or two of kind "interpretation" (what might connect them: what the pattern might mean, what it resembles), and always, last, exactly one of kind "break" labelled "The case against" that makes the strongest honest case against the narrative: a sampling objection, a rival explanation, a reason the pattern is an artefact of the collection or of English, or a reason you have mistaken a normal thing for a new thing. The break rung must be substantive and specific, not a generic caveat. Observation and interpretation rungs have plain descriptive labels of two to six words saying what they cover ("Four workplace deaths", "Where the money is going"), not titles or images ("Two doors", "The counter goes quiet").
- each rung has one to three fragments. A fragment has a short plain label, a text of two to five sentences, and the ids of the headlines it rests on (observation and interpretation fragments cite at least one; break fragments may cite none). The text names publishers and countries and quotes headlines in paraphrase; it does not invent facts that are not in a headline. It may notice what a headline withholds.
- bookIds and trajectoryIds: cite a book or a trajectory only when it changes how the fragment reads. Most fragments should cite none. Never more than two per fragment.
- horizons: after the rungs, "How we got here". Exactly four, in this order, with span "decade" (the past ten years), "half-century" (the past fifty years), "since-2001" (since September 2001) and "since-1945" (since the end of the Second World War). Each has a lens of two or three capitalised words separated by " / " naming the kinds of history it draws on (for example "OIL / REVOLUTION / ALLIANCE", "DEMOGRAPHY / HOUSING / PROTEST", "CAPITAL / DISCLOSURE / WATER"), and a text of 130 to 200 words. A horizon places this day's pattern on a longer trajectory: sociological, economic, demographic, migratory, environmental, technological, legal or intellectual, whichever genuinely explain how the present arrived. Name dates, laws, prices, flows of people, institutions, books and the people who wrote them. Be concrete and specific to the narrative's countries and headlines; connect at least once in each horizon back to a specific headline in the narrative. Do not write a general history of the period. Do not claim authority: a horizon is a trajectory, not a verdict, and it may say where the trajectory is contested. Each horizon cites one to four trajectories and zero to two books from the library, chosen because they are the moments and arguments the text actually stands on; if the library lacks the moment you need, name it in the text and cite nothing. Use only facts you are confident of; where the decade's recent events are known to you only from the headlines, say "by these headlines".

Language. This matters as much as the structure:
- Plain spoken and descriptive throughout, in every field. Say what is reported, where, by whom, and how it connects. Prefer the concrete noun to the image and the ordinary word to the striking one. Short sentences are fine. Numbers, dates, names and institutions are the material.
- No metaphor and no personification: money does not "slip", clouds do not "come down", states do not "answer". No aphorisms, no paradoxes, no rhetorical questions, no lists of three for rhythm, no sentence built to be quoted. If a sentence would be admired for its style, rewrite it for its content.
- The intelligence of the edition lives in the connections and the evidence, not in the phrasing. A good narrative is one a careful reader could restate in their own words without loss.

Rules of the game:
- Prefer connections that cross countries, languages and registers: a market story with a church story, a sport story with a protest story, a material object that appears in several roles. Framing comparisons (how different countries report the same event) are one kind of narrative, not the only kind. Vary the kinds across the edition.
- Commit. The structure already contains the doubt (the break rung). Do not write "this does not establish" or "may or may not" inside fragments.
- Use only headline ids from the collection. Use only book and trajectory ids from the library.
- Each narrative should cite between six and twenty-five headlines across at least four countries.
- Do not repeat the previous edition's lines or claims. If a thread continues, say what has changed.
- Write in plain British English. Use hyphens, never dashes. Capitalise proper nouns only.
- Across the edition the horizons must not repeat each other: if two narratives share a decade, they must read it through different lenses and different moments.

Return JSON matching the schema (its top-level key is still called "readings"; each item is one narrative). Compose five narratives: fewer, fuller and better evidenced rather than more."""


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
    if not 4 <= len(readings) <= 6:
        problems.append(f"{len(readings)} readings (asked for five)")
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
            for t in h.get("trajectoryIds", []):
                if t not in trajs:
                    problems.append(f"{r['id']}/{h.get('span')}: unknown trajectory {t}")
            for b in h.get("bookIds", []):
                if b not in books:
                    problems.append(f"{r['id']}/{h.get('span')}: unknown book {b}")
        if len(r.get("line", "")) > 140:
            problems.append(f"{r['id']}: line too long")
    return problems


def load_state():
    state = json.loads(STATE.read_text()) if STATE.exists() else {"day": None, "attempts": 0, "history": []}
    today = now_iso()[:10]
    if state.get("day") != today:
        state = {"day": today, "attempts": 0, "history": state.get("history", [])[-30:]}
    return state


def save_state(state):
    STATE.write_text(json.dumps(state, indent=1) + "\n")


def note(state, message, **extra):
    entry = {"at": now_iso(), "note": message[:300]}
    entry.update(extra)
    state.setdefault("history", []).append(entry)
    save_state(state)


def request_params(model, effort, user):
    return {
        "model": model,
        "max_tokens": 64000,
        "system": BRIEF,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        "messages": [{"role": "user", "content": user}],
    }


def submit(client, state, news, library, previous, model, effort):
    cap = int(os.environ.get("ORACLE_MAX_PER_DAY") or "2")
    if state["attempts"] >= cap:
        print(f"oracle already submitted {state['attempts']} time(s) today; nothing sent", file=sys.stderr)
        return None
    user = build_request(news, library, previous)
    try:
        batch = client.messages.batches.create(requests=[{"custom_id": "edition", "params": request_params(model, effort, user)}])
    except anthropic.APIError as error:
        state["attempts"] += 1
        note(state, f"submission failed: {error}")
        print(f"oracle: submission failed: {error}", file=sys.stderr)
        return None
    pending = {
        "batchId": batch.id,
        "submittedAt": now_iso(),
        "model": model,
        "effort": effort,
        "newsGeneratedAt": news["generatedAt"],
        "articles": [{k: a[k] for k in KEEP if k in a} for a in news["articles"]],
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False) + "\n")
    state["attempts"] += 1
    note(state, "submitted", batchId=batch.id)
    print(f"submitted batch {batch.id} for the collection of {news['generatedAt']} ({len(news['articles'])} headlines) to {model}")
    return pending


def collect(client, state, pending, library):
    """Returns True when the pending batch is finished with (written or failed), False while it is still running."""
    try:
        batch = client.messages.batches.retrieve(pending["batchId"])
    except anthropic.APIError as error:
        print(f"oracle: could not retrieve batch {pending['batchId']}: {error}", file=sys.stderr)
        return False
    if batch.processing_status != "ended":
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(pending["submittedAt"].replace("Z", "+00:00"))).total_seconds() / 3600
        if age_h > 26:
            PENDING.unlink(missing_ok=True)
            note(state, f"batch {pending['batchId']} abandoned after {age_h:.0f} hours")
            print("oracle: pending batch abandoned after a day; readings unchanged", file=sys.stderr)
            return True
        print(f"batch {pending['batchId']} still {batch.processing_status} ({age_h * 60:.0f} minutes); readings unchanged for now")
        return False
    result = next((r for r in client.messages.batches.results(pending["batchId"]) if r.custom_id == "edition"), None)
    PENDING.unlink(missing_ok=True)
    if result is None or result.result.type != "succeeded":
        kind = result.result.type if result else "missing"
        detail = describe_error(result.result) if result else ""
        return fail(state, f"batch {kind}: {detail}".strip())
    message = result.result.message
    if message.stop_reason == "refusal":
        return fail(state, "the request was refused")
    if message.stop_reason == "max_tokens":
        return fail(state, "the response was cut off")
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        edition = json.loads(text)
    except ValueError as error:
        return fail(state, f"response was not JSON: {error}")
    snapshot_news = {"generatedAt": pending["newsGeneratedAt"], "articles": pending["articles"]}
    problems = validate(edition, snapshot_news, library)
    if problems:
        return fail(state, "edition rejected: " + "; ".join(problems[:8]))
    by_id = {a["id"]: a for a in pending["articles"]}
    cited = []
    for r in edition["readings"]:
        ids = []
        for rung in r["rungs"]:
            for f in rung["fragments"]:
                for aid in f.get("articleIds", []):
                    if aid not in ids:
                        ids.append(aid)
        r["articleIds"] = ids
        cited.extend(i for i in ids if i not in cited)
    usage = {"input": message.usage.input_tokens, "output": message.usage.output_tokens, "tier": "batch"}
    out = {
        "schemaVersion": 3,
        "generatedAt": now_iso(),
        "newsGeneratedAt": pending["newsGeneratedAt"],
        "method": "claude-api-batch",
        "model": message.model,
        "promptVersion": "narrative-3",
        "usage": usage,
        "notes": [
            "Edition composed by Claude from the collected headlines, reading titles and metadata only.",
            "Each narrative commits to a claim. The last rung of every narrative is the case against it. Read both.",
            "Each narrative ends with 'How we got here': four horizons, the past decade, the past fifty years, since September 2001 and since 1945, that place the day's pattern on longer trajectories. They are a trajectory, not a verdict.",
            "The connections are made by the model, not by the publishers. Follow any headline to the original report before repeating it.",
            "Books and trajectories appear only where they change how a fragment or a horizon reads.",
        ],
        "sourceArticles": [by_id[i] for i in cited],
        "readings": edition["readings"],
    }
    (DATA / "readings.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    note(state, "ok", batchId=pending["batchId"], usage=usage)
    print(f"composed {len(out['readings'])} readings with {message.model} (batch); {usage['input']} in / {usage['output']} out tokens")
    return True


def describe_error(res):
    err = getattr(res, "error", None)
    if err is None:
        return ""
    try:
        return json.dumps(err.model_dump() if hasattr(err, "model_dump") else err, default=str)[:600]
    except Exception:
        return repr(err)[:600]


def inspect_batch(client, batch_id):
    batch = client.messages.batches.retrieve(batch_id)
    print(f"batch {batch.id}: {batch.processing_status}; counts {batch.request_counts}")
    if batch.processing_status != "ended":
        return 0
    for r in client.messages.batches.results(batch_id):
        print(f"- {r.custom_id}: {r.result.type}")
        if r.result.type == "succeeded":
            m = r.result.message
            print(f"  stop_reason={m.stop_reason} model={m.model} usage={m.usage}")
        else:
            print("  " + describe_error(r.result))
    return 0


def fail(state, message):
    note(state, message)
    print(f"oracle: {message}; readings unchanged", file=sys.stderr)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--collect", action="store_true", help="Only collect a pending edition")
    parser.add_argument("--submit", action="store_true", help="Only submit; do not wait")
    parser.add_argument("--inspect", metavar="BATCH_ID", help="Print the status and result of a batch, then exit")
    parser.add_argument("--recover", metavar="BATCH_ID", help="Adopt a finished batch against the current collection")
    args = parser.parse_args()
    news = json.loads((DATA / "news.json").read_text())
    library = json.loads((DATA / "library.json").read_text())
    previous = json.loads((DATA / "readings.json").read_text()) if (DATA / "readings.json").exists() else None
    model = os.environ.get("ORACLE_MODEL") or "claude-opus-5-5"
    effort = os.environ.get("ORACLE_EFFORT") or "high"
    wait = float(os.environ.get("ORACLE_WAIT_MINUTES") or "25")
    if args.dry_run:
        user = build_request(news, library, previous)
        print(f"dry run: {len(user):,} characters of input for {model} via the batch API; no request made")
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; readings unchanged", file=sys.stderr)
        return 1
    try:
        global anthropic
        import anthropic
    except ImportError:
        print("anthropic SDK not installed; pip install anthropic", file=sys.stderr)
        return 1
    client = anthropic.Anthropic()
    if args.inspect:
        return inspect_batch(client, args.inspect)
    state = load_state()
    if args.recover:
        pending = {
            "batchId": args.recover, "submittedAt": now_iso(), "model": model, "effort": effort,
            "newsGeneratedAt": news["generatedAt"],
            "articles": [{k: a[k] for k in KEEP if k in a} for a in news["articles"]],
        }
        note(state, f"recovering batch {args.recover} against the collection of {news['generatedAt']}")
        done = collect(client, state, pending, library)
        save_state(state)
        return 0 if done else 1
    pending = json.loads(PENDING.read_text()) if PENDING.exists() else None
    if pending:
        done = collect(client, state, pending, library)
        if not done and not args.collect and not args.submit:
            done = wait_for(client, state, pending, library, wait)
        return 0
    if args.collect:
        print("no pending edition to collect")
        return 0
    pending = submit(client, state, news, library, previous, model, effort)
    if not pending:
        return 1
    if args.submit:
        return 0
    wait_for(client, state, pending, library, wait)
    return 0


def wait_for(client, state, pending, library, minutes):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(45)
        if collect(client, state, pending, library):
            return True
    print(f"batch {pending['batchId']} not finished after {minutes:.0f} minutes; the next run will collect it")
    return False


if __name__ == "__main__":
    raise SystemExit(main())
