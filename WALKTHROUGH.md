# How a question becomes a checked answer

Every layer, in the order data moves through it — from 36,879 CGWB readings in
Postgres to a sentence nobody had to take on trust.

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the file-by-file detail,
[DEMO.md](DEMO.md) for the runbook, [HANDOFF.md](HANDOFF.md) for what is still
weak.

---

## 1. The shape of the system

Four layers. Each one only talks to the layer below it.

| | Layer | What is in it |
|---|---|---|
| A | **Data** | Postgres — four tables. Plus a committed vector index for the CGWB report. |
| B | **Services** | `groundwater_service` holds every SQL query; `rag_service` holds document search; `llm_client` is the only place a model is called. |
| C | **Agents** | Six small modules, wired by an orchestrator. This is where a question becomes an answer. |
| D | **API + browser** | FastAPI exposes the pipeline twice — plain and streaming — and React renders it. |

The important structural decision is that **the service layer has no FastAPI
imports at all**. The agents call the SQL functions directly as Python. Nothing
loops back out over HTTP to talk to itself, so there is one code path to a
number rather than two.

### The invariant everything depends on

`water_level_m` is **depth to water, in metres below ground**. A larger number
means the water is deeper down, which is *worse*. So a *positive* trend is
depletion, and the "deepest" water table is the "lowest" water level.

That inversion has caused more bugs in this project than anything else — it is
why the trend chart's Y axis is flipped, and why the ranking field is called
`worst`/`best` rather than `highest`/`lowest`.

---

## 2. What is in the database

| Table | Rows | What it holds |
|---|---|---|
| `stations` | 1,607 | Name, district, latitude, longitude. Unique on (name, district). |
| `readings` | 36,879 | One water-level measurement, with a date. Unique on (station, date). |
| `risk_categories` | 23 | One derived category per district, plus the block counts behind it. |
| `assessment_blocks` | 153 | CGWB's actual unit of assessment: block, extraction %, category. |

Those two unique constraints are not decoration. Without them, running the
ingestion script a second time silently doubles every row and every average in
the system quietly becomes wrong. With them, re-running is a no-op.

### Why `risk_categories` is the interesting table

**CGWB categorises blocks, never districts.** There is no official "Ludhiana is
over-exploited" anywhere in their publication — only 14 individual block
assessments. A district-level category therefore cannot be transcribed; it has
to be *derived*.

The rule: the category held by most of the district's blocks, ties broken
toward the worse category. That is a modelling choice, so the block counts are
stored alongside it — which is why an answer can say "14 of 14 blocks
over-exploited" rather than just asserting a label.

> **What that cost to get right.** An earlier extraction read the wrong table in
> the report and produced **four wrong categories** — rows spanning a page break
> paired a 2024 percentage with a 2023 label, marking a block over-exploited at
> 66% extraction. It was caught by cross-checking against a second, independent
> table in the same report. Both tables now agree for all 23 districts.

---

## 3. Two knowledge sources, and the rule that separates them

This is the single most important design decision in the project.

The database knows **how much** water there is. It contains no water quality
data whatsoever — no uranium, no nitrate, no salinity. Those live in CGWB's
published report, which is indexed for semantic search.

| Question | Source | Why |
|---|---|---|
| "Level in Bathinda?" | Postgres | An exact figure with a station and a date |
| "How fast is it falling?" | Postgres | Computed from readings |
| "Is it safe to drink?" | Report | The database has no quality data at all |
| "Why is it falling?" | Report | An explanation, not a measurement |

**A numeric question must never go to the document search.** Retrieving prose
*about* a figure loses the station and the date — the two things that make the
figure checkable. A passage saying "levels have fallen sharply in central
Punjab" cannot be verified against anything; a row saying `18.15 m at Basian Bet
M on 2024-01-01` can.

---

## 4. One question, traced all the way

*"How many years until Ludhiana hits critical depth?"* — with the real values it
produces.

### Step 1 — Understanding *(model)*

The question, plus up to four previous turns, goes to the model with a schema
attached. Ollama constrains decoding to that JSON Schema, so the reply is valid
by construction rather than parsed hopefully:

```json
{ "intent": "years_to_critical", "district": "Ludhiana" }
```

The district is then **re-canonicalised in Python**. The model is not trusted to
spell it — a near-miss would reach SQL and silently return nothing.

### Step 2 — Retrieval *(no model)*

A dictionary lookup, not a decision. `years_to_critical` maps to three service
calls, and they return:

```
current_level    18.15 m at Basian Bet M, 2024-01-01
                 22 stations reporting, district mean 19.88 m
