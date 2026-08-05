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

---

## 2. Where the data came from

| Source | What it gave | Rows |
|---|---|---|
| NWDP (`nwdp.nwic.gov.in`), CGWB *Manual Quarterly* export | Station-level water levels, 1996–2024 | 36,879 readings across 1,607 stations |
| CGWB *Ground Water Resources of Punjab 2024* (PDF, 130pp) | Block categories, and the RAG corpus | 153 blocks, 254 text chunks |

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
| `scripts/districts.py` | 135 | Punjab's 23 canonical district names plus every spelling CGWB actually uses. `Ropar`→Rupnagar, `Firozpur`→Ferozepur, `Mukatsar`→Muktsar, `Mohali`/`SAS Nagar`→Sahibzada Ajit Singh Nagar. `variants_of()` exists because the report writes *Bhatinda*. |
| `scripts/create_db.py` | 61 | Creates the database. Postgres has no `CREATE DATABASE IF NOT EXISTS`, and it cannot be created from a connection to itself. |
| `scripts/ingest_data.py` | 776 | The loader. Resolves columns against known CGWB header spellings and **aborts printing the real headers** rather than guessing. Handles long and wide layouts, drops non-Punjab rows, sentinels (`-9999`), unparseable dates, and out-of-range levels — counting every drop by reason. Idempotent. |
| `scripts/build_rag_index.py` | 143 | Chunks pages 9–114 of the report and embeds them locally. Annexures are excluded on purpose: those tables are already in Postgres as exact rows. |

### Services — the layer both the API and the agents call

| File | Lines | Job |
|---|---|---|
| `services/groundwater_service.py` | 345 | All SQL. Current level, depletion rate, risk category, blocks, comparison, ranking, yearly series, map points. No FastAPI imports, so agents call it directly instead of looping back over HTTP. |
| `services/rag_service.py` | 91 | Semantic search over the report. Vectors are pre-normalised, so search is a dot product over a 762 KB matrix — no vector database. Passages below 0.55 similarity are discarded rather than answered from. |
| `services/llm_client.py` | 224 | The model boundary. One interface, two backends. Handles structured output, refusals, and a retry when a small model runs out of tokens mid-JSON. |

### Agents — `backend/app/agents/`

| File | Lines | Job |
|---|---|---|
| `query_understanding.py` | 154 | Question → structured intent, via constrained JSON. Also canonicalises the district itself, so a near-miss spelling never reaches SQL. |
| `retrieval.py` | 134 | **Deterministic.** Maps intent to service calls. No model involved. |
| `calculation.py` | 99 | **Deterministic.** Projects the water table forward at its measured rate. |
| `grounding.py` | 155 | **Deterministic.** The blocking verification gate. |
| `verification.py` | 51 | Model-based review. Advisory only. |
| `response.py` | 71 | Writes the prose from verified data. |
| `orchestrator.py` | 322 | Wires it together and decides what the user finally sees. |

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
| `components/ChatWindow.jsx` | 128 | State, submission, bottom-anchored message list, scroll pinning. |
| `components/AquiferHero.jsx` | 246 | The landing page: an animated cross-section, counting stats, tagged prompt cards. Inline SVG only — no external assets, so it works offline. |
| `components/MessageBubble.jsx` | 64 | One message: prose, source badge, citations, unverified warning. |
| `components/TrendChart.jsx` | 85 | Depth over time, **Y axis reversed** so a falling line reads as a falling water table. |
| `components/MapView.jsx` | 132 | Districts coloured by category, re-measured after layout settles. Names any district it cannot plot. |
| `index.css` | 105 | Animations, all disabled under `prefers-reduced-motion`. |

---

## 4. What happens when you ask a question

Take *"How many years until Ludhiana hits critical depth?"*

**1 — Understanding.** The model returns constrained JSON:
`{intent: "years_to_critical", district: "Ludhiana"}`. The district is then
re-canonicalised in Python, so a typo cannot reach the database.

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

*Deterministic (`grounding.py`), blocking:*
- every parenthesised citation must name something in the retrieved data
- every figure must match a value in the data, with rounding tolerance
- every district named must be one the data covers, matched across spellings
- a threshold the data marks as non-official must not be credited to CGWB

*Model-based (`verification.py`), advisory:* catches nuance rules cannot — a
dropped caveat, a projection stated as fact. It gets one rewrite, not a veto,
because it also objects to figures that are genuinely present.

If grounding still fails after the rewrite, the answer is replaced by a plain
data dump saying so. **An unverifiable answer is never shown as if it were
verified.**

**6 — Assembly.** Citations, chart and map are built **from the data**, not from
model flags — it left both flags false on questions that obviously wanted a
visual, and left the citations array empty while writing citations inline.

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
| The projection maths | no — numpy |
| Writing the prose | **yes** |
| Checking citations, figures, districts | no — plain Python |
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

**Run it**

```bash
cd backend && python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend && npm run dev
```

Open **http://localhost:5173**. Interactive API docs are at `/docs`.

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
stations. It is named in the map footnote rather than dropped, and a question
about its water level says so plainly.

---

## 8. Known limitations

- **Document answers are less verifiable than database answers.** Grounding
  confirms a cited page and figure appear in the retrieved passages, but cannot
  catch a subtler misreading — a Punjab-wide salinity statistic was once
  attributed to Bathinda specifically. This is inherent to RAG, and is why
  numeric questions stay on the structured path.
- **"Why is groundwater falling in Punjab?"** is rejected by grounding and falls
  back to a data dump. Honest, but avoid it in a demo.
- **A persona injection wrapped around a real question** is refused outright.
  The injection is resisted; the legitimate question inside is lost. Fails safe.
- **Map tiles need internet.** Everything else runs offline; OpenStreetMap tiles
  do not.
- **Malerkotla has no readings** — level, trend and projection are unavailable
  for it. Only its category exists.
