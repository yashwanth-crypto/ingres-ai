# The backend, in detail

Twenty-two source files, about 3,600 lines, plus 1,371 lines of tests. What each
one does, the decisions behind them, and the bugs that shaped them.

The companion to [FRONTEND.md](FRONTEND.md). For the request flow end to end see
[WALKTHROUGH.md](WALKTHROUGH.md).

---

## 1. The stack, and what is deliberately absent

| | Version | Why |
|---|---|---|
| FastAPI | 0.141.1 | Two endpoints for chat, five tool endpoints, one health check |
| PostgreSQL + SQLAlchemy | 2.0.51 | Relational, because the data is relational |
| psycopg | 3.3.4 | Driver named explicitly — see `config.py` below |
| Pydantic | 2.13.4 | Response shapes, and every model reply is validated into one |
| NumPy | 2.4.2 | Trend fitting and the semantic search |
| Ollama | qwen2.5:7b-instruct | Local inference, no key, no cost |
| pytest | 9.1.1 | 133 tests |

**Absent on purpose:**

- **No LangChain, no LlamaIndex.** The pipeline is six small modules and an
  orchestrator; a framework would hide the control flow that *is* the project.
- **No vector database.** 178 passages is a NumPy dot product — see §6.
- **No pandas.** This machine's Windows Application Control policy blocks
  pandas' unsigned compiled extensions (NumPy's and psycopg's load fine), so
  ingestion is stdlib `csv` only. It never needed a dataframe.
- **No SciPy.** `numpy.polyfit` does the trend fitting, avoiding the same risk
  on a dependency barely used.

Every one of those is written down in `requirements.txt`, in a "deliberately
absent" block, so the next person does not re-add them.

---

## 2. The four layers

```
app/scripts/     ingestion, district names, the RAG index builder
app/models.py    ORM — four tables
app/services/    all SQL · document search · the only place a model is called
app/agents/      six modules + an orchestrator: question → checked answer
app/routers/     FastAPI surface
```

**The service layer imports no FastAPI.** The agents call the SQL functions
directly as Python rather than looping back out over HTTP, so there is one code
path to a number rather than two. The tool endpoints exist so the same functions
can be tested standalone with `curl`.

---

## 3. Configuration — `config.py` (54 lines)

Two details worth knowing, both of which cost time to find.

**The `.env` path is resolved from the module location**, not the working
directory. Otherwise the app starts differently depending on where you launched
it — `uvicorn --app-dir`, a test runner and a deploy would each disagree.

**The database URL is rewritten for the driver.** Railway hands out
`postgresql://…`, and older tooling still emits `postgres://`. SQLAlchemy
resolves both to **psycopg2**, which is not installed — psycopg 3 is. So:

```
postgres://…  →  postgresql://…  →  postgresql+psycopg://…
```

Without that rewrite the app fails at import with a driver error that says
nothing useful.

> If your password contains `@`, percent-encode it as `%40`. It is a URL
> delimiter and will otherwise be parsed as part of the host.

---

## 4. The data model — `models.py` (77 lines) + `schema.sql` (64)

| Table | Rows | Key column |
|---|---|---|
| `stations` | 1,607 | unique on **(station_name, district)** |
| `readings` | 36,879 | unique on **(station_id, reading_date)** |
| `risk_categories` | 23 | one derived category per district |
| `assessment_blocks` | 153 | CGWB's real unit of assessment |

**The two unique constraints are load-bearing.** They are beyond what the spec
asked for. Without them, running the ingestion a second time silently doubles
every row — and every average in the system quietly becomes wrong, with nothing
to indicate it. With them, re-running is a no-op.

### The invariant everything depends on

`water_level_m` is **depth to water in metres below ground.** Larger means
deeper means worse. A **positive** trend is depletion. The "deepest" water table
is the "lowest" water level.

That inversion has caused more bugs here than anything else — it is why the
chart's Y axis is flipped and why the ranking field is `worst`/`best` rather
than `highest`/`lowest`. An earlier version answered *"which district has the
deepest water table?"* with one of the **shallowest**.

### Why `risk_categories` is derived, not transcribed