depletion_rate   0.504 m/year, median of 75 station trends
risk_category    over-exploited, 14 of 14 blocks
```

### Step 3 — Calculation *(no model)*

Plain arithmetic over those numbers:

```
(30.0 - 19.88) / 0.504  =  20.1 years
2024 + 20.1             ->  reaches 30 m around 2044
```

The 30 m is a **stated pumping limit, not a CGWB threshold** — CGWB publishes no
depth threshold at all. The agent attaches that caveat to its own output so the
answer cannot quietly drop it.

> **Why the year is computed here and not by the model.** It used to be left as
> arithmetic for the model, which wrote *"approximately 20 years (2034)"*. The
> span was right and the year was invented. Now the pipeline states the year,
> and a check verifies whatever the model writes.

### Step 4 — Response *(model)*

The model receives the data as JSON and writes prose around it. Before it does,
two things happen to that JSON:

- **Bulk is stripped.** A 75-name station list becomes `[75 stations]` — the
  model never cites them individually.
- **Some fields are withheld.** Shown a field called `projected_year`, the model
  cited the field name as if it were a source: *"(projected_year: 2044)"*. The
  checks need that field; the model does not get to see it.

### Step 5 — Verification *(code first)*

Eight plain-Python checks run against the retrieved data — section 8 below. Then
a model reviews for nuance, but only advisory: it can trigger one rewrite, never
a block.

### Step 6 — Assembly *(no model)*

Citations, chart and map are built **from the data**, not from anything the
model said. The model has flags for "this needs a chart" and it left them false
on questions that obviously wanted one, so the decision is a rule keyed on
intent instead.

---

## 5. The agents, one by one

| Agent | In → out | Model? |
|---|---|---|
| Query understanding | Text + history → structured intent | yes |
| Retrieval | Intent → rows or passages | no |
| Calculation | Rows → projection + caveats | no |
| Response | Data → prose | yes |
| Grounding | Prose + data → list of faults | no |
| Verification | Prose + data → advisory verdict | yes |

The orchestrator wires them together and owns every decision about what the user
finally sees. It is also where the failure paths live — section 9.

### Follow-up questions

The last four turns are passed to query understanding as context, which is
enough for *"and what about Moga?"* or *"how fast is it falling there?"* to
resolve. One shape needed more than context:

> After discussing Bathinda and Moga, *"which of those two is worse?"* was
> classified as a ranking, measured against all 23 districts, and answered
> **Barnala** — a district nobody had mentioned. It passed verification, because
> Barnala genuinely is in the ranking data.
>
> A superlative pointing back at the conversation is now converted to a
> comparison of the districts already discussed — but only when the question
> names no district of its own and recent turns named between two and four.

---

## 6. What the SQL really does

Two queries carry most of the system. Both are more careful than they look.

### Current level

Find the latest reading date in the district, take every station reporting on
that date, then — and this is the part worth knowing — **cite the station
nearest the district mean**, not an arbitrary one. A district's answer should
quote a representative well rather than whichever row came back first.

It returns the cited station *and* the district mean *and* how many stations
reported, so an answer can show the single reading in context.

### Depletion rate

Not one line through all pooled readings. Each station is fitted **separately**
with `numpy.polyfit`, and the **median** of those slopes is reported.

Why: stations rotate in and out of CGWB's network over the years. Pooling every
reading lets a handful of unusually deep wells that only appear in recent years
dominate the slope and manufacture a trend that isn't there.

A station qualifies only with **8 or more readings spanning at least 3 years**.
Roughly a quarter of Punjab's stations fail that. If *nothing* qualifies,
relaxed thresholds (4 readings, 2 years) are tried — and the answer discloses
that it had to.

```
rate_m_per_year   0.504
stations_used     75 stations
confidence_note   "Median of 75 station trends fitted over
                   2009-01-01 to present; 66 of 75 stations
                   show a falling water table."
```

That `confidence_note` is written by the service, not the model, and the
response agent is instructed to reflect its substance.

---

## 7. How the document search works

178 passages from one CGWB report, and a rerank that knows what each one is
about.

The report's narrative chapters — printed pages 1 to 78 — are split into
overlapping ~900-character passages and embedded locally with
`nomic-embed-text`.

### There is no vector database

The whole index is two files: `vectors.npy`, a **178 × 768 float32** NumPy array
(534 KB), and `chunks.json` holding the passages and their metadata. Searching
is one line:

```python
scores = vectors @ _embed_query(question)
```

The rows are normalised to unit length at build time and the query vector is
normalised too, so **that dot product is cosine similarity**. No index
structure, no separate service, no Pinecone, Chroma, FAISS or pgvector — and no
such dependency in `requirements.txt`.

This is a decision, not an omission. At 178 passages a brute-force scan is about
137,000 multiply-adds — microseconds. Approximate-nearest-neighbour indexes
exist to avoid scanning *millions* of vectors; at this scale one would be pure
overhead and **less accurate**, trading exactness for speed we do not need. It
also means nothing extra to run, deploy or have fail on demo day, and the index
is small enough to commit, so the pipeline runs on a fresh clone without the
7 MB source PDF.

Say **semantic search**, not vector database. Embeddings are genuinely used; a
database to store them is not.

### Every passage declares what it is

```json
{ "page": 58,
  "section": "Fluoride",
  "districts": ["Bathinda", "Mansa", "..."],
  "scope": "district",
  "text": "..." }
