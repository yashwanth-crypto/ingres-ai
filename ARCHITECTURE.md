# How this is built

A complete walkthrough: what the system does, what every file is for, how a
question travels through it, and how the model is wired in.

---

## 1. The problem, and the shape of the answer

Ask a plain-English question about Punjab groundwater; get an answer grounded in
real CGWB data, with citations, and a chart or map.

The hard part is not generating an answer. It is **not generating a wrong one**.
A language model asked about groundwater will happily produce a fluent,
confident, entirely invented figure. Everything below is arranged around that.

Three ideas carry the design:

**Ask the database, not the model.** Numbers come from SQL over real readings —
exact, with a station name and a date attached. The model writes prose around
figures it was handed; it never supplies them.

**Verify with code, not only with a model.** Spec §7.4 has one model fact-check
another. That is in here and it helps — but during testing the reviewer
**approved** an answer citing *Kot Shamir*, a Bathinda station, as the source
for a **Ludhiana** figure. So plain-Python checks run first and are the blocking
gate. Rules cannot hallucinate, because they do not generate anything.

**Two sources, chosen deliberately.** The database knows how *much* water there
is. It knows nothing about *quality*. Quality, methodology and causes live in
CGWB's report, which is indexed for semantic search — but numeric questions
never go there, because retrieving prose *about* a figure loses the station and
the date that make it checkable.

The document side is the weaker half, and its weakness is *place*: a finding
about Punjab is one sentence away from a finding about a district. Every chunk
therefore declares what it is about — chapter, section, the districts it names,
and whether it is local or statewide — and retrieval, the prompt and check 7
all use that.

---

## 2. Where the data came from

| Source | What it gave | Rows |
|---|---|---|
| NWDP (`nwdp.nwic.gov.in`), CGWB *Manual Quarterly* export | Station-level water levels, 1996–2024 | 36,879 readings across 1,607 stations |
| CGWB *Ground Water Resources of Punjab 2024* (PDF, 130pp) | Block categories, and the RAG corpus | 153 blocks, 178 text chunks |

Two dead ends worth knowing about, because they cost real time:

- **IndiaWRIS** — its groundwater API returns `503`. The page spins forever and
  reports 0 stations. It is not a browser problem.
- **data.gov.in district tables** — these are *summary* tables: counts of wells
  per depth band, with no station, no date and no level. Useless for trends. The
  ingestion script rejects them outright rather than half-loading them.

**On the risk categories.** CGWB categorises *blocks*, never districts. So a
district category cannot be transcribed — it has to be derived. The rule here is
*the category held by most of the district's blocks, ties broken toward the
worse category*, and the block counts are stored alongside so an answer can show
its working. The extraction was cross-checked against a second table in the same
report, which caught **4 wrong categories** in the first attempt.

---

## 3. Every file

### Data layer — `backend/app/`

| File | Lines | Job |
|---|---|---|
| `config.py` | 54 | Settings from `.env`. Resolves the `.env` path from the module location so the app starts from any working directory, and rewrites `postgres://` → `postgresql+psycopg://` for SQLAlchemy. |
| `database.py` | 30 | Engine and session factory. `pool_pre_ping` because managed Postgres drops idle connections. |
| `models.py` | 77 | ORM: `Station`, `Reading`, `RiskCategory`, `AssessmentBlock`. |
| `schemas.py` | 68 | Pydantic response shapes for the API. |
| `scripts/schema.sql` | 64 | Tables. Adds two unique indexes beyond spec §4 — without them a second ingestion silently doubles every row. |
| `scripts/districts.py` | 160 | Punjab's 23 canonical district names plus every spelling CGWB actually uses. `Ropar`→Rupnagar, `Firozpur`→Ferozepur, `Mukatsar`→Muktsar, `Mohali`/`SAS Nagar`→Sahibzada Ajit Singh Nagar. `variants_of()` exists because the report writes *Bhatinda*. |
| `scripts/create_db.py` | 61 | Creates the database. Postgres has no `CREATE DATABASE IF NOT EXISTS`, and it cannot be created from a connection to itself. |
| `scripts/ingest_data.py` | 776 | The loader. Resolves columns against known CGWB header spellings and **aborts printing the real headers** rather than guessing. Handles long and wide layouts, drops non-Punjab rows, sentinels (`-9999`), unparseable dates, and out-of-range levels — counting every drop by reason. Idempotent. |
| `scripts/build_rag_index.py` | 308 | Chunks the report's narrative chapters — printed pages 1–78 — and embeds them locally. Every chunk records its chapter, section, the districts it names, and whether it is district-scoped or statewide. Annexures are excluded on purpose: those tables are already in Postgres as exact rows. |

