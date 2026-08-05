# INGRES AI Assistant

Conversational assistant over real CGWB groundwater data for Punjab. Ask a
plain-English question about a district, get a grounded, cited answer with a
chart or map. Built as a 5-agent pipeline — query understanding → retrieval →
calculation → verification → response.

**Status: Phases 1–3 complete.** Data loaded (1,607 stations, 36,879 readings
1996–2024, 23 risk categories, 153 assessment blocks), six tool endpoints
live, and the five-agent pipeline answering all four demo questions. Next is
Phase 4, the React frontend.

---

## Setup

```bash
python -m pip install --user -r backend/requirements.txt
```

> Note: this machine's Windows Application Control policy blocks unsigned
> compiled extensions inside a `.venv`, so packages are installed to user
> site-packages instead. `numpy`, `psycopg` and `sqlalchemy` all load fine
> there; `pandas` does not load at all, which is why ingestion is stdlib-only.

Then copy `backend/.env.example` to `backend/.env` and fill in `DATABASE_URL`.

### Database: local for dev, Railway for deploy

Development uses a **local PostgreSQL 16** instance, not Railway:

```
DATABASE_URL=postgresql://postgres:PASSWORD@localhost:5432/ingres
```

> **Why not Railway locally?** The dev network permits outbound traffic on ports
> 80, 443 and 8080 only. Every database port is blocked, including the high port
> Railway's TCP proxy binds to, so the managed instance is unreachable from here.
> This is not a Railway misconfiguration and no Railway setting works around it.
>
> It costs nothing architecturally: when the backend is deployed *inside*
> Railway it reaches Postgres over `postgres.railway.internal` and never crosses
> this firewall. It also satisfies the local fallback spec §13 requires for demo
> day, when venue wifi will likely impose the same restriction.

If the password contains `@`, `:` or `/`, percent-encode it (`@` → `%40`) —
those are URL delimiters and will otherwise be parsed as part of the host.

Create the database once:

```bash
python -m app.scripts.create_db
```

---

## Phase 1 — data ingestion

Everything runs from the `backend/` directory.

### 1. The raw CSVs

Two files from the **National Water Data Portal** (NWIC), dataset
*Ground Water Level (Manual – Quarterly), Central Ground Water Board* —
CGWB's National Hydrograph Network, monitored four times a year:

| File | Coverage | Size |
|---|---|---|
| `gwl_manual_quarterly_cgwb_pb_1991_2020.csv` | 1996–2020 | 4.28 MB |
| `gwl_manual_quarterly_cgwb_pb_2021_2025.csv` | 2021–2024 | 582 KB |

Both live in `backend/data/raw/`. To re-fetch:

```bash
curl -L -o gwl_manual_quarterly_cgwb_pb_1991_2020.csv \
  "https://nwdp.nwic.gov.in/dataset/956add67-cba9-41a5-9d5c-96d73db44aef/resource/41e431b0-082a-41f7-bf32-d7eea6a4ef1f/download/gwl_manual_quarterly_cgwb_pb_1991_2020.csv"
curl -L -o gwl_manual_quarterly_cgwb_pb_2021_2025.csv \
  "https://nwdp.nwic.gov.in/dataset/956add67-cba9-41a5-9d5c-96d73db44aef/resource/862305d4-0384-4af2-9dca-122e6db0a1c2/download/gwl_manual_quarterly_cgwb_pb_2021_2025.csv"
```

> **Do not use the IndiaWRIS groundwater UI.** Its data API
> (`POST /gwlMinMaxDate`) returned 503 on every attempt during this build — the
> page spins forever and reports 0 stations. NWDP serves the same CGWB data over
> plain HTTP with no UI in the way.
>
> Also avoid the district-wise summary tables on data.gov.in. They give
> per-district *counts of wells per depth band* with no station, no date and no
> level — useless for trends. The ingestion script rejects them outright.

The script does not assume a fixed column layout. It resolves the columns it
needs against a table of known CGWB header spellings and handles both shapes
these exports come in:

- **long** — one row per reading, with `DATE` and `WATER_LEVEL` columns
- **wide** — one row per station, with per-period columns like
  `Pre-monsoon_2019`, `Post-monsoon_2020`

If a required column can't be resolved it aborts and prints the file's actual
headers, rather than guessing. Add the spelling to `COLUMN_ALIASES` in
[ingest_data.py](backend/app/scripts/ingest_data.py) and re-run.

### 2. Dry run first

```bash
python -m app.scripts.ingest_data --csv data/raw/gwl_manual_quarterly_cgwb_pb_1991_2020.csv data/raw/gwl_manual_quarterly_cgwb_pb_2021_2025.csv --dry-run
```

`--csv` takes several files and merges them into one dataset, resolving each
file's headers separately.