**CGWB categorises blocks, never districts.** There is no official "Ludhiana is
over-exploited" anywhere in the publication — only 14 block assessments. So the
district category is *derived*: the category held by most of the district's
blocks, ties broken toward the worse one. Because that is a modelling choice,
the block counts are stored beside it as evidence.

---

## 5. Ingestion — `ingest_data.py` (776 lines, the largest file)

It does not assume a fixed column layout. It resolves the columns it needs
against a table of known CGWB header spellings, and handles both shapes these
exports come in:

- **long** — one row per reading, with `DATE` and `WATER_LEVEL`
- **wide** — one row per station, with `Pre-monsoon_2019`, `Post-monsoon_2020`…

**If a required column cannot be resolved it aborts and prints the file's actual
headers** rather than guessing. Guessing here would put wrong numbers in the
database, which is the one thing this project cannot tolerate.

### Cleaning rules, every drop counted by reason

| Rule | Threshold |
|---|---|
| Punjab only, when the file states a state at all | — |
| District must canonicalise | else counted as *unrecognised* and named |
| Station name must be present | — |
| Date must parse | — |
| Water level must be numeric | — |
| Level must be in range | **−5 m to 200 m** — catches `-9999` sentinels and unit errors |
| Coordinates must be inside Punjab | lat 29–33, lon 73–77 — **blanked, not dropped** |

A coordinate outside Punjab is a bad coordinate, so it is blanked rather than
used: a wrong pin on the map is worse than no pin. The row's *reading* is still
good, so the row stays.

Duplicates collapse to one reading per station per date, averaging genuine
repeats.

**`--dry-run` validates and prints the full summary without touching the
database**, and needs no `DATABASE_URL`. The summary includes station and
reading counts, the date range, a per-district breakdown, and every dropped row
with its reason.

> **A trap the summary is designed to catch.** Wide-format seasonal columns
> carry no exact date, so pre-monsoon readings are dated 1 May, monsoon 1 Aug,
> post-monsoon 1 Nov. Trend slopes are then accurate to the *season*, not the
> day — and the summary says so when it happens.

### The four wrong categories

An earlier extraction parsed the wrong table in the CGWB report. Rows spanning a
page break paired a **2024 percentage with a 2023 label**, marking Bathinda's
Sangat block over-exploited at 66% extraction. It was caught by cross-checking
against a second, independent table in the same report. All 23 districts now
agree across both tables.

---

## 6. Document search — `rag_service.py` (145) + `build_rag_index.py` (308)

The narrative chapters of the CGWB report — **printed pages 1 to 78** — split
into overlapping ~900-character passages and embedded locally with
`nomic-embed-text`.

### There is no vector database

The index is two files: `vectors.npy`, a **178 × 768 float32** array (534 KB),
and `chunks.json`. Search is one line:

```python
scores = vectors @ _embed_query(question)
```

Rows are normalised to unit length at build time and the query vector is
normalised too, so **that dot product is cosine similarity.** No index
structure, no service, no Pinecone or FAISS or pgvector — and no such dependency
in `requirements.txt`.

That is a decision, not a gap. At 178 passages a brute-force scan is about
137,000 multiply-adds — microseconds. Approximate-nearest-neighbour indexes
exist to avoid scanning *millions* of vectors; here one would be overhead **and
less accurate**, trading exactness for speed nobody needs. It also means nothing
extra to run, and the index is small enough to commit, so a fresh clone works
without the 7 MB PDF.

Say **semantic search**, not vector database. Embeddings are genuinely used; a
database to store them is not.

### Every passage declares what it is about

```json
{ "page": 58, "section": "Fluoride",
  "districts": ["Bathinda", "Mansa"],
  "scope": "district", "text": "…" }
```

Retrieval takes the **twelve closest** by similarity, then reorders
deterministically: a passage scoped to the district asked about is promoted, one
scoped to a *different* district is demoted hard. A passage naming more than six
districts is a survey of the state, so it is marked statewide and left alone.
Anything below **0.55** similarity is discarded rather than answered from.