### Services — the layer both the API and the agents call

| File | Lines | Job |
|---|---|---|
| `services/groundwater_service.py` | 360 | All SQL. Current level, depletion rate, risk category, blocks, comparison, ranking, yearly series, map points, categories in bulk. No FastAPI imports, so agents call it directly instead of looping back over HTTP. |
| `services/rag_service.py` | 145 | Semantic search over the report, then a deterministic rerank on what each chunk says it is about. Vectors are pre-normalised, so search is a dot product over a 534 KB matrix — no vector database. Passages below 0.55 similarity are discarded rather than answered from. |
| `services/llm_client.py` | 233 | The model boundary. One interface, two backends. Handles structured output, refusals, and a retry when a small model runs out of tokens mid-JSON. `slim_for_prompt()` also withholds fields the checks read but the model must not see. |

### Agents — `backend/app/agents/`

| File | Lines | Job |
|---|---|---|
| `query_understanding.py` | 206 | Question → structured intent, via constrained JSON. Canonicalises the district itself, so a near-miss spelling never reaches SQL, and resolves a follow-up that points back at the conversation rather than naming its subject. |
| `retrieval.py` | 142 | **Deterministic.** Maps intent to service calls, and passes the district to the reranker rather than only gluing it onto the query. No model involved. |
| `calculation.py` | 108 | **Deterministic.** Projects the water table forward at its measured rate, and states the year it lands on rather than leaving that as arithmetic. |
| `grounding.py` | 314 | **Deterministic.** The blocking verification gate — seven checks. |
| `verification.py` | 51 | Model-based review. Advisory only. |
| `response.py` | 72 | Writes the prose from verified data. |
| `orchestrator.py` | 462 | Wires it together, decides what the user finally sees, and builds the chart and map payloads. |

### API — `backend/app/routers/`

| File | Endpoints |
|---|---|
| `tools.py` | `/tools/current_level`, `/depletion_rate`, `/risk_category`, `/compare`, `/blocks` |
| `chat.py` | `POST /chat` |
| `health.py` | `GET /health` — database and model reachability, without spending tokens |
| `main.py` | App, CORS (explicit origins, never `*`), and a background model warm-up at startup |

### Frontend — `frontend/src/`

| File | Lines | Job |
|---|---|---|
| `App.jsx` | 68 | Shell, wordmark, live health indicator. |
| `api.js` | 26 | `sendMessage` / `getHealth`. In dev, Vite proxies `/api` so the browser makes no cross-origin request. |
| `categories.js` | 27 | The CGWB category colours, shared. The map and the bars often appear in one answer, and a district red on one and orange on the other reads as two findings. |
| `components/ChatWindow.jsx` | 128 | State, submission, bottom-anchored message list, scroll pinning. |
| `components/AquiferHero.jsx` | 246 | The landing page: an animated cross-section, counting stats, tagged prompt cards. Inline SVG only — no external assets, so it works offline. |
| `components/MessageBubble.jsx` | 69 | One message: prose, source badge, citations, unverified warning. Routes `chart_data` to bars or to the trend line by its `type`. |
| `components/TrendChart.jsx` | 292 | Depth over time as a cross-section: ground filled above the water table, **Y axis reversed** so a falling line reads as a falling water table. Draws the projection dashed into a shaded future region, ending on a marked crossing of the reference depth. |
| `components/RankChart.jsx` | 121 | Districts side by side, worst first, coloured by category, the answering district held at full opacity. Plain CSS grid — a grid lays out labelled horizontal bars better than a chart library. |
| `components/MapView.jsx` | 126 | Districts coloured by category, re-measured after layout settles. Names any district it cannot plot. |
| `index.css` | 125 | Animations, all disabled under `prefers-reduced-motion`. Nothing load-bearing is animated: bar widths and the projection's dash are correct in the markup whether or not the animation runs. |

