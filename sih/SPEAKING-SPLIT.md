# NexGen Devs — who says what

**SIH25066 · Development of an AI-driven Chatbot for INGRES as a virtual
assistant · Smart Automation · Software**

Six speakers, six slides — but not one slide each in the obvious way. The title
page is twenty seconds and slide 2 is three times that, so the thin slides are
paired with a job (opening, closing, Q&A) to even out the time.

Target: **about 7 minutes** of speaking. Cut instructions at the end if the slot
is 5.

---

## The rule for everyone

**Do not read the slide.** The panel can read. Say the thing that is *not* on
the slide — the reason, the number behind it, the story. Your bullets are the
prompt, not the script.

And everyone should be able to answer this one, because it will come and it is
the question the whole project answers:

> **"How do you know it isn't hallucinating?"**
>
> During testing the model produced an answer citing **Kot Shamir** — a Bathinda
> station — as the source for a **Ludhiana** figure. A second model, asked to
> check it, approved it. That is why verification is not left to a model. Eight
> plain-Python checks test every citation, figure, district, year and unit
> against the retrieved data before an answer is shown.

---

## Speaker 1 — Opening and the problem
**Slide 1 · about 60 seconds**

Your job is the hook. There is almost nothing on this slide, so the words carry
it.

- Introduce the team and the problem statement in one line each
- **Punjab is draining its groundwater faster than it refills**
- **20 of Punjab's 23 assessed districts are classified over-exploited by CGWB.**
  Say this number slowly — it is the reason the project exists
- The data to see this already exists. It sits in PDFs and departmental portals
  that a farmer, a panchayat officer or a journalist cannot query
- **The constraint is access, not data collection**

> **Hand over:** "So the data is there. The hard part is getting an answer out
> of it that you can trust — [Speaker 2] will show you what we built."

**You own:** *"Why this problem?"* · *"Who asked for this?"*

---

## Speaker 2 — The solution, and why it is different
**Slide 2 · about 90 seconds — the longest slot, and the most important**

This is the pitch. If the panel remembers one slide, make it this one.

- Ask in plain English, get an answer with a chart, a map, and **a citation for
  every figure**
- **Figures come from SQL over 36,879 CGWB station readings — never from the
  language model.** The model writes prose *around* numbers it was handed
- Two sources by question type: the database for *how much* water, the CGWB
  report for quality and causes
- **Then the line that separates us:** verification-first. Eight deterministic
  checks can block an answer before it is shown. Code cannot hallucinate,
  because it does not generate anything
- **Tell the Kot Shamir story here.** It is the strongest thirty seconds in the
  presentation
- Runs fully offline on a free local model — no internet, no API key, no cost
  per query

> **Hand over:** "That is what it does. [Speaker 3] will show you how it is
> built."

**You own:** *"Isn't this just a wrapper around ChatGPT?"* — three of the five
stages involve no language model at all.

---

## Speaker 3 — Technical approach
**Slide 3 · about 80 seconds — give this to the most technical speaker**

- Walk the pipeline **left to right**: Query understanding → Retrieval →
  Calculation → Response → Verification
- Point at the colours: **three of the five stages involve no language model.**
  The model understands the question and writes the sentence. It supplies no
  number at any point
- The stack: FastAPI, PostgreSQL, NumPy, React, and Ollama running qwen2.5:7b
  locally
- **No vector database** — 178 passages is a NumPy dot product in microseconds.
  An index would be overhead and less accurate at this scale
- Then the provenance strip: CGWB CSV exports become 36,879 readings in
  Postgres; the CGWB report becomes 178 indexed passages

> **Hand over:** "It is built and it runs. [Speaker 4] will tell you what that
> cost and what could still go wrong."

**You own:** *"Which model?"* · *"Why not a vector database?"* · *"Why local
inference?"*

---

## Speaker 4 — Feasibility, risks and how we handle them
**Slide 4 · about 80 seconds**

This slide wins credibility. Naming your own limits reads as engineering
maturity — do not soften it.

- **Built and running end to end on real CGWB data — a working prototype, not a
  concept.** 133 automated tests
- Runs on one machine with no runtime network dependency, so zero recurring cost
  and nothing to fail on venue wifi
- Then be straight about the risks: a model inventing a plausible figure;
  single-user with no request queue; one report in the corpus; data published
  to 2024, not live; not deployed because the development network blocked every
  database port
- **Pair each risk with its answer.** Eight blocking checks plus an advisory
  reviewer — and when verification fails, **it shows the raw data marked
  unverified rather than a confident sentence**

> **Hand over:** "That is what it costs. [Speaker 5] will tell you what it is
> worth."

**You own:** *"What happens when it gets something wrong?"* · *"Why isn't it
deployed?"*

---

## Speaker 5 — Impact and benefits
**Slide 5 · about 75 seconds**

- Name the audience first: farmers and panchayats deciding where and how deep to
  drill; district and block officials; CGWB field staff; researchers and
  students
- **Social** — groundwater status becomes answerable by anyone who can type a
  question, and every answer is citable, so a decision taken from it can be
  audited
- **Economic** — better-informed borewell and cropping decisions; no licensing
  or per-query cost, so a department can deploy it without a budget line
- **Environmental** — point at the map. **20 of 23 districts in red.** Trend and
  projection views turn a slow crisis into something a non-specialist can see

> **Hand over:** "And none of that works unless the data is real — [Speaker 6]."

**You own:** *"Who actually uses this?"* · *"How does this change a decision?"*

---

## Speaker 6 — Sources, close, and Q&A
**Slide 6 · about 60 seconds, then you lead questions**

- Everything traces to two published CGWB sources: the *Ground Water Resources
  of Punjab 2024* report and the National Water Data Portal
- **The methodology note is worth saying out loud:** CGWB classifies assessment
  **blocks**, never districts. Our district categories are derived, with block
  counts stored alongside as the evidence — and cross-checking against a second
  table in the same report **caught four wrong categories**
- Close on the claim: *"Anyone can put a chatbot on a dataset. We built the part
  that checks it."*

> **Then:** "We'd be glad to take questions."

**You own:** the first thirty seconds of any question — repeat it back, then
route it to whoever owns it. Nobody talks over anybody.

---

## Jobs that are not speaking

Assign these too, and not to whoever is talking at that moment.

| Job | What it means |
|---|---|
| **Driver** | Advances slides. Advances only on a handover line, never mid-sentence. |
| **Demo operator** | If there is a live demo: types the question, **one at a time**, and never types while an answer is still running. Two at once collapses the model. |
| **Timekeeper** | Signals at 5 minutes. Speakers 5 and 6 are the ones who compress. |

---

## If the slot is 5 minutes, not 7

Cut in this order:

1. Speaker 3 drops the provenance strip and the stack list — keep the pipeline
   and "three of five stages"
2. Speaker 5 drops Economic, keeps Social and Environmental
3. Speaker 1 drops the team introduction and opens straight on the 20-of-23
   number

**Never cut:** the Kot Shamir story, "three of five stages use no model", or the
honest-limits slide. Those three are the presentation.
