# The Present Tense

A world in conversation, read by an oracle.

Hundreds of the day's headlines from publishers in dozens of countries, laid out as one continuous field: softly geographic, slowly drifting, each a door to the original report. At the centre sits an oracle that reads the collection into constellations, possible narratives that join a headline in Lagos to one in Taipei to one in Córdoba. Every reading commits to a claim, shows its evidence, and then argues against itself.

Black and white. No framework, no build step. A static site that refreshes itself from GitHub Actions.

## What is in the box

| Path | What it is |
| --- | --- |
| `index.html`, `style.css`, `app.js` | The site. One field, an oracle, a reading drawer, the tide, the index, about. |
| `data/news.json` | The current collection: headline metadata from the GDELT Article List, with English titles. |
| `data/readings.json` | The current edition of readings. Each reading has a line, a kicker, a claim, rungs of fragments, and the headlines it cites, frozen with the edition. |
| `data/library.json` | Books and historical trajectories the oracle may cite. |
| `data/ledger.json` | The tide: what arrived, stayed and departed since the previous collection, and which countries were silent. |
| `data/editions/` | Slim copies of the last 14 collections, for the ledger. |
| `data/world.json` | Natural Earth land, sampled as dots. See `data/WORLD-SOURCE.md`. |
| `data/source-config.json` | The publisher allowlist, country anchors and collection limits. |
| `data/translations.json` | Cache of English headlines keyed by the original title. |
| `scripts/collect.py` | Bounded GDELT collection. Standard library only. |
| `scripts/translate.py` | English headlines for new, non-English titles (Claude Haiku). |
| `scripts/ledger.py` | Builds the tide and archives editions. |
| `scripts/oracle.py` | Asks Claude for a new edition of readings against a strict schema. The brief is in the file. |
| `scripts/freeze.py` | Attaches each reading's cited headlines so it keeps its evidence after the collection moves on. |
| `scripts/validate.py` | Refuses an edition whose citations do not resolve or whose readings do not end with a case against. |
| `scripts/build.py` | Copies the public files to `_site/`. |
| `.github/workflows/pages.yml` | Collect, translate, read, validate, commit, deploy. |

## Preview on your own machine

```sh
cd Present-Tense
python3 -m http.server 8770
```

Open <http://127.0.0.1:8770/>. The site loads JSON, so it needs a server rather than a `file:` URL.

Controls: drag to move, scroll or pinch to zoom, click a headline for its card and link. The oracle at the bottom cycles through readings; "Open the reading" shows the ladder. In the ladder, hover or open a fragment and its headlines light up in the field. "Original" switches headlines to their source language. "Tide" shows what changed since the previous collection and can show departed headlines as ghosts. "Index" is the plain, searchable list. The URL hash carries the state, so a view can be shared.

## Put it on GitHub Pages

1. Create a repository with `main` as its default branch and push this folder to its root. Hidden folders matter: `.github/workflows/pages.yml` and `.nojekyll` must be included.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write**, so the job can commit each new edition.
4. **Settings → Secrets and variables → Actions:**
   - Secret `ANTHROPIC_API_KEY`: needed for English headlines and for new readings.
   - Variable `GENERATE_READINGS` = `true` to let the scheduled run ask the oracle. Manual runs ask for it in the dialog.
   - Optional variables: `ORACLE_MODEL` (default `claude-opus-5-5`), `ORACLE_EFFORT` (default `high`), `ORACLE_MAX_PER_DAY` (default `2`), `TRANSLATE_MODEL` (default `claude-haiku-5-5`).
5. **Actions → Collect, read and publish → Run workflow.** The first run can publish the seed edition with refresh off.

The schedule is 04:17 and 16:17 UTC. Scheduled runs on public repositories pause after sixty days without a commit; a manual run restarts them.

## What one edition costs

One oracle request sends every headline in the collection (around 60,000 input tokens) and returns five to eight readings (around 15,000 output tokens, plus thinking). On Claude Opus 5.5 that is roughly US$0.50 to US$0.80 an edition, so about US$1.50 a day on the default schedule, with a hard cap of two attempts a day in `data/oracle-state.json`. Translation of a few hundred new headlines on Haiku costs a few cents. Set a spending limit on the key in the Anthropic console as well.

The oracle request does not enable server-side refusal fallbacks; a refused or malformed response simply leaves the previous edition in place.

## How an edition is made

```
collect.py  ->  translate.py  ->  ledger.py  ->  oracle.py  ->  freeze.py  ->  validate.py  ->  commit  ->  deploy
```

Each step keeps the previous result if it fails. Readings that are older than the collection are marked as such on the page, and their cited headlines remain inspectable because `freeze.py` stores them with the edition.

The oracle brief in `scripts/oracle.py` asks for readings that commit, that cross countries and registers, that cite books and trajectories only when they change the reading, and that always end with a rung called "Break this reading" containing a specific, honest case against. The validator enforces the structure. It cannot enforce the quality; read what comes back.

## Seed edition

The readings shipped with this repository were composed by Claude from the collection of 26 October 2026, 23:46 UTC, reading titles and metadata only. The ledger compares that collection with one reconstructed from the 12:02 and 15:02 UTC samples of the same day, so the tide is real from the first edition.

## Rights and limits

Headline metadata comes from the [GDELT Project](https://www.gdeltproject.org/) under its terms of use, with attribution. Only titles, links, publishers, languages and timestamps are used; no article bodies or images. Land is [Natural Earth](https://www.naturalearthdata.com/), public domain. Country placement is the publisher's country, approximate, never the event's location. A country's press is not that country's people. The sample is bounded by the allowlist and by per-country and per-publisher caps, so it is not representative of anything except itself.

Concept and direction: Craig Smith. First prototype, collector and map: Codex. This version, seed readings and oracle brief: Claude.
