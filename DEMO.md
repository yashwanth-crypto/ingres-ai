# Demo runbook

Timings measured through the API on the local model, one question at a time.
The seven-question script is about **40 seconds** of answer time, so budget four
to five minutes with talking.

---

## Before the slot

**Start 15 minutes early.** The first model call loads ~4.7 GB into VRAM and
takes about 45 seconds. The backend warms it in the background at startup, but
only once the process is up.

```bash
cd C:\multi-agent-INGRES\backend && python -m uvicorn app.main:app --port 8000
```

```bash
cd C:\multi-agent-INGRES\frontend && npm run dev
```

Then open **http://localhost:5173** and check:

- [ ] Header dot is **green** and reads `ollama`
- [ ] Ask one throwaway question ("status in Moga") and confirm it answers in a
      few seconds — this proves the model is warm
- [ ] **Reload the page** so you start with an empty conversation
- [ ] Laptop set to never sleep (this project lost both servers to sleep once)
- [ ] Internet on if you want map tiles; everything else works without it

> **One question at a time.** Nothing queues requests in front of the model, and
> two at once collapse: a question that answers in 13 seconds took **183** with a
> second in flight. If a judge reaches for the keyboard while an answer is
> running, let the current one finish first. This is the single most likely way
> the demo goes wrong.

---

## The script

Every answer streams its progress while it works — *"Retrieved — 22 stations
reporting on 2024-01-01"*, *"Checking every figure — 7 checks over 7 figures"*.
**Read a line or two aloud as they appear.** That list is the pipeline, and it
is the most convincing thing on screen.

### 1. "What's the groundwater status in Bathinda?" — 3s

> 15.91 m below ground (Kot Shamir, 2024-01-01), over-exploited.

A **trend chart** drawn as a cross-section: earth fill above the line, and the
**Y axis inverted** so a falling line means a falling water table. The footer
says *every figure checked against the source*, tagged **Monitoring database**.

### 2. "Which districts in Punjab are over-exploited?" — 5s

> 20 of Punjab's 23 assessed districts are over-exploited.

Renders the **map**. Read the footnote aloud:

> *Malerkotla is categorised but not shown — no monitoring stations there.*

It says what is missing instead of hiding it.

### 3. "Which district has the worst water table?" — 4s

> Barnala, 43.22 m below ground.

**Ranked bars**, worst first, coloured by CGWB category, with Barnala at full
strength and the rest dimmed. A superlative names no district, so this needs
every district ranked — and an earlier version answered it with one of the
*shallowest*.

### 4. "How many years until Ludhiana hits critical depth?" — 8s

> About 20 years at 0.504 m/year, reaching 30 m around 2044.

The flagship. The chart draws the projection **dashed into a shaded future**,
ending on a marked crossing of the 30 m line.

Say clearly that **CGWB publishes no "critical depth"** — its categories measure
extraction against recharge, not metres. 30 m is a stated pumping limit and the
answer says so. The projection is deterministic Python, not the model.

### 5. Follow-ups — ask both, ~4s each

```
And what about Moga?
```
```
Which of those two is worse?
```

It carries the conversation, and the second compares **Bathinda and Moga** —
not all 23. Worth showing: it is what makes it a conversation rather than a
search box.

### 6. "Is the water in Bathinda safe to drink?" — 12s

Badge flips to **CGWB report** and the citation becomes a page number. The
hybrid-retrieval moment: the database holds no quality data at all, so this
comes from the report.

The slowest answer — fill the gap by explaining that numbers never go through
RAG, because retrieving prose *about* a figure loses the station and the date.

### 7. "What's the groundwater status in Mumbai?" — 1s

Graceful refusal naming its actual scope.

---

## The strongest thing to say

If asked how you know it is not hallucinating:

> During testing the model produced an answer citing **Kot Shamir** — a Bathinda
> station — as the source for a **Ludhiana** figure. The LLM verifier approved
> it. So verification is not left to a model: eight plain-Python checks test
> every citation, figure, district, year and unit against the retrieved data
> before the answer is shown. They cannot hallucinate, because they do not
> generate anything.

Two more if there is time:

- **CGWB categorises blocks, not districts.** The district category is derived
  (predominant block, ties to the worse category), the block counts are stored
  as evidence, and the extraction was cross-checked against a second table in
  the same report — which caught 4 wrong categories on the first attempt.
- **It runs fully offline** on a free local model. No internet, no API key, no
  cost. Running on a 7B is the point: the guarantees come from the checks, not
  from the model being good.

---

## Safer ground

- **"Why is groundwater falling in Punjab?"** now works, but takes ~20 seconds —
  the longest answer in the system. *"What does CGWB recommend for Punjab?"*
  makes the same point in 7.
- Anything needing two hops ("compare the trend in the three worst districts")
  is still beyond it.

---

## If something breaks

| Symptom | Fix |
|---|---|
| Header dot red | Backend died — restart uvicorn |
| First answer hangs ~45s | Model was cold; fast from then on |
| Everything crawls | Two requests at once. Wait for the first to finish |
| Progress list stalls on one line | That step is genuinely slow, not stuck. The drafting step is the long one |
| "could not produce an answer" | A guard rejected the draft. Rephrase, and say the safeguard just fired — that *is* the feature |
| Answers slow across the board | Close other GPU applications |
| Everything is broken | `/tools/current_level?district=Bathinda` in a browser tab still returns real data |

---

## On the model

`LLM_PROVIDER=anthropic` would switch to Claude for about $0.02 a question and
better prose. **This was deliberately not done.** The system is meant to hold up
on a free local model, and "correct answers on a 7B" is a stronger claim than
"we used a good model". If a judge asks why the prose is plain, that is the
answer — and the switch is one line if they want to see it.