### Tests — `backend/tests/`

Pure functions only: no model, no database, no network. Runs in about a second.

| File | Lines | Covers |
|---|---|---|
| `test_grounding.py` | 277 | All seven checks, including the three failures that shipped. |
| `test_calculation.py` | 148 | The projection, its chart line, and which fields the model may see. |
| `test_chart_payloads.py` | 145 | Which visual an intent earns, and the bar payloads. |
| `test_districts.py` | 73 | Canonicalisation across CGWB's spellings. |
| `test_followups.py` | 128 | Resolving "those two" against the conversation. |
| `test_rag.py` | 148 | Page offset, section map, chunk metadata, and the rerank. |

---

## 4. What happens when you ask a question

Take *"How many years until Ludhiana hits critical depth?"*

**1 — Understanding.** The model returns constrained JSON:
`{intent: "years_to_critical", district: "Ludhiana"}`. The district is then
re-canonicalised in Python, so a typo cannot reach the database.

A follow-up gets the last four turns as context, which is enough for *"and what
about Moga?"*, *"how fast is it falling there?"* and *"how many years until it
hits critical depth?"* to resolve. One shape needed more than context: *"which
of those two is worse?"* was classified as a ranking, measured against all 23
districts, and answered **Barnala** — a district nobody had mentioned, and
verified, because Barnala genuinely is in the ranking data. A superlative
pointing back at the conversation is a comparison of what was discussed, so it
is converted to one when the question names no district of its own and recent
turns named between two and four. Outside those bounds the intent is left alone:
*"which district has the worst water table?"* is still a real ranking
mid-conversation.

**2 — Retrieval (no model).** `years_to_critical` maps to two service calls:
depletion rate and current level. Real SQL, real rows.

**3 — Calculation (no model).** Each qualifying station gets a straight-line fit
(`numpy.polyfit`), and the **median** slope is taken. Median, not a line through
all pooled readings: stations rotate in and out of CGWB's network, so pooling
lets a few unusually deep wells set the slope. Stations with under 8 readings or
under a 3-year span are excluded. Result: 0.504 m/year from 75 stations,
20.1 years to 30 m.

**4 — Response.** The model writes prose around those numbers.

**5 — Verification, in two tiers.**

*Deterministic (`grounding.py`), blocking — seven checks:*

1. every parenthesised citation must name something in the retrieved data
2. every figure must match a value in the data, with rounding tolerance
3. every district named must be one the data covers, matched across spellings
4. a threshold the data marks as non-official must not be credited to CGWB
5. a projected arrival year must be the year the data computed
6. a figure written with a unit must match a value *of that unit*
7. a percentage tied to a district must come from a passage sentence tying them

The last three exist because the ones before them passed answers that were
wrong. Check 2 exempts every integer from 1900 to 2100 as "a year", since
citations carry them legitimately — so *"approximately 20 years (2034)"* went
out verified when the projection gives 2044, on the one question where the year
is the headline. Check 6 answers the mirror image: membership alone approved *"a
reference depth of 20.1 metres"*, because 20.1 really is in the data — as the
number of years. **Being in the data is not the same as measuring what the
sentence says.**

Check 7 covers report-backed answers, where the others are weakest. Asked
whether Bathinda's water is safe, the model wrote *"In Bathinda, 13.9% of water
samples have fluoride above 1.50 mg/L"* from a passage whose own sentence reads
*"the remaining 13.9% have fluoride above 1.50 mg/L"* — a Punjab-wide figure.
The page does name Bathinda elsewhere, so no amount of chunk-level scoping
catches it; only the sentence does. Percentages only: a threshold like *1.50
mg/L* is a limit the report defines once and applies everywhere, and demanding
it share a sentence with the district would reject correct answers.

