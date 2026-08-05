# Demo runbook

Timings below are measured through the browser UI on the local model, not the
API. Total answer time for the five-question script is **53 seconds**, so budget
around four minutes with talking.

---

## Before the slot

**Start 15 minutes early.** The first model call loads ~4.7 GB into VRAM and
takes about 45 seconds; the backend warms it in the background at startup, but
only after the process is up.

```bash
cd C:\multi-agent-INGRES\backend && python -m uvicorn app.main:app --port 8000
```

```bash
cd C:\multi-agent-INGRES\frontend && npm run dev
```

Then open **http://localhost:5173** and check:

- [ ] Header dot is **green** and reads `ollama`
- [ ] Ask one throwaway question (e.g. "status in Moga") and confirm it answers
      in a few seconds — this proves the model is warm
- [ ] **Reload the page** so you start with an empty conversation
- [ ] Laptop set to never sleep (this session lost both servers to sleep once)

If the dot is red, the backend is down. If it is green but answers hang, Ollama
is not running — `ollama serve`.

---

## The script

### 1. "What's the groundwater status in Bathinda?" — 6s

> Bathinda is 15.91 m below ground (Kot Shamir, 2024-01-01), over-exploited.

Renders a **trend chart**. Point out the Y axis is inverted, so a falling line
means a falling water table. Two citations appear, tagged **MONITORING DATA**.

### 2. "Which districts in Punjab are over-exploited?" — 8s

> 20 of Punjab's 23 assessed districts are over-exploited.

Renders the **map**, 19 pins coloured by category. The footnote is worth
reading aloud:

> *Malerkotla is categorised but not shown — no monitoring stations there.*

19 pins for 20 districts, and the system says why rather than hiding it.

### 3. "How many years until Ludhiana hits critical depth?" — 15s

> ~20 years at 0.504 m/year.

Say clearly that **CGWB publishes no "critical depth"** — its categories
measure extraction against recharge, not metres. 30 m is a stated pumping
limit, and the answer says so. The projection is deterministic Python, not the
model.

### 4. "Is the water in Bathinda safe to drink?" — 21s

Badge flips to **CGWB REPORT**. This is the hybrid-retrieval moment: the
database has no quality data, so it answers from the report and cites a page.

The slowest answer — fill the gap by explaining that numbers never go through
RAG, because retrieving prose about a figure loses the station and the date.

### 5. "What's the groundwater status in Mumbai?" — 4s

Graceful refusal naming its actual scope.

---

## The strongest thing to say

If asked how you know it isn't hallucinating:

> During testing the model produced an answer citing **Kot Shamir** — a
> Bathinda station — as the source for a **Ludhiana** figure. The LLM verifier
> approved it. So verification is not left to a model: plain Python checks every
> citation, figure and district against the retrieved data before the answer is
> shown. It cannot hallucinate, because it does not generate anything.

Two more if there is time:

- **CGWB categorises blocks, not districts.** The district category is derived
  (predominant block, ties to the worse category), the block counts are stored
  as evidence, and the extraction was cross-checked against a second table in
  the same report — which caught 4 wrong categories on the first attempt.
- **It runs fully offline** on a local model. No internet, no API key, no cost.
  One line in `.env` switches to Claude for stronger prose.

---

## Do not ask these

- **"Why is groundwater falling in Punjab?"** — the grounding checks reject the
  draft and it falls back to a data dump. Honest, but not a good look on stage.
  Use *"What does CGWB recommend for Punjab?"* instead (9s).
- Anything needing two hops ("compare the trend in the three worst districts").

---

## If something breaks

| Symptom | Fix |
|---|---|
| Header dot red | Backend died — restart uvicorn |
| First answer hangs ~45s | Model was cold; it will be fast from then on |
| "could not produce an answer" | Guard rejected the draft. Rephrase, or say the safeguard just fired — that *is* the feature |
| Answers slow across the board | Close other GPU applications |
| Everything is broken | `/tools/current_level?district=Bathinda` in a browser tab still returns real data |

---

## Switching to Claude

Edit `backend/.env`, set `LLM_PROVIDER=anthropic` and a real
`ANTHROPIC_API_KEY`, restart the backend. Roughly $0.02 per question, so the
whole demo costs about 10 cents. Better prose and stronger verification; needs
working internet, which the local model does not.