> **Two real defects this replaced.**
>
> **Every citation was nine pages out.** The report's printed numbering runs
> nine behind the PDF's, and passages cited the PDF index — so a fluoride
> passage was cited as page 67, which is the **Iron** section. Plausible, and
> about the wrong contaminant.
>
> **A quarter of the corpus was not the report.** The indexed range ran past the
> narrative into twelve pages of government notifications and fourteen of plates
> and figures, whose extracted "text" is chart axis labels like
> `FIGURE-7 / 75.18% / 2.61%`. Those competed with the actual chapters.
> 254 chunks became 178, all of them prose.

---

## 7. The SQL that matters — `groundwater_service.py` (360)

### Current level

Find the latest reading date in the district, take every station reporting that
day, then **cite the station nearest the district mean** — not an arbitrary one.
An answer should quote a representative well rather than whichever row came back
first. It returns the cited station, the district mean, and how many stations
reported, so a single reading can be shown in context.

### Depletion rate

Not one line through pooled readings. **Each station is fitted separately** with
`numpy.polyfit`, and the **median** of those slopes is reported.

Stations rotate in and out of CGWB's network over the years. Pooling every
reading lets a handful of unusually deep wells that only appear recently
dominate the slope and manufacture a trend that is not there.

A station qualifies with **≥ 8 readings spanning ≥ 3 years**. Roughly a quarter
of Punjab's stations fail that. If *nothing* qualifies, relaxed thresholds
(4 readings, 2 years) are tried — **and the answer discloses that it had to.**

The `confidence_note` is written by the service, not the model:

```
"Median of 75 station trends fitted over 2009-01-01 to present;
 66 of 75 stations show a falling water table."
```

---

## 8. The model boundary — `llm_client.py` (252)

**The only file in the project that calls a language model.** One interface, two
providers; the agents never branch on which is in use.

Both paths return a **validated Pydantic object**. Ollama constrains decoding to
the JSON Schema; the Claude API uses structured outputs. No agent ever parses
free text.

### `temperature: 0` is not determinism

The same prompt returned **91 tokens** once and ran to its **2,048-token cap**
the next time, truncated mid-string and unparseable. So there are three
attempts: more room, then **a different sample** — because greedy decoding
cannot escape a repetition loop it has entered.

When all three fail the result is `LLMGarbledResponse`, deliberately distinct
from "the model is unreachable". Nothing can be done about a model that is down;
a model that rambled has not made the retrieved data any worse, so the data is
shown.

### Fields the model is not allowed to see

`slim_for_prompt()` strips bulk — a 75-name station list becomes
`[75 stations]` — and **withholds fields the checks need**. Shown a field called
`projected_year`, the model cited the field name as a source:
*"around 2044 (projected_year: 2044, citation: projection.confidence_note)"*.

---

## 9. The agents

| File | Lines | Model? |
|---|---|---|
| `query_understanding.py` | 206 | yes |
| `retrieval.py` | 142 | no |
| `calculation.py` | 108 | no |
| `response.py` | 74 | yes |
| `grounding.py` | 344 | no |
| `verification.py` | 51 | yes — advisory only |
| `orchestrator.py` | 705 | wires them together |

### Query understanding

Free text → structured intent, via constrained JSON. Then **the district is
re-canonicalised in Python** — the model is not trusted to spell it, because a
near-miss reaches SQL and silently returns nothing.

It also resolves follow-ups. The last four turns are context, which handles
*"and what about Moga?"*. One shape needed more:

> After discussing Bathinda and Moga, *"which of those two is worse?"* was
> classified as a ranking, measured against all 23 districts, and answered
> **Barnala** — never mentioned. It **passed verification**, because Barnala
> genuinely is in the ranking data.

### Grounding — eight checks, blocking

| # | Requires | What got through without it |
|---|---|---|
| 1 | Citations name something in the data | A Bathinda station cited for a Ludhiana figure — *approved by the model reviewer* |
| 2 | Figures match a value, with rounding tolerance | Plausible invented numbers |
| 3 | Districts named are covered by the data | Drift to a neighbouring district |
| 4 | Unofficial thresholds not credited to CGWB | "the 30 m threshold set by CGWB" |
| 5 | A projected year is the computed year | "approximately 20 years (2034)" — it is 2044 |
| 6 | A figure with a unit matches a value *of that unit* | "a reference depth of 20.1 metres" — 20.1 is *years* |
| 7 | A percentage tied to a district comes from a sentence tying them | "In Bathinda, 13.9%…" — a Punjab-wide figure |
| 8 | A count of Punjab's districts is Punjab's real one | "2 of Punjab's 3 assessed districts" — Punjab has 23 |

