# The Present Tense

The day's headlines, and the narratives that run through them.

Hundreds of the day's headlines from publishers in dozens of countries, laid out as one continuous field. Zoomed out it is a map of the world with each country a swarm of its headlines; zoom in and a swarm unfolds into a page you can read. Along the bottom of the page sit the day's narratives, written once a day by a language model. A narrative is an idea that joins unlike events: a price in one country, a strike in a second, a court case in a third, that share a cause, a mechanism, an actor or a shape. The narrative is the idea and the headlines are its evidence; one event reported from many countries is a collation, not a narrative, and the brief allows at most one of those an edition. Every narrative lists what it joins, commits to a claim, shows its evidence, sets out the case against itself, and then asks how we got here: four horizons, the past decade, the past fifty years, since September 2001 and since 1945, placing the day on longer trajectories.

Black and white. No framework, no build step. A static site that refreshes itself from GitHub Actions.

## What is in the box

| Path | What it is |
| --- | --- |
| `index.html`, `style.css`, `app.js` | The site. One field, a strip of narratives, a drawer for each, the tide, the index, about. |
| `data/news.json` | The current collection: headline metadata from the GDELT Article List, with English titles. |
| `data/readings.json` | The current edition of narratives. Each has a line, a kicker, a claim, rungs of fragments, four horizons, and the headlines it cites, frozen with the edition. |
| `data/library.json` | Thirty books and sixty-eight historical moments the narratives may cite, every link checked. |
| `data/ledger.json` | The tide: what arrived, stayed and departed since the previous collection, and which countries were silent. |
| `data/editions/` | Slim copies of the last 14 collections, for the ledger. |
| `data/narratives/` | Every edition of narratives, one file per headline collection read, with `index.json` listing them newest first. The site's Editions panel and the Threads page read it. |
| `data/chronicle.json`, `data/chronicle/` | The Chronicle: a running account of where things stand by these headlines, revised after each edition, with every version kept. |
| `data/attention.json` | A second register: yesterday's most-viewed Wikipedia articles in 28 language editions, Bluesky's trending topics, trending hashtags on a few Mastodon servers. |
| `threads.html`, `threads.js` | The narratives across editions, drawn as threads, with the Chronicle beneath. |
| `lineage.html` | Where the idea comes from: the books and arguments behind the site. |
| `data/world.json` | Natural Earth land, sampled as dots. See `data/WORLD-SOURCE.md`. |
| `data/source-config.json` | The publisher allowlist, country anchors and collection limits. |
| `data/translations.json` | Cache of English headlines keyed by the original title. |
| `scripts/collect.py` | Bounded GDELT collection. Standard library only. |
| `scripts/translate.py` | English headlines for new, non-English titles (Claude Haiku). |
| `scripts/ledger.py` | Builds the tide and archives editions. |
| `scripts/oracle.py` | Asks Claude for a new edition of narratives against a strict schema, through the Message Batches API (same model, half price). The writing brief is in the file. |
| `scripts/freeze.py` | Attaches each narrative's cited headlines so it keeps its evidence after the collection moves on. |
| `scripts/validate.py` | Refuses an edition whose citations do not resolve, whose narratives do not end with a case against, or whose narratives are collations of one event rather than joins of several. |
| `scripts/archive.py` | Keeps every edition under `data/narratives/` and rebuilds its index; `--backfill` recovers earlier editions from git history. |
| `scripts/chronicle.py` | Revises the Chronicle from the narratives (not the headlines) through the Messages API, streamed; validates thread references; keeps every version. The brief is in the file. |
| `scripts/attention.py` | Collects the second register from the Wikimedia REST API and the public Bluesky and Mastodon endpoints. Standard library only; every source is optional. |
| `scripts/build.py` | Copies the public files to `_site/`. |
| `.github/workflows/pages.yml` | Collect, translate, read, validate, commit, deploy. |

## Preview on your own machine

```sh
cd Present-Tense
python3 -m http.server 8770
```

Open <http://127.0.0.1:8770/>. The site loads JSON, so it needs a server rather than a `file:` URL.

Controls: drag to move, scroll, pinch or double-click to zoom (shift-double-click zooms out; `+`, `-`, `0` for the world, `1` for the constellation), click a headline for its card and link. There are four levels: WORLD (countries as swarms), REGION (swarms with names), HEADLINES (countries unfold into pages of their headlines) and CLOSE. The country under the pointer stays under the pointer while the others unfold around it. The strip along the bottom shows all of the day's narratives; select one and its headlines light up in the field and the drawer opens with the evidence, the connections and the case against. In the drawer, hover or open a fragment and its headlines light up in the field. "Original" switches headlines to their source language. "Tide" shows what changed since the previous collection and can show departed headlines as ghosts. "Index" is the plain, searchable list. "Editions" lists every edition of narratives, newest first; choose one and the strip, the drawer and the field step back to that day, with the headlines it cited held in the field. The strip's "earlier" and "later" step between editions. Where a narrative continues one from the edition before, the drawer says what has changed and links back to it, and forward to any later narrative that continued it. The URL hash carries the state, including `edition`, so a view can be shared.

## Put it on GitHub Pages

1. Create a repository with `main` as its default branch and push this folder to its root. Hidden folders matter: `.github/workflows/pages.yml` and `.nojekyll` must be included.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write**, so the job can commit each new edition.
4. **Settings → Secrets and variables → Actions:**
   - Secret `ANTHROPIC_API_KEY`: needed for English headlines and for new narratives.
   - Variable `GENERATE_READINGS` = `true` to let the scheduled run ask for new narratives. Manual runs ask for it in the dialog.
   - Optional variables: `ORACLE_MODEL` (default `claude-opus-5-5`), `ORACLE_EFFORT` (default `high`), `ORACLE_MAX_PER_DAY` (default `2`), `ORACLE_WAIT_MINUTES` (default `25`), `TRANSLATE_MODEL` (default `claude-haiku-5-5`).
