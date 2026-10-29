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

BRIEF = """You write the narratives of The Present Tense, a site that lays out one day's world headlines as a field and shows, along the bottom of the page, the narratives that run through them. A narrative is an idea that joins unlike events. You look at hundreds of headlines from dozens of countries, reporting many different things, and you find what several of those different things have in common: a shared cause, a shared mechanism, a shared actor, or the same shape. Then you say it plainly and show the headlines it rests on.

The narrative is the idea. The headlines are its evidence. No single headline contains the idea; the connection is yours to make and to defend, and the structure gives you a place to doubt it.

What a narrative is not. It is not one event as reported from many countries. "Forty outlets covered the Brazilian election" is a collation, not a narrative, however many countries the outlets are in. The events a narrative joins must be different events: a price in one place, a strike in a second, an election in a third, a court case in a fourth, that turn out to have something in common. At most one narrative in the edition may be built mainly on how different countries report the same event, and only when the differences in the reporting are the point.

Kinds of join, to vary across the edition:
- A shared cause: one upstream development with different downstream consequences, for example the same rise in bond yields appearing as a pension story in the Netherlands, a mortgage story in Britain and a budget story in Kenya.
- A shared mechanism: the same thing happening for the same reason in unrelated places, for example savers in Kenya, China and Indonesia moving money out of reach of the tax office while each government offers an amnesty.
- A shared actor: one company, state, court, church, fund or person appearing in stories that are otherwise about different things.
- The same shape: different events in which the same question is being decided the same way, who pays, who decides, who is blamed, what is rationed. Name the shape in plain words.
- A material or an object in several roles: water, copper, a chip, a vaccine, a stadium, a ship, appearing in unrelated stories.

Worked example. Suppose the collection holds: Chennai eases building rules in its aquifer zone; an Arizona chip plant is delayed over its water supply; Ireland pauses new data centres on the Dublin grid and water network; Dutch farmers protest nitrogen and water rules. A collation would make four narratives, housing, chips, data centres, farming, or one narrative about "Chennai's water shortage as reported in India, Britain and Singapore". A narrative joins them. Its claim opens by naming them: "Chennai's aquifer rules, an Arizona chip plant, Dublin's data centres and Dutch farms are all held up this week by water rather than land or money." Its line says what that shows: "Ten years after the first big drought warnings, water has become the limit on building in rich and poor countries alike." Its kicker is "WATER / BUILDING / LIMITS". The line is plain, specific and checkable against the headlines, and it can be wrong, which is what the case against is for.

You will receive the collection: one line per headline with its id, publisher country, publisher, language, time and English headline. You may also receive a second register, what was looked up: yesterday's most-viewed Wikipedia articles by language edition, and trending topics on Bluesky and Mastodon. That register is context, not evidence: a fragment may mention it in its text, naming the language edition or the platform ("the Spanish and Portuguese Wikipedias' most-viewed pages were Lula and the Brazilian election"), but cannot cite it, and a narrative may not rest on it. You will also receive a library of books and historical trajectories you may draw on, and the previous edition's narratives (id and line) so you do not repeat them and so you can say what each of yours continues.

Compose an edition of narratives. Each narrative has:
- line: one plain sentence, shown on the narrative's tile, that says what the join shows about the present at the scale of a decade: what it tells a reader about where things stand in this year, not which headlines were joined. "Eight months into a war over oil, the countries that said they were leaving it still price their roads, flights and subsidies by it" is a line; "The war's fuel squeeze reaches US air fares, easyJet luggage, Estonian asphalt and Malaysian subsidies" is not, because it lists the evidence and leaves the idea to the reader. The line names no publisher and no headline, and is not a list: it may name a kind of thing (roads, flights, subsidies) but not the four places they happened. If the join genuinely shows nothing about the present beyond itself, do not invent a condition: state the join plainly instead, and let the kicker carry the idea. At most 135 characters, counted strictly; shorten by dropping a clause, not by compressing into an image. No metaphor, no aphorism, no wordplay, no paradox, no colon-headlines, no questions, no hedging, no sentence that reads as a slogan. Dates, durations, numbers and the names of institutions are what make a line specific.
- kicker: three plain words in capitals separated by " / " that name the terms of the idea, for example "OIL / A WAR / THE TRANSITION" or "BONDS / PENSIONS / BUDGETS". The terms of the idea, not a list of the products or places in the evidence, and not the same nouns the line uses. Subjects, not images.
- events: three to six entries, each a short plain label of two to eight words naming one distinct event or development the narrative joins, with the ids of the headlines about that event. The entries must be about different things, not the same event in different countries. Every headline the narrative cites should belong to one entry, and no entry may hold more than half of the narrative's headlines. This list is shown to the reader at the top of the narrative as what it joins.
- firmness: "firm", "plausible" or "tentative", chosen honestly. Firm: the cause, actor or mechanism is named in the headlines themselves and the join would be hard to deny. Plausible: the join is a reasonable reading that a careful reader could contest. Tentative: the pattern may be an artefact of the sample, of English, or of one day. An edition of five firm narratives is not credible; a tentative narrative is worth publishing when it says so. The site shows the word to the reader and, in time, checks it against what the join went on to predict.
- continues: the id of the narrative in the previous edition that this one carries forward, if any; otherwise an empty string. A narrative continues an earlier one when it follows the same join or the same events a day later, not merely the same topic.
- change: if continues is set, one to three plain sentences saying what has changed since that narrative: what moved, what was confirmed, what fell away. If continues is empty, an empty string. This is shown to the reader as "Since the previous edition", so write it for them.
- claim: two to four sentences, read first when the narrative is opened. The first sentence names the joined events: who, what, where, so that a reader knows at once what has been connected. The rest states the idea and why the join matters. Written for an intelligent general reader in plain descriptive prose. Commit to the interpretation. No disclaimers, and no closing flourish: do not end a paragraph on an epigram or a line designed to be quoted.
- rungs: three to five rungs, in this order: one or two of kind "observation" (what the headlines say, event by event, across countries), one or two of kind "interpretation" (what joins them: the cause, mechanism, actor or shape, and what it might mean), and always, last, exactly one of kind "break" labelled "The case against" that makes the strongest honest case against the narrative: that the events are not in fact connected, a rival explanation, a sampling objection, a reason the pattern is an artefact of the collection or of English, or a reason you have mistaken a normal thing for a new thing. The break rung must be substantive and specific, not a generic caveat, and it must say, in plain words, what the joined events do not share: the difference that survives the join (one is fraud, one is a flood of applicants, one is the state itself). A narrative that cannot say where its events part is not ready. Observation and interpretation rungs have plain descriptive labels of two to six words saying what they cover ("Four workplace deaths", "Where the money is going"), not titles or images ("Two doors", "The counter goes quiet").
- each rung has one to three fragments. A fragment has a short plain label, a text of two to five sentences, and the ids of the headlines it rests on (observation and interpretation fragments cite at least one; break fragments may cite none). The text names publishers and countries and quotes headlines in paraphrase. Facts about events come only from the headlines; do not invent them. The connection between events is yours, so state it as an idea, not as a reported fact. A fragment may notice what a headline withholds.
- bookIds and trajectoryIds: cite a book or a trajectory only when it changes how the fragment reads. Most fragments should cite none. Never more than two per fragment.
- horizons: after the rungs, "How we got here". Four, in this order, each anchored to the start of a regime most of the world is still living inside: span "since-2020" (the pandemic, the inflation that followed it, the war in Ukraine, the AI wave: the conditions of this decade), "since-2008" (the financial crisis, the smartphone and the platforms, China as the second economy, the end of the belief that globalisation ran itself), "since-1989" (the end of the Cold War, the openings of India and China, the internet, the WTO, the long peace that 2008 and 2022 ended) and "since-1945" (decolonisation, the institutions, the dollar, the welfare state: the order the other three are chapters of). Each horizon answers the same question in the same shape: what did the regime that began then put in place that these headlines are now living inside? Its label is "Since 2020", "Since 2008", "Since 1989" or "Since 1945"; its from field is an empty string. A fifth horizon, span "longer", may be added after the four only when the join is about something older than 1945 and the past genuinely offers better context: water, land, a border, a religion, an empire, a trade route. It names its own starting point: from is a four-digit year ("1916"), its label is "Since" followed by that year or the moment ("Since 1916, the Sykes-Picot line"), and its text explains why that is where this join begins. Most narratives should not have one. Each horizon has a lens of two or three capitalised words separated by " / " naming the kinds of history it draws on (for example "OIL / REVOLUTION / ALLIANCE", "DEMOGRAPHY / HOUSING / PROTEST", "CAPITAL / DISCLOSURE / WATER"), and a text of 130 to 200 words. A horizon places the idea, the join itself, on a longer trajectory: sociological, economic, demographic, migratory, environmental, technological, legal or intellectual, whichever genuinely explain how these different things came to have this in common. Name dates, laws, prices, flows of people, institutions, books and the people who wrote them. Be concrete and specific to the narrative's countries and events; connect at least once in each horizon back to a specific headline in the narrative. Do not write a general history of the period, and do not let the horizons overlap: what belongs to the years since 2020 is said once, there, and the since-2008 horizon begins where that one stops. Do not claim authority: a horizon is a trajectory, not a verdict, and it may say where the trajectory is contested. Each horizon cites one to four trajectories and zero to two books from the library, chosen because they are the moments and arguments the text actually stands on; if the library lacks the moment you need, name it in the text and cite nothing (the longer horizon will often have to). Use only facts you are confident of; where the decade's recent events are known to you only from the headlines, say "by these headlines".

Language. This matters as much as the structure:
- Plain spoken and descriptive throughout, in every field. Say what is reported, where, by whom, and what joins it to the rest. Prefer the concrete noun to the image and the ordinary word to the striking one. Short sentences are fine. Numbers, dates, names and institutions are the material.
- No metaphor and no personification: money does not "slip", clouds do not "come down", states do not "answer". No aphorisms, no paradoxes, no rhetorical questions, no lists of three for rhythm, no sentence built to be quoted. If a sentence would be admired for its style, rewrite it for its content.
- The intelligence of the edition lives in the joins and the evidence, not in the phrasing. A good narrative is one a careful reader could restate in their own words without loss, and could then test against the headlines.
- A join must be a real, nameable thing (a cause, a mechanism, an actor, a shape), stated in plain words. "Everything is about power" or "a world in flux" is not a join. If you cannot say in one plain sentence what the events have in common, they are not a narrative.

Rules of the game:
- Each narrative joins at least three different events, reported from at least four countries, and cites between six and twenty-five headlines. Prefer joins that cross registers: a market story with a church story, a sport story with a protest story, a court case with a harvest.
- Vary the kinds of join across the edition. Not five shared causes; not five shapes.
- Commit. The structure already contains the doubt (the break rung). Do not write "this does not establish" or "may or may not" inside fragments.
- Use only headline ids from the collection. Use only book and trajectory ids from the library.
- Do not repeat the previous edition's lines or claims. If a join continues from a previous edition, set continues to that narrative's id and say in change what has changed. The site keeps every edition, and readers can step back to the one you continue, so the edition as a whole should read as where we are today against where we were yesterday: some narratives continue, some are new, and change says which is which.
- Write in plain British English. Use hyphens, never dashes. Capitalise proper nouns only.
- Across the edition the horizons must not repeat each other: if two narratives share a decade, they must read it through different lenses and different moments.

Return JSON matching the schema (its top-level key is still called "readings"; each item is one narrative). Compose three to five narratives: only the joins that hold. If three hold, write three; an edition that reaches for a fourth to fill the page is worse than one that stops, and a quiet day is itself a finding. Fewer, fuller and better evidenced rather than more."""


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
                    "firmness": {"type": "string", "enum": ["firm", "plausible", "tentative"]},
                    "continues": {"type": "string", "description": "id of the previous edition's narrative this continues, or empty"},
                    "change": {"type": "string", "description": "what has changed since that narrative, or empty"},
                    "claim": {"type": "string"},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "two to eight plain words naming one distinct event"},
                                "articleIds": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["label", "articleIds"],
                            "additionalProperties": False,
                        },
                    },
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
                            "span": {"type": "string", "enum": ["since-2020", "since-2008", "since-1989", "since-1945", "longer"]},
                            "from": {"type": "string"},
                            "label": {"type": "string"},
                            "lens": {"type": "string"},
                            "text": {"type": "string"},
                            "trajectoryIds": {"type": "array", "items": {"type": "string"}},
                            "bookIds": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["span", "from", "label", "lens", "text", "trajectoryIds", "bookIds"],
                        "additionalProperties": False,
                    },
                },
                },
                "required": ["id", "line", "kicker", "firmness", "continues", "change", "claim", "events", "rungs", "horizons"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["readings"],
    "additionalProperties": False,
}