*Model-based (`verification.py`), advisory:* catches nuance rules cannot — a
dropped caveat, a projection stated as fact. It gets one rewrite, not a veto,
because it also objects to figures that are genuinely present.

A rewrite that introduces a grounding failure the original did not have is
discarded. Told to mention the pumping limit, one rewrite credited the 30 m
figure to CGWB — and a first draft that grounded clean was being replaced by a
data dump on the strength of a nitpick, which is exactly the veto the advisory
reviewer is not meant to have.

If grounding still fails after the rewrite, the answer is replaced by a plain
data dump saying so. **An unverifiable answer is never shown as if it were
verified.**

**6 — Assembly.** Citations, chart and map are built **from the data**, not from
model flags — it left both flags false on questions that obviously wanted a
visual, and left the citations array empty while writing citations inline.

Which visual follows from the intent. One district over time gets the trend
line, with the projection drawn on it when there is one. Several districts
against each other get bars. A category listing gets only the map: every bar
would be the same length and the same colour.

---

## 5. The model

### Two backends, one interface

`LLM_PROVIDER` in `backend/.env`:

| Value | Model | Cost | Trade-off |
|---|---|---|---|
| `ollama` | `qwen2.5:7b-instruct` | free | Local, offline, no key. Weaker prose and verification. |
| `anthropic` | `claude-opus-5` | ~$0.02/question | Better prose and review. Needs internet and a key. |

The five agents are identical either way. Only the call inside `llm_client.py`
differs. Ollama's JSON-schema mode and the Claude API's structured outputs both
return a **validated Pydantic object**, so no agent ever parses free text.

### Where the model is and is not used

| Step | Model? |
|---|---|
| Understanding the question | **yes** |
| Choosing what data to fetch | no — a dict lookup |
| Fetching it | no — SQL |
| The projection maths, and the year it lands on | no — numpy |
| Writing the prose | **yes** |
| Checking citations, figures, districts, years, units | no — plain Python |
| Reviewing for nuance | **yes**, advisory |
| Citations, chart, map | no — built from the data |

Three of five agents involve no model at all.

### Switching to Claude

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Restart the backend. Roughly 2,300 input and 430 output tokens per question
across three calls — about $0.02, so the full demo costs under ten cents.

### Cost control

`slim_for_prompt()` strips bulk the model never cites individually — a 75-name
station list becomes `[75 stations]`, which the `confidence_note` already
summarises.

It also withholds fields the checks read but the model must not see. Shown the
projection's `projected_year`, a 7B model cited the field name as a source:
*"around 2044 (projected_year: 2044, citation: projection.confidence_note)"*.
The year is in `confidence_note` as prose, which is where an answer should get
it from.

---

## 6. Running it

**One-time**

```bash
python -m pip install --user -r backend/requirements.txt
```

```bash
ollama pull qwen2.5:7b-instruct
```

```bash
ollama pull nomic-embed-text
```

Then `backend/.env`:

```
DATABASE_URL=postgresql://postgres:PASSWORD@localhost:5432/ingres
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b-instruct
ALLOWED_ORIGINS=http://localhost:5173
```

Percent-encode `@` in the password as `%40` — it is a URL delimiter.

**Load the data** (from `backend/`)

```bash
python -m app.scripts.create_db
```

```bash
python -m app.scripts.ingest_data --csv data/raw/gwl_manual_quarterly_cgwb_pb_1991_2020.csv data/raw/gwl_manual_quarterly_cgwb_pb_2021_2025.csv --risk-csv data/risk_categories.csv --blocks-csv data/cgwb_blocks_2024.csv
```

Add `--dry-run` first: it validates and prints a full summary without touching
the database, and needs no `DATABASE_URL`. Re-running is safe — nothing
duplicates.

The RAG index is committed, so `build_rag_index.py` is only needed to rebuild it
(and only then does the 7 MB PDF matter).

