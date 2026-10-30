#!/usr/bin/env python3
"""The Chronicle: a running account of where things stand, by these headlines, revised after each edition.

Once a day, after a new edition of narratives has been composed, the model is
given the previous Chronicle, the recent editions (each narrative's id, line,
kicker and what it continues) and today's edition in detail, and returns the
whole Chronicle revised: where things stand, what moved, what fell silent, one
paragraph per living thread, the case against, and what changed in the Chronicle
itself. Every version is kept under data/chronicle/ so the account's own history
can be read. Input is the narratives, not the headlines, so a revision costs
about a tenth of an edition. The request goes straight to the Messages API
(streamed) rather than through a batch, because it is small and the page waits
for it.

Usage:
  python3 scripts/chronicle.py            # revise if the current edition has not been chronicled
  python3 scripts/chronicle.py --force    # revise even if it has
  python3 scripts/chronicle.py --dry-run  # build the request, make no API call
Env:
  ANTHROPIC_API_KEY       required
  CHRONICLE_MODEL         default claude-opus-5-5
  CHRONICLE_EFFORT        default high
  CHRONICLE_MAX_PER_DAY   default 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "chronicle"
CURRENT = DATA / "chronicle.json"
RECORD = DATA / "record.json"
WATCH = DATA / "watch.json"
STATE = DATA / "chronicle-state.json"
RECENT_EDITIONS = 30
PRUNE_SILENT_AFTER = 14  # editions


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


BRIEF = """You keep the Chronicle of The Present Tense. The site lays out one day's world headlines as a field and publishes, once a day, three to five narratives: each an idea that joins unlike events in that day's headlines, with its evidence and the case against it. Every edition is kept, and where a narrative carries on one from the edition before it says so. The Chronicle is the zoomed-out view of all this: a running account of where things stand and which way they have been moving, by these headlines, over days and weeks. It is revised after each edition, not added to, so it always reads as a current understanding. Every version is kept, so readers can also see how the understanding changed.

You will receive the previous Chronicle (or none, the first time), the recent editions in brief (for each narrative: edition stamp, id, kicker, line, and the id of the narrative it continues, if any), today's edition in detail, and the ledger of expectations: the things earlier narratives said to watch for, which of them were kept or failed since the previous Chronicle and against which headline, and which are still open. Return the whole Chronicle, revised.