def attention_block():
    path = DATA / "attention.json"
    if not path.exists():
        return ""
    try:
        a = json.loads(path.read_text())
    except ValueError:
        return ""
    out = []
    w = a.get("wikipedia") or {}
    subs = w.get("subjects") or []
    if subs:
        out.append("Wikipedia subjects reached for in more than one language edition (subject: editions): " + "; ".join(f"{g['title']} ({g['editions']}: {', '.join(x['language'] for x in g['languages'][:6])})" for g in subs if g.get("editions", 0) > 1)[:4000])
    for l in w.get("languages", []):
        titles = ", ".join(x["title"] for x in l.get("articles", [])[:8])
        if titles:
            out.append(f"{l['languageName']} Wikipedia: {titles}")
    bs = [t["topic"] for t in (a.get("bluesky") or {}).get("topics", [])[:15]]
    if bs:
        out.append("Bluesky trending: " + "; ".join(bs))
    ms = [f"#{t['tag']} ({', '.join(t.get('languages', []))})" for t in (a.get("mastodon") or {}).get("tags", [])[:10]]
    if ms:
        out.append("Mastodon trending: " + "; ".join(ms))
    if not out:
        return ""
    return f"WHAT WAS LOOKED UP (Wikipedia most-viewed on {w.get('date')} by language edition; context, not evidence):\n" + "\n".join(out) + "\n\n"


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
    prev = "\n".join(f"- {r['id']} | {r['line']}" for r in (previous or {}).get("readings", [])) or "(none)"
    user = (
        f"THE COLLECTION, gathered {news['generatedAt']} ({len(news['articles'])} headlines):\n{collection}\n\n"
        + attention_block() +
        f"THE LIBRARY, books:\n{books}\n\nTHE LIBRARY, trajectories:\n{trajs}\n\n"
        f"THE PREVIOUS EDITION'S NARRATIVES (id | line):\n{prev}\n\nCompose this edition."
    )
    return user