This cleans and reports without touching the database — no `DATABASE_URL`
needed. **Read the summary before loading for real.** It prints station and
reading counts, the date range, a per-district breakdown, and every row it
dropped with the reason why. Sanity-check that manually, as the spec requires.

Pay particular attention to:
- **`UNRECOGNISED district names`** — a new spelling variant that needs adding
  to [districts.py](backend/app/scripts/districts.py). Those rows were dropped.
- **`NOT in the data`** — Punjab districts with no coverage at all. The
  assistant cannot answer questions about these.
- **the date range and per-district `First`/`Last`** — a district with under
  three years of readings will produce a weak depletion trend, which the
  Calculation Agent has to be honest about (spec 7.3, `confidence_note`).
- **the seasonal-date note**, if it appears — wide-format seasonal columns
  carry no exact date, so pre-monsoon readings are dated 1 May, monsoon 1 Aug
  and post-monsoon 1 Nov. Trend slopes are then accurate to the season, not
  the day.

### 3. Risk categories — done, and how they were derived

**Source:** *Ground Water Resources of Punjab State (As on 31st March, 2024)*,
Central Ground Water Board — Annexure I (block-wise resources, pp. 115–118) and
Annexure III (district summary, p. 119).

Two files in `backend/data/`:

- `cgwb_blocks_2024.csv` — 153 blocks: district, block, stage of extraction %, category
- `risk_categories.csv` — 23 districts: derived category plus the block counts behind it

**CGWB categorises assessment units (blocks), never districts.** The spec's
schema wants one category per district, so `category` is *derived*: the category
held by most of the district's blocks, ties broken toward the worse category.
That is a modelling choice, not an official figure, which is exactly why the
block counts are stored alongside it — an answer should cite
"5 of 9 blocks over-exploited", not just assert a label.

**How the extraction was verified.** Parsing Annexure I gives 153 blocks whose
category totals (22 safe, 12 semi-critical, 4 critical, 115 over-exploited)
reproduce the report's printed totals exactly, and whose per-district counts
match Annexure III for all 23 districts — an independent cross-check against a
different table in the same report. No block's label contradicts CGWB's own
stage-of-extraction thresholds.

> An earlier attempt parsed Table III (block categorisation, pp. 125–129)
> instead and produced 4 wrong categories: rows spanning page breaks paired a
> 2024 percentage with a 2023 label, marking Bathinda's Sangat block
> over-exploited at 66% extraction. The cross-check against Annexure III is what
> caught it. If this data is ever re-extracted, run that check again.

Result: **20 districts over-exploited, 3 safe** (Fazilka, Muktsar, Pathankot).

### Re-deriving the risk categories (only if needed)

`risk_categories` holds CGWB's official safe / semi-critical / critical /
over-exploited assessment. **These are not derived from the water level data
and are not guessed** — they must be transcribed from CGWB's published
assessment report.

A template with all 23 Punjab districts is at
[risk_categories.template.csv](backend/data/risk_categories.template.csv):

```csv
district,category,assessment_year
Amritsar,,
Barnala,,
...
```

Fill in the `category` column, save it as `backend/data/risk_categories.csv`,
and the loader will validate every row — a blank, an invalid category or an
unrecognised district all abort the load with a specific message.

### 4. Load for real

```bash
python -m app.scripts.ingest_data --csv data/raw/gwl_manual_quarterly_cgwb_pb_1991_2020.csv data/raw/gwl_manual_quarterly_cgwb_pb_2021_2025.csv --risk-csv data/risk_categories.csv
```

The script creates the schema if needed and is idempotent — re-running inserts
nothing new, thanks to unique indexes on `(station_name, district)` and
`(station_id, reading_date)`.

---

## The dataset, as verified

Dry-run output from the two files above:

| | |
|---|---|
| Rows read | 36,941 |
| Clean readings | 36,879 (13 dropped, 49 duplicates averaged) |
| Stations | 1,607 |
| Date range | 1996-01-05 → 2024-01-01 |
| Districts | 22 of 23 |
| Unrecognised district names | none |

Coverage is continuous — every year from 1996 to 2024 has readings, with no
gaps. Density dips around 2005–2012 and peaks in 2018. 2024 holds only the
January round.

Stations rotate in and out of the network, so per-station history is shorter
than the 28-year span suggests: median 15 readings and an 8-year span per
station. 77% of stations span ≥3 years and 73% have ≥8 readings. For the two
demo districts:

| District | Stations | Usable for a trend (≥3 yr, ≥8 readings) | Still reporting since 2020 |
|---|---|---|---|
| Ludhiana | 131 | 99 | 71 |
| Bathinda | 106 | 82 | 68 |

**Two things this implies for later phases:**