```bash
python -m app.scripts.build_rag_index --dry-run
```

`--dry-run` chunks and reports without embedding or writing, which is the fast
way to see what a change to the chunking does. The index is cached in-process,
so a rebuild needs a backend restart to take effect.

**Run it**

```bash
cd backend && python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend && npm run dev
```

Open **http://localhost:5173**. Interactive API docs are at `/docs`.

`--reload` is unreliable on this machine: an edit to `llm_client.py` never
triggered one, and the stale code was only caught because three answers came
back byte-identical after a change that should have altered them. Restart the
backend rather than trust it. It also watches `backend/tests/`, so writing a
test bounces the server.

**Tests**

```bash
cd backend && python -m pytest tests/
```

102 tests, about a second, no model or database needed.

---

## 7. Decisions worth defending

**Median of per-station trends, not one pooled regression.** Stations rotate in
and out of the network; pooling lets a handful of wells set the slope.

**No official "critical depth" exists.** CGWB's categories measure extraction
against recharge, not metres. The projection therefore states its own reference
depth (30 m, a practical pumping limit) and says explicitly that it is not a
CGWB threshold.

**Numbers never go through RAG.** Retrieving prose about a figure loses the
station and the date. The report answers only what the database cannot.

**Withholding beats instructing.** Asked whether Bathinda's water is safe to
drink, the model led with *"Bathinda is over-exploited"* even though the prompt
forbade exactly that. The extraction category is now simply not retrieved for
quality questions.

**Rank by severity, not by axis.** `rank_order` was `highest`/`lowest`, and a
*deep* water table is a *low* water level — so the model read "deepest" as
"lowest" and returned the **shallowest** district. Renaming to `worst`/`best`
removed the ambiguity.

**Say what is missing.** Malerkotla has a CGWB category and no monitoring
stations. It is named in the map footnote and in the bar chart's footer rather
than dropped, and a question about its water level says so plainly.

**Check the quantity, not just the value.** Every figure in a projection answer
is somewhere in the data, so asking only *is this number present* approves the
number of years written as a depth. Figures are collected by what they measure,
and a number carrying a unit must match a value of that unit.

**Nothing load-bearing is animated.** Bar widths and the projection's dash are
correct in the markup whether or not the animation ever runs. An earlier version
transitioned bar width up from zero and rendered an empty chart wherever the
frames did not come.

---

## 8. Known limitations

- **Document answers are still the weaker half.** Check 7 stops a statewide
  percentage being *stated* as a district's, and the answer now reads "13.9% of
  samples across Punjab" rather than "in Bathinda, 13.9%". It cannot stop a
  reader drawing the same inference from two adjacent sentences, and it covers
  percentages only. Numeric questions stay on the structured path for this
  reason.
- **Scope is chunk-level, attribution is sentence-level.** A page that reports a
  Punjab-wide figure and names a district lower down is one chunk, marked
  district-scoped. The metadata cannot express that split; only check 7 sees it.
  Sentence-level scoping would be the real fix.
- **"Why is groundwater falling in Punjab?"** is rejected by grounding and falls
  back to a data dump. Honest, but avoid it in a demo.
- **A persona injection wrapped around a real question** is refused outright.
  The injection is resisted; the legitimate question inside is lost. Fails safe.
- **Map tiles need internet.** Everything else runs offline; OpenStreetMap tiles
  do not.
- **Malerkotla has no readings** — level, trend and projection are unavailable
  for it. Only its category exists.
- **The model still cites field names.** Asked how fast Sangrur is falling, a
  7B model answers `1.205 meters per year (depletion_rate). } (Sangrur,
  depletion_rate)` — a stray brace, and a key used as a source. Check 1 misses
  it because only capitalised tokens are treated as citations. The figure and
  its unit are right; the citation is noise.
- **Grounding cannot check what it was never given.** Checks 5 and 6 exist
  because two wrong answers were *correctly grounded* in the data they had. The
  same blind spot remains anywhere the retrieved data does not distinguish two
  quantities the prose can confuse.