def validate(edition, news, library):
    ids = {a["id"] for a in news["articles"]}
    books = {b["id"] for b in library["books"]}
    trajs = {t["id"] for t in library["trajectories"]}
    problems = []
    readings = edition.get("readings", [])
    if not 3 <= len(readings) <= 5:
        problems.append(f"{len(readings)} narratives (need three to five: only the joins that hold)")
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
        problems.extend(f"{r['id']}: {p}" for p in check_events(r, ids))
        for key in ("line", "kicker", "claim"):
            if not r.get(key, "").strip():
                problems.append(f"{r['id']}: empty {key}")
        if r.get("firmness") not in ("firm", "plausible", "tentative"):
            problems.append(f"{r['id']}: firmness must be firm, plausible or tentative")
        problems.extend(f"{r['id']}: {p}" for p in check_horizon_spans(r.get("horizons", [])))
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
        problems.extend(f"{r['id']}: {p}" for p in check_line(r, by))
    return problems


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


HORIZON_SPANS = ["since-2020", "since-2008", "since-1989", "since-1945"]
OLD_HORIZON_SPANS = ["decade", "half-century", "since-2001", "since-1945"]  # editions before 29 October 2026


def check_horizon_spans(horizons, allow_old=False):
    """Four fixed horizons in order, then at most one 'longer' horizon that names its own starting year."""
    spans = [h.get("span") for h in horizons]
    if allow_old and spans == OLD_HORIZON_SPANS:
        return []
    out = []
    if spans[:4] != HORIZON_SPANS:
        out.append(f"horizons must be {', '.join(HORIZON_SPANS)} in order (got {spans})")
    if len(spans) > 5 or (len(spans) == 5 and spans[4] != "longer"):
        out.append("at most one further horizon, and it must be 'longer'")
    for h in horizons:
        if h.get("span") == "longer":
            if not re.fullmatch(r"\d{4}", str(h.get("from", "")).strip()):
                out.append("the longer horizon must give its starting year in 'from'")
            elif int(h["from"]) >= 1945:
                out.append("the longer horizon must begin before 1945")
    return out