1. **Malerkotla is absent.** It was carved out of Sangrur in 2021 and the
   monitoring network still files those stations under Sangrur. The Query
   Understanding Agent's district list must either exclude it or map it to
   Sangrur with a caveat — it must not silently return "no data".
2. **The Calculation Agent must filter stations before fitting.** Roughly a
   quarter of stations have too little history for a defensible slope, and a
   linear fit across the full 28 years will understate recent depletion if the
   rate accelerated. Fit recent data from qualifying stations, and let
   `confidence_note` say which window and how many stations were used.

## Cleaning rules

| Rule | Behaviour |
|---|---|
| Non-Punjab rows | Dropped, when the file has a state column |
| District spelling | Collapsed to one of 23 canonical names; unrecognised names dropped **and reported**, never folded into a neighbour |
| Missing station / date / level | Dropped, counted by reason |
| Water level outside −5…200 m | Dropped as a sentinel (`-9999`) or unit error |
| Coordinates outside Punjab's bounding box | Blanked, row kept — a bad coordinate shouldn't cost a reading |
| Same station, same date | Averaged into one reading, count reported |

`water_level_m` is **depth to water, metres below ground**. Larger means
deeper, which means worse — a rising number is a falling water table.

---

## Loading everything from scratch

```bash
python -m app.scripts.create_db
python -m app.scripts.ingest_data --csv data/raw/gwl_manual_quarterly_cgwb_pb_1991_2020.csv data/raw/gwl_manual_quarterly_cgwb_pb_2021_2025.csv --risk-csv data/risk_categories.csv --blocks-csv data/cgwb_blocks_2024.csv
```

Re-running is safe: readings insert nothing new, and the risk/block tables are
upserted.

---

## Phase 2 — tool endpoints

Run the API from `backend/`:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Interactive docs at `http://127.0.0.1:8000/docs`.

| Endpoint | Notes |
|---|---|
| `GET /tools/current_level?district=` | Latest reading, plus `stations_reporting` and `district_mean_m` |
| `GET /tools/depletion_rate?district=&years=` | Median of per-station trends, with `confidence_note` |
| `GET /tools/risk_category?district=` | CGWB category plus the block counts behind it |
| `GET /tools/compare?districts=a,b,c` | Level + category side by side |
| `GET /tools/blocks?district=` | Individual assessment units — the citable evidence |
| `GET /health` | `db_connected`, `llm_reachable` |

**Why the median of per-station trends** rather than one line through all
pooled readings: stations rotate in and out of CGWB's network, so pooling lets
a handful of unusually deep or shallow wells dominate the slope. Each station
is fitted separately (`numpy.polyfit`), stations with under 8 readings or under
a 3-year span are excluded, and the median across the survivors is reported.
`confidence_note` states how many stations were used and how many are falling.

Unknown districts return **404** with `error: "unknown_district"` and the list
of valid names — that response is what the orchestrator's out-of-scope fallback
will key off in Phase 3. A district that exists but has no readings returns a
distinct `error: "no_data"`.

### Cross-validation

Depletion rates come from the water-level readings; risk categories come from
the CGWB PDF. They are entirely independent, and they agree:

| | Level | Depletion | CGWB category |
|---|---|---|---|
| Pathankot | 4.5 m | 0.03 m/yr | safe |
| Muktsar | 3.4 m | 0.09 m/yr | safe |
| Fazilka | 2.9 m | 0.11 m/yr | safe |
| Ludhiana | 18.2 m | 0.48 m/yr | over-exploited |
| Sangrur | 40.1 m | 1.21 m/yr | over-exploited |
| Barnala | 42.6 m | 1.41 m/yr | over-exploited |

All three "safe" districts have the shallowest water tables and the slowest
decline; the fastest-declining have the deepest. **All 22 districts with
readings show a falling water table** — none rising.

> Known artefact: **Rupnagar** is labelled over-exploited but declines only
> 0.04 m/yr. Its blocks split 2 safe / 1 semi-critical / 2 over-exploited, and
> the tie broke toward the worse category. The block counts are stored precisely
> so an answer can show this rather than hide it.

## Phase 3 — the agent pipeline

`POST /chat` runs query understanding → retrieval → calculation →
verification → response (spec §7).

### Two LLM backends

Set `LLM_PROVIDER` in `.env`:

| Value | Model | Cost | Notes |
|---|---|---|---|
| `ollama` | `qwen2.5:7b-instruct` | free | Local, works offline — covers spec §13's venue-wifi risk |
| `anthropic` | `claude-opus-5` | ~$0.02/question | Stronger verification; use for the demo |

The five agents are identical either way; only the backend call differs.
Ollama's JSON-schema mode and the Claude API's structured outputs both return
a validated Pydantic object, so no agent ever parses free text.

First Ollama call takes ~45 s while the model loads into VRAM, then ~1 s.
**Warm it before a demo** with any throwaway question.