```

Retrieval takes the twelve closest passages by similarity, then **reorders them
deterministically**: a passage scoped to the district being asked about is
promoted; one scoped to a *different* district is demoted hard. A passage naming
more than six districts is a survey of the state, not a local report, so it is
marked statewide and left alone.

> **Two real defects this replaced.**
>
> *Every citation was nine pages out.* The report's printed page numbering runs
> nine behind the PDF's, and passages cited the PDF index. A fluoride passage
> was cited as page 67 — which is the *Iron* section. Plausible-looking, wrong
> contaminant.
>
> *A quarter of the corpus was not the report.* The indexed range ran past the
> narrative into twelve pages of government notifications and fourteen of plates
> and figures, whose extracted "text" is chart axis labels like
> `FIGURE-7 / 75.18% / 2.61%`. Those were competing with the actual chapters for
> retrieval.

---

## 8. The eight checks

Plain Python over the retrieved data. They cannot hallucinate, because they do
not generate anything. Every one of them exists because something got through.

| # | What it requires | What got through without it |
|---|---|---|
| 1 | Every parenthesised citation names something in the data | A Bathinda station cited as the source for a Ludhiana figure — and the model reviewer approved it |
| 2 | Every figure matches a value in the data | Invented numbers that read plausibly |
| 3 | Every district named is one the data covers | Answers drifting to a neighbouring district |
| 4 | A non-official threshold is not credited to CGWB | "the 30 m threshold set by CGWB" — CGWB sets no such threshold |
| 5 | A projected year is the year the data computed | "approximately 20 years (2034)" when the projection gives 2044 |
| 6 | A figure with a unit matches a value *of that unit* | "a reference depth of 20.1 metres" — 20.1 is the number of *years* |
| 7 | A percentage tied to a district comes from a sentence tying them | "In Bathinda, 13.9% of samples…" — a Punjab-wide figure |
| 8 | A count of Punjab's districts is Punjab's real one | "2 of Punjab's 3 assessed districts" — Punjab has 23 |

### The pattern in checks 5 through 8

The first four ask *is this number in the data?* That is not enough. In a
projection answer **every** number is in the data somewhere — so the model can
pick up a real figure and attach it to the wrong claim, and a membership test
sees nothing wrong.

`20.1` is real; it is a count of years, and the sentence called it a depth.
`13.9%` is real; it is Punjab's, and the sentence gave it to Bathinda. `3` is
real; it counts the districts compared, and the sentence called them all of
Punjab. **Being in the data is not the same as measuring what the sentence says
it measures.**

### Why the model reviewer is only advisory

It catches nuance rules cannot — a dropped caveat, a projection stated as
certainty. But it also objects to figures that are genuinely present, so it
triggers one rewrite rather than a block. And if that rewrite introduces a
grounding failure the original never had, the rewrite is discarded and the first
draft kept. An advisory reviewer must not be able to veto a correct answer.

---

## 9. Every way it can fail, and what happens

Six distinct paths. None of them shows an unverified answer as if it were
verified.

| What went wrong | What the user gets |
|---|---|
| Question is out of scope | A refusal naming the system's actual coverage |
| Question is about water quality, from the database path | A refusal explaining that an extraction category says nothing about drinking safety |
| District is real but has no readings *(Malerkotla)* | Its category, and a plain statement that no readings exist |
| Grounding rejects the draft, twice | The retrieved figures printed raw, with the reason, flagged unverified |
| Model returns unparseable output three times | The retrieved data, shown rather than an apology — a rambling model has not made the data worse |
| Model is unreachable | An error that says so, and suggests rephrasing |

> **Worth knowing about the model itself.** `temperature: 0` does not mean
> deterministic here. The same prompt returned 91 tokens once and ran to its
> 2,048-token cap the next time, truncated mid-string and unparseable. So there
> are three attempts: more room, then a different sample to break a repetition
> loop that greedy decoding cannot escape.

---

## 10. What the browser does with the answer

The response carries five things, and the interface renders each of them.

```json
{ "answer":      "...prose...",
  "citations":   [ { "station": "...", "date": "..." } ],
  "chart_data":  { "type": "line" },
  "map_data":    { "points": [], "not_plotted": [] },
  "verified":    true,
  "source":      "database" }
```

- **A line chart** for one district over time, drawn as a cross-section with the
  ground filled in above the water table — and the Y axis inverted, so a falling
  line means falling water.
- **Ranked bars** when several districts are compared, coloured by CGWB
  category, with the answering district at full strength and the rest dimmed.
- **A map** for several districts, which names any district it could not plot
  rather than quietly showing fewer pins.
- **A footer** stating that every figure was checked, which source answered, and
  what backed it.

### The progress stream

Answering takes 3 to 15 seconds. Rather than one blob at the end, the pipeline
reports each step as it reaches it — *"Retrieved — 22 stations reporting on
2024-01-01"*, *"Checking every figure — 7 checks over 7 figures"* — with the
first event landing about 7 ms after asking.

Both endpoints run **the same generator**: the plain one consumes it and returns
whatever it ends with. Two code paths answering one question differently is
exactly the bug this project keeps finding, so there is only one.

The draft itself is deliberately **not** streamed word by word. That would mean
showing figures the checks may be about to reject — and given the model
sometimes rambles to 21,000 characters before failing, a reader would watch it
happen.

---

133 tests cover the deterministic parts:

```bash
cd backend && python -m pytest tests/
```