def refuse_narratives(edition, by):
    """A narrative that breaks the tile rules (a line that lists its evidence or names a publisher, a missing
    firmness) is refused on its own; the edition stands with the rest as long as three remain. Returns the reasons."""
    readings = edition.get("readings", [])
    bad = {}
    for r in readings:
        reasons = check_line(r, by)
        if r.get("firmness") not in ("firm", "plausible", "tentative"):
            reasons.append("no firmness")
        if reasons:
            bad[r.get("id", "?")] = reasons
    if not bad or len(readings) - len(bad) < 3:
        return []  # nothing to drop, or too few would remain: validate() will refuse the whole edition
    edition["readings"] = [r for r in readings if r.get("id", "?") not in bad]
    edition.setdefault("refused", []).extend({"id": k, "reasons": v} for k, v in bad.items())
    return [f"{k}: {'; '.join(v)}" for k, v in bad.items()]


def check_line(reading, by):
    """The line states what the join shows, not the evidence: no list of four or more items, no publisher's name."""
    line = reading.get("line", "")
    out = []
    if is_list(line):
        out.append("line is a list; it should say what the join shows, not list the evidence")
    low = line.lower()
    cited = set()
    for rung in reading.get("rungs", []):
        for f in rung.get("fragments", []):
            cited.update(f.get("articleIds", []))
    for x in cited:
        a = by.get(x)
        if not a:
            continue
        pub = (a.get("publisher") or a.get("publisherDomain") or "").lower()
        if pub and len(pub) > 3 and pub in low:
            out.append(f"line names a publisher ({pub})")
            break
    return out