**Checks 1–4 ask whether a number is in the data. That is not enough.** In a
projection answer *every* number is in the data somewhere, so the model can take
a real figure and attach it to the wrong claim while a membership test sees
nothing wrong.

`20.1` is real — it counts years, and the sentence called it a depth.
`13.9%` is real — it is Punjab's, and the sentence gave it to Bathinda.
`3` is real — it counts the districts compared, and the sentence called them all
of Punjab.

### Why the model reviewer cannot veto

It catches nuance rules cannot — a dropped caveat, a projection stated as fact.
But it also objects to figures that are genuinely present, so it triggers **one
rewrite, never a block**. And if that rewrite introduces a grounding failure the
original never had, the rewrite is **discarded and the first draft kept**.

> That rule exists because of a real regression. Told to mention the pumping
> limit, a rewrite credited the 30 m figure to CGWB — and a first draft that had
> grounded clean was being replaced by a data dump on the strength of a nitpick.

---

## 10. The API — `routers/` (191 lines total)

| Endpoint | Notes |
|---|---|
| `POST /chat` | The pipeline, one JSON response |
| `POST /chat/stream` | The **same generator**, one server-sent event per step |
| `GET /tools/current_level` `depletion_rate` `risk_category` `compare` `blocks` | Callable standalone with curl |
| `GET /health` | Database and model reachability, **without spending tokens** |

**`/chat` and `/chat/stream` cannot diverge.** `handle_chat()` consumes
`run_chat()` and returns whatever it ends with. Two code paths answering one
question differently is exactly the class of bug this project keeps finding, so
there is one — and a test asserts the stream's final event equals what `/chat`
returns.

The streaming endpoint opens its **own database session inside the generator**
rather than taking one by dependency: a FastAPI dependency is torn down when the
handler returns, which for a streaming response is *before* the body is
produced. The session would be closed under the pipeline mid-query.

Errors say what to do next — an unknown district returns 404 with the list of
valid districts in the body.

CORS uses **explicit origins, never `*`**.

---

## 11. Tests — `tests/` (1,371 lines, 133 tests, ~1 second)

Pure functions only: no model, no database, no network.

| File | Covers |
|---|---|
| `test_grounding.py` | All eight checks, including the four failures that shipped |
| `test_sources.py` | Naming a derived figure's source, citation dedupe, garbled-draft fallback |
| `test_streaming.py` | The event sequence, and that the stream ends with what `/chat` returns |
| `test_calculation.py` | The projection, its chart line, which fields the model may see |
| `test_rag.py` | Page offset, section map, chunk metadata, the rerank |
| `test_chart_payloads.py` | Which visual an intent earns |
| `test_followups.py` | Resolving "those two" against the conversation |
| `test_districts.py` | Canonicalisation across CGWB's spellings |

```bash
cd backend && python -m pytest tests/
```

> Writing these found a bug in the tests, not the code: `is_punjab` reads a
> **state** column, so `is_punjab("Ludhiana")` is correctly `False`. The first
> test asserted the opposite.

---

## 12. Talking points, if you are asked about the backend

- **Three of the five pipeline stages call no model at all.** Retrieval is a
  dictionary lookup, calculation is numpy, verification is plain Python.
- **The unique constraints** are a good answer to *"how do you handle bad
  data?"* — re-running ingestion is a no-op instead of silently doubling.
- **The median-of-per-station-trends** decision shows statistical care: pooling
  would let rotating stations manufacture a trend.
- **The eight checks with their bug stories** are the strongest technical
  material in the project. Checks 5–8 exist because a *real* figure was attached
  to the wrong claim.
- **No vector database, with the arithmetic to justify it** — 137,000
  multiply-adds against an approximate index that would be slower to justify and
  less accurate.
- It runs **fully offline**: local model, local embeddings, local Postgres, no
  API key, no per-query cost.