The Chronicle has:
- standing: three to five plain sentences on where things stand today by these headlines. Name the places, the prices, the people and the institutions. Not "the world is anxious"; rather "fuel refined from oil has been short in four countries for three days, Brazil's defeated right is leaving for the United States, and public schemes in six countries are reported as falling short".
- moved: one to four short items, one or two sentences each, saying what moved since the previous Chronicle: a thread that grew, a thread that turned, a join that was confirmed or broke.
- silent: zero to four short items on what fell silent: a thread no narrative has touched in the last two or three editions. Say, where you can, whether that is likely the world moving on or the collection's sample.
- threads: the living account, one entry per thread. A thread is a run of narratives across editions that follow the same join or the same events. Each has: key (kebab-case, stable: keep the previous Chronicle's keys for threads that continue); label (three to eight plain words naming the thread); status "live" or "silent"; since (the stamp of the first edition in the thread); lastSeen (the stamp of the last edition with a narrative in it); narratives (every narrative in the thread, oldest first, as edition stamp and id); text (60 to 140 words, dated, saying where this thread stands and how it has moved across its editions: "On 27 October the join was fuel prices at the pump; by the 28th it had reached jet fuel, bitumen and subsidy formulas"); direction (one plain sentence on the direction it has been moving, or an empty string if it has not moved).
- withdrawn: the list of interpretations the Chronicle once held and no longer holds. Carry forward every item from the previous Chronicle exactly as it was, and add an item whenever this revision drops or reverses something the previous version said: a thread that turned out to be two, a direction that reversed, a join that broke. Each item has held (the interpretation, one plain sentence, as it was held), undone (why it no longer holds, one or two sentences, by these headlines) and stamp (today's edition stamp). Items are never removed or softened; this list is the record of being wrong.
- caseAgainst: one paragraph on why this Chronicle may be wrong: the sample of publishers and the caps on it, the fact that continuity between days is partly produced by the brief that asks for it, the pull of your own earlier versions, and anything specific to this day.
- line: one plain sentence, at most 170 characters, saying what this day is in the longer story since 1945, by these headlines. It is kept in a record that is never revised, one line per edition, so write it to be read in a year beside the lines of every other day: dated where a date helps ("Eight months into the Iran war, ..."), concrete, naming the thing that marks the day, and not a summary of the five narratives. No metaphor, no aphorism, no sentence written to be quoted; a sentence a careful reader could check against the Chronicle.
- revision: one to three sentences on what changed in the Chronicle itself since its previous version: threads begun, threads ended, the standing rewritten, a direction reversed. The first time, say that this is the first version.

Rules:
- The ledger of expectations is evidence about the threads. Where an expectation was kept or failed, say so in the thread's text or in moved, dated, with what the headline reported; a failed expectation is a reason to doubt the thread's direction and to say so. Do not total the ledger or give a score; the site counts it.
- A narrative whose "continues" names an earlier narrative belongs to that narrative's thread. A narrative that continues nothing starts a new thread, unless it plainly belongs to a silent thread, in which case revive that thread and keep its key.
- Every narrative in today's edition appears in exactly one thread. Earlier narratives keep their threads.
- A thread with no narrative in the last three editions is "silent". Keep silent threads, with their text left as it was or shortened; they are pruned later by the site, not by you.
- At most twelve live threads. If more would be live, merge the ones that are genuinely one thread and say so in revision.
- Plain spoken and descriptive throughout. No metaphor, no aphorism, no sentence written to be quoted. Dates as day and month. "By these headlines" when you reach past what the narratives support. Do not claim to know where the world is going; say which way these threads have moved and leave the rest.
- Use only edition stamps and narrative ids that appear in the editions you were given.
- Plain British English. Hyphens, never dashes.

Return JSON matching the schema."""

SCHEMA = {
    "type": "object",
    "properties": {
        "standing": {"type": "string"},
        "moved": {"type": "array", "items": {"type": "string"}},
        "silent": {"type": "array", "items": {"type": "string"}},
        "threads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "label": {"type": "string"},
                    "status": {"type": "string", "enum": ["live", "silent"]},
                    "since": {"type": "string"},
                    "lastSeen": {"type": "string"},
                    "narratives": {"type": "array", "items": {"type": "object", "properties": {"stamp": {"type": "string"}, "id": {"type": "string"}}, "required": ["stamp", "id"], "additionalProperties": False}},
                    "text": {"type": "string"},
                    "direction": {"type": "string"},
                },
                "required": ["key", "label", "status", "since", "lastSeen", "narratives", "text", "direction"],
                "additionalProperties": False,
            },
        },
        "withdrawn": {"type": "array", "items": {"type": "object", "properties": {"held": {"type": "string"}, "undone": {"type": "string"}, "stamp": {"type": "string"}}, "required": ["held", "undone", "stamp"], "additionalProperties": False}},
        "caseAgainst": {"type": "string"},
        "line": {"type": "string"},
        "revision": {"type": "string"},
    },
    "required": ["standing", "moved", "silent", "threads", "withdrawn", "caseAgainst", "line", "revision"],
    "additionalProperties": False,
}


def watch_block(previous):
    if not WATCH.exists():
        return ""
    try:
        items = json.loads(WATCH.read_text()).get("items", [])
    except ValueError:
        return ""
    if not items:
        return ""
    since = (previous or {}).get("generatedAt") or ""
    recent = [w for w in items if w.get("resolved") and (w["resolved"].get("asOf") or "") >= since[:10]]
    open_ = [w for w in items if w.get("status") == "open"]
    lines = []
    for w in recent:
        res = w["resolved"]
        heads = "; ".join(f"{h.get('publisher', '')} ({h.get('sourceCountry', '')}): {h.get('titleEnglish') or h.get('title', '')}" for h in res.get("headlines", [])[:2])
        lines.append(f"{w['status'].upper()} on {res['asOf'][:10]} | set {w['asOf'][:10]} by {w['narrativeId']} ({w['firmness']}) | {w['what']} | {res.get('note', '')}{' | ' + heads if heads else ''}")
    for w in open_:
        lines.append(f"OPEN, runs to {w['by']} | set {w['asOf'][:10]} by {w['narrativeId']} ({w['firmness']}) | {w['what']}")
    return "THE LEDGER OF EXPECTATIONS (settled since the previous Chronicle, then still open):\n" + "\n".join(lines) + "\n\n"


def build_request(index, readings, previous):
    editions = index["editions"][:RECENT_EDITIONS]
    stamp = stamp_of(readings)
    brief_lines = []
    for e in reversed(editions):
        brief_lines.append(f"EDITION {e['stamp']} (headlines of {e['newsGeneratedAt']}):")
        for n in e["narratives"]:
            brief_lines.append(f"  {n['id']} | {n['kicker']} | {n['line']} | continues: {n.get('continues') or '-'}")
    today = []
    for r in readings["readings"]:
        today.append(f"id: {r['id']}\nkicker: {r['kicker']}\nline: {r['line']}\nfirmness: {r.get('firmness') or '-'}\ncontinues: {r.get('continues') or '-'}\nchange: {r.get('change') or '-'}\nevents: " + "; ".join(e["label"] for e in r.get("events", [])) + f"\nclaim: {r['claim']}")
        if r.get("watch"):
            today.append("to watch for: " + "; ".join(f"{w['what']} (by {w['by']})" for w in r["watch"]))
        brk = next((ru for ru in r["rungs"] if ru["kind"] == "break"), None)
        if brk:
            today.append("case against: " + " ".join(f["text"] for f in brk["fragments"]))
        today.append("")
    prev = json.dumps({k: previous[k] for k in ("standing", "moved", "silent", "threads", "withdrawn", "caseAgainst", "line", "revision") if k in previous}, ensure_ascii=False, indent=1) if previous else "(none: this is the first version)"
    prev_stamp = previous.get("editionStamp") if previous else None
    user = (
        f"THE PREVIOUS CHRONICLE{' (revised for edition ' + prev_stamp + ')' if prev_stamp else ''}:\n{prev}\n\n"
        f"THE RECENT EDITIONS, oldest first:\n" + "\n".join(brief_lines) + "\n\n"
        f"TODAY'S EDITION, {stamp} (headlines of {readings.get('newsGeneratedAt')}), in detail:\n" + "\n".join(today) + "\n"
        + watch_block(previous) +
        "Revise the Chronicle."
    )
    return user


def stamp_of(edition):
    return (edition.get("newsGeneratedAt") or edition["generatedAt"]).replace("-", "").replace(":", "")[:15]


def validate(ch, index, readings, previous=None):
    problems = []
    held = {w["held"].strip() for w in ch.get("withdrawn", [])}
    for w in (previous or {}).get("withdrawn", []):
        if w["held"].strip() not in held:
            problems.append("a withdrawn item from the previous Chronicle was dropped: " + w["held"][:60])
    stamp = stamp_of(readings)
    known = {(e["stamp"], n["id"]) for e in index["editions"] for n in e["narratives"]}
    known.update((stamp, r["id"]) for r in readings["readings"])
    stamps = {e["stamp"] for e in index["editions"]} | {stamp}
    if not ch.get("standing", "").strip():
        problems.append("empty standing")
    if not ch.get("line", "").strip():
        problems.append("empty line")
    elif len(ch["line"]) > 200:
        problems.append("line longer than 200 characters")
    keys, seen = set(), {}
    for t in ch.get("threads", []):
        if t["key"] in keys:
            problems.append(f"duplicate thread key {t['key']}")
        keys.add(t["key"])
        if t["since"] not in stamps or t["lastSeen"] not in stamps:
            problems.append(f"thread {t['key']}: unknown stamp")
        for n in t["narratives"]:
            ref = (n["stamp"], n["id"])
            if ref not in known:
                problems.append(f"thread {t['key']}: unknown narrative {ref}")
            if ref in seen and seen[ref] != t["key"]:
                problems.append(f"narrative {ref} in two threads")
            seen[ref] = t["key"]
    for r in readings["readings"]:
        if (stamp, r["id"]) not in seen:
            problems.append(f"today's narrative {r['id']} is in no thread")
    if sum(1 for t in ch.get("threads", []) if t["status"] == "live") > 14:
        problems.append("more than fourteen live threads")
    return problems


def prune(ch, index):
    order = [e["stamp"] for e in index["editions"]]  # newest first
    keep = []
    for t in ch["threads"]:
        if t["status"] == "silent" and t["lastSeen"] in order and order.index(t["lastSeen"]) >= PRUNE_SILENT_AFTER:
            continue
        keep.append(t)
    ch["threads"] = keep


def load_state():
    state = json.loads(STATE.read_text()) if STATE.exists() else {"day": None, "attempts": 0, "history": []}
    today = now_iso()[:10]
    if state.get("day") != today:
        state = {"day": today, "attempts": 0, "history": state.get("history", [])[-30:]}
    return state


def note(state, message, **extra):
    entry = {"at": now_iso(), "note": message[:300]}
    entry.update(extra)
    state.setdefault("history", []).append(entry)
    STATE.write_text(json.dumps(state, indent=1) + "\n")


def write_versions(ch):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{ch['editionStamp']}.json").write_text(json.dumps(ch, ensure_ascii=False, indent=2) + "\n")
    CURRENT.write_text(json.dumps(ch, ensure_ascii=False, indent=2) + "\n")
    versions = []
    for p in sorted(OUT.glob("*.json")):
        if p.name == "index.json":
            continue
        v = json.loads(p.read_text())
        versions.append({"stamp": v["editionStamp"], "file": f"data/chronicle/{p.name}", "asOf": v["asOf"], "generatedAt": v["generatedAt"],
                         "threads": len(v["threads"]), "live": sum(1 for t in v["threads"] if t["status"] == "live")})
    versions.sort(key=lambda v: v["stamp"], reverse=True)
    (OUT / "index.json").write_text(json.dumps({"versions": versions}, ensure_ascii=False, indent=1) + "\n")
    append_record(ch)


def append_record(ch):
    """The record: one line per edition, kept in order, never revised. A stamp already recorded is left as it was."""
    if not ch.get("line"):
        return
    rec = json.loads(RECORD.read_text()) if RECORD.exists() else {"notes": ["One line per edition from the keeper of the Chronicle, saying what the day is in the longer story since 1945, by these headlines. Lines are added, never revised or removed."], "lines": []}
    if any(l["stamp"] == ch["editionStamp"] for l in rec["lines"]):
        return
    rec["lines"].append({"stamp": ch["editionStamp"], "asOf": ch["asOf"], "writtenAt": ch["generatedAt"], "line": ch["line"].strip()})
    rec["lines"].sort(key=lambda l: l["stamp"])
    RECORD.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    readings = json.loads((DATA / "readings.json").read_text())
    index = json.loads((DATA / "narratives" / "index.json").read_text())
    previous = json.loads(CURRENT.read_text()) if CURRENT.exists() else None
    stamp = stamp_of(readings)
    if previous and previous.get("editionStamp") == stamp and not args.force:
        print(f"chronicle: edition {stamp} already chronicled; nothing to do")
        return 0
    user = build_request(index, readings, previous)
    model = os.environ.get("CHRONICLE_MODEL") or "claude-opus-5-5"
    effort = os.environ.get("CHRONICLE_EFFORT") or "high"
    if args.dry_run:
        print(f"dry run: {len(user):,} characters of input for {model}; no request made")
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; chronicle unchanged", file=sys.stderr)
        return 1
    state = load_state()
    cap = int(os.environ.get("CHRONICLE_MAX_PER_DAY") or "2")
    if state["attempts"] >= cap:
        print(f"chronicle: already revised {state['attempts']} time(s) today; nothing sent", file=sys.stderr)
        return 0
    import anthropic
    client = anthropic.Anthropic()
    state["attempts"] += 1
    note(state, f"revising for edition {stamp}")
    try:
        with client.messages.stream(
            model=model, max_tokens=48000, system=BRIEF, thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()
    except anthropic.APIError as error:
        note(state, f"request failed: {error}")
        print(f"chronicle: request failed: {error}", file=sys.stderr)
        return 1
    if message.stop_reason in ("refusal", "max_tokens"):
        note(state, f"stopped: {message.stop_reason}")
        print(f"chronicle: stopped with {message.stop_reason}; chronicle unchanged", file=sys.stderr)
        return 1
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        ch = json.loads(text)
    except ValueError as error:
        note(state, f"not JSON: {error}")
        return 1
    problems = validate(ch, index, readings, previous)
    if problems:
        note(state, "rejected: " + "; ".join(problems[:6]))
        print("chronicle rejected: " + "; ".join(problems[:6]), file=sys.stderr)
        return 1
    prune(ch, index)
    usage = {"input": message.usage.input_tokens, "output": message.usage.output_tokens, "tier": "standard"}
    out = {
        "schemaVersion": 1, "editionStamp": stamp, "asOf": readings.get("newsGeneratedAt"), "generatedAt": now_iso(),
        "model": message.model, "promptVersion": "chronicle-2", "usage": usage,
        "previousVersion": previous.get("editionStamp") if previous else None,
        "notes": ["A running account of where things stand by these headlines, revised after each edition rather than added to. Every version is kept.",
                  "Written by the model from the narratives, not from the headlines. It is a reading, not a record."],
    }
    out.update(ch)
    write_versions(out)
    note(state, "ok", usage=usage)
    print(f"chronicle revised for edition {stamp} with {message.model}: {len(out['threads'])} threads ({sum(1 for t in out['threads'] if t['status'] == 'live')} live); {usage['input']} in / {usage['output']} out tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