5. **Actions → Collect, read and publish → Run workflow.** The first run can publish the seed edition with refresh off.

Headlines are collected at 04:17, 10:17, 16:17 and 22:17 UTC. New narratives are written once a day, submitted on the 22:17 run (09:17 in Sydney during daylight saving) as a batch request. The run waits up to 25 minutes for it; if the batch takes longer, the next scheduled run collects it, frozen against the collection it was asked about. The other runs refresh the field and the tide under the existing readings; the headlines those narratives cite are held in the field, marked `held`, until the next edition replaces them. Scheduled runs on public repositories pause after sixty days without a commit; a manual run restarts them.

## Threads and the Chronicle

`threads.html` draws every edition as a column and every narrative as a mark sized by its headlines; where a narrative continues one from the edition before, a line joins them, so a story that persists runs across the page as a thread and a story that stops simply ends. Scale it to days, weeks or months. Select a mark to open that narrative in that edition. Beneath it sits the Chronicle: where things stand, what moved, what fell silent, a dated paragraph per thread, the case against the Chronicle itself, and what changed in it since its previous version. It is revised after each edition, not added to, and every version is kept so the account's own history can be read.

The second register, "Looked up", sets what people looked up and talked about beside what publishers printed. It is passed to the model as context: a narrative may mention it, naming the language edition or the platform, but cannot cite it or rest on it.

## What one edition costs

One edition sends every headline in the collection plus the library and the second register (around 55,000 input tokens) and returns five narratives with their horizons (around 25,000 output tokens, plus 40,000 to 50,000 of thinking at high effort). It goes through the Message Batches API, which runs the same model at half the standard price: at Claude Opus 5.5's batch rate of US$2 per million input and US$10 per million output tokens that is about US$0.85 an edition. The Chronicle revision sends the narratives, not the headlines (around 15,000 input, 6,000 output plus thinking at the standard rate, US$4 and US$20 per million), about US$0.25. Translation of new headlines on Haiku is a few cents. Call it US$1.15 a day, US$35 a month, US$420 a year, with hard caps of two submissions a day for each writer in `data/oracle-state.json` and `data/chronicle-state.json`. The model and the thinking effort are deliberately not reduced; if you must cut further, cut days, not depth. `ORACLE_MODEL` and `ORACLE_EFFORT` exist as repository variables if you ever want to. Translation of a few hundred new headlines on Haiku costs a few cents. Set a spending limit on the key in the Anthropic console as well.

## How many headlines

The collector takes up to 720 headlines an edition, at most 20 from any country and 7 from any publisher, sampled from ten moments across the previous eighteen hours of the GDELT feed. The ceiling is in `data/source-config.json` (`maxArticles`, up to 800 without changing the collector). Three things limit it. The field stays legible to about 1,500 beads. The model reads every headline in one request and its narratives get looser, not richer, past roughly a thousand lines. And breadth matters more than depth: a country capped at 20 headlines keeps the field a map rather than a list of whoever publishes most. The way to see more of a day is more countries and more collections, not a bigger single sample.

The request does not enable server-side refusal fallbacks; a refused or malformed response simply leaves the previous edition in place.

## How an edition is made

```
collect.py  ->  translate.py  ->  ledger.py  ->  oracle.py (batch: submit, wait, or collect)  ->  freeze.py  ->  validate.py  ->  archive.py  ->  attention.py  ->  chronicle.py  ->  commit  ->  deploy
```

Each step keeps the previous result if it fails. Narratives that are older than the collection are marked as such on the page, and their cited headlines remain inspectable because `freeze.py` stores them with the edition.

The writing brief in `scripts/oracle.py` asks for narratives that are ideas joining at least three different events (the validator refuses a narrative in which one event holds more than half the headlines), that commit, that cross countries and registers, that cite books and trajectories only when they change the narrative, that always end with a rung called "The case against" containing a specific, honest objection, and that close with four horizons of 130 to 200 words each, concrete, dated, tied back to the headlines, and written as a trajectory rather than a verdict. The language mandate is plain spoken and descriptive throughout: no metaphor, no aphorism, nothing written to be quoted; the intelligence should be in the connections and the evidence. The validator enforces the structure. It cannot enforce the quality; read what comes back.

## Seed edition

The narratives and their horizons first shipped with this repository were composed by Claude from the collection of 26 October 2026, 23:46 UTC, reading titles and metadata only. Where a horizon relies on an event of 2025 or 2026 it says so or leans on the headlines. The ledger compares that collection with one reconstructed from the 12:02 and 15:02 UTC samples of the same day, so the tide is real from the first edition.

## Rights and limits

Headline metadata comes from the [GDELT Project](https://www.gdeltproject.org/) under its terms of use, with attribution. Only titles, links, publishers, languages and timestamps are used; no article bodies or images. Land is [Natural Earth](https://www.naturalearthdata.com/), public domain. Country placement is the publisher's country, approximate, never the event's location. A country's press is not that country's people. The sample is bounded by the allowlist and by per-country and per-publisher caps, so it is not representative of anything except itself.

Concept and direction: Craig Smith. First prototype, collector and map: Codex. This version, the seed edition and the writing brief: Claude.