def check_events(reading, ids):
    """A narrative joins different events: at least three, none holding more than half of its headlines."""
    events = reading.get("events") or []
    out = []
    if len(events) < 3:
        out.append(f"joins {len(events)} events (need at least 3)")
    sizes = []
    for e in events:
        known = {x for x in e.get("articleIds", []) if x in ids}
        if not e.get("label", "").strip():
            out.append("an event has no label")
        if not known:
            out.append(f"event '{e.get('label', '?')}' cites no known headline")
        sizes.append(len(known))
    union = set()
    for e in events:
        union.update(x for x in e.get("articleIds", []) if x in ids)
    if union and sizes and max(sizes) * 2 > len(union):
        out.append(f"one event holds {max(sizes)} of {len(union)} headlines (more than half: a collation, not a join)")
    return out


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
        "max_tokens": 128000,  # the model's ceiling; an edition with its thinking ran past 64,000 on 27 Oct 2026
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
    by_id = {a["id"]: a for a in pending["articles"]}
    refused = refuse_narratives(edition, by_id)
    if refused:
        note(state, "narratives refused: " + "; ".join(refused))
        print("oracle: narratives refused, the edition stands without them: " + "; ".join(refused), file=sys.stderr)
    problems = validate(edition, snapshot_news, library)
    if problems:
        return fail(state, "edition rejected: " + "; ".join(problems[:8]))
    previous = json.loads((DATA / "readings.json").read_text()) if (DATA / "readings.json").exists() else {}
    prev_ids = {r["id"] for r in previous.get("readings", [])}
    cited = []
    for r in edition["readings"]:
        if r.get("continues") and r["continues"] not in prev_ids:
            r["continues"] = ""
        if not r.get("continues"):
            r["change"] = ""
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
        "promptVersion": "narrative-5",
        "previousNewsGeneratedAt": previous.get("newsGeneratedAt"),
        "usage": usage,
        "notes": [
            "Edition composed by Claude from the collected headlines, reading titles and metadata only.",
            "Each narrative is an idea that joins several different events; what it joins is listed at the top. It commits to a claim, and the last rung of every narrative is the case against it. Read both.",
            "Where a narrative continues one from the previous edition it says what has changed since; every edition is kept, so the reader can step back to where we were.",
            "Each narrative ends with 'How we got here': four horizons, since 2020, since 2008, since 1989 and since 1945, each the start of a regime the headlines are living inside, and sometimes a fifth that reaches further back and names its own starting year. They are a trajectory, not a verdict.",
            "The connections are made by the model, not by the publishers. Follow any headline to the original report before repeating it.",
            "Books and trajectories appear only where they change how a fragment or a horizon reads.",
        ],
        "sourceArticles": [by_id[i] for i in cited],
        "readings": edition["readings"],
    }
    if edition.get("refused"):
        out["refused"] = edition["refused"]
        out["notes"].append("One or more narratives in this edition were refused by the site's own rules (a tile line that listed its evidence or named a publisher, or no stated firmness) and are not shown; the ids and reasons are kept in this file under 'refused'.")
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