### Grounding checks — why an LLM verifier is not enough

Spec §7.4 has a model fact-check another model. That works until it doesn't:
the 7B model approved a draft citing **Kot Shamir — a Bathinda station — as
the source for a Ludhiana figure**, and credited the 30 m projection depth to
CGWB when the data explicitly says it is not a CGWB threshold. The numbers
were right; the attributions were invented.

So [grounding.py](backend/app/agents/grounding.py) runs plain-Python checks
over the retrieved data first. It cannot hallucinate, and it catches:

- a citation naming something absent from the data
- a figure matching no value in the data (with rounding tolerance)
- a district the retrieved data does not cover
- a non-CGWB threshold attributed to CGWB
- a projected arrival year that is not the year the data computed
- a figure written with a unit that matches no value *of that unit*

The last two were added after the first four passed answers that were wrong.
Checking membership alone let *"approximately 20 years (2034)"* through when the
projection gives 2044, and *"a reference depth of 20.1 metres"* through because
20.1 really is in the data — as the number of years. **Being in the data is not
the same as measuring what the sentence says it measures.**

These are the **blocking** gate. The LLM reviewer is **advisory** — it catches
nuance the rules cannot (a dropped caveat, a projection stated as fact) but
also objects to figures that are genuinely present, so it triggers one rewrite
rather than a block. A rewrite that introduces a grounding failure the original
did not have is discarded, so an advisory objection can never turn a clean
answer into a data dump. If grounding still fails after the rewrite, the answer
is replaced by a plain data dump saying so.

All six checks are covered by tests, including both failures above, so neither
can come back:

```bash
cd backend && python -m pytest tests/
```

## Hybrid retrieval — database *and* document

Two sources, chosen by intent, never mixed:

| Question | Source | Why |
|---|---|---|
| "Level in Bathinda?" | **Postgres** | Exact value, station, date |
| "Which are over-exploited?" | **Postgres** | Exact list |
| "Deepest water table?" | **Postgres** | Ranked across all districts |
| "Is the water safe to drink?" | **CGWB report** | No quality data in the database |
| "Why is groundwater falling?" | **CGWB report** | Explanation, not measurement |
| "What does stage of extraction mean?" | **CGWB report** | Methodology |

**Numbers never go through RAG.** Retrieving prose *about* a figure is strictly
worse than querying the figure: it loses the station, the date, and the ability
to check it. The report is indexed for what the database genuinely lacks.

### The index

254 chunks from pages 9–114 of *Ground Water Resources of Punjab 2024*,
embedded with `nomic-embed-text` locally. Annexures I–V are deliberately
**excluded** — those tables are already in Postgres as exact rows.

At 254 chunks, search is a dot product over a 762 KB normalised matrix. No
vector database, no pgvector, no extra service. The index is committed, so the
pipeline runs without the 7 MB PDF.

```bash
python -m app.scripts.build_rag_index      # only needed to rebuild
```

Passages below 0.55 cosine similarity are discarded rather than answered from.
Each carries its page number, so answers cite
*"(CGWB, Ground Water Resources of Punjab 2024, p. 83)"*.

> **Honest limitation.** Document answers are harder to verify than database
> answers. The grounding checks confirm a cited page and figure appear in the
> retrieved passages, but cannot catch a subtler misreading — in testing, a
> Punjab-wide salinity statistic was once attributed to Bathinda specifically.
> Database answers do not have this weakness, which is why numeric questions
> stay on the structured path.

## Repository layout

```
backend/
  app/
    config.py          settings from env
    database.py        SQLAlchemy engine + session
    models.py          ORM models mirroring schema.sql
    routers/           Phase 2 — tool endpoints, /chat, /health
    agents/            Phase 3 — the 5-agent pipeline
    services/          Phase 3 — LLM client, groundwater service
    scripts/
      schema.sql       table definitions
      districts.py     canonical Punjab districts + spelling variants
      ingest_data.py   the ingestion script
  data/raw/            raw CSVs (gitignored)
  data/rag/            committed chunk + vector index
  tests/               pytest over the deterministic pieces
frontend/              Phase 4
```

## Build order

1. ~~**Data** — ingest and verify counts~~
2. ~~**Backend core** — tool endpoints~~ *(Railway skipped — see below)*
3. ~~**Agents** — 7.1 → 7.6~~
4. ~~**Frontend** — chat UI~~
5. ~~**Integration testing** — ambiguous and out-of-scope questions~~
6. ~~**Polish** — suggested questions, citations, `/health`~~
7. **Demo prep** ← *you are here*

Deployment was skipped deliberately: this network blocks every database port,
so Railway was unusable during development and the demo runs locally.
[HANDOFF.md](HANDOFF.md) has what is still weak and what to do next.
