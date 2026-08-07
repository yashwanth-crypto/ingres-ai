# NexGen Devs — the script, word for word

**SIH25066 · AI-driven Chatbot for INGRES · Smart Automation · Software**

Six speakers, about **seven minutes**. Say these lines. Replace `[NAME]` with the
next speaker's actual name before you rehearse — a handover that says "Speaker 4"
out loud is worse than no handover.

**Bold** = land on this word. **[beat]** = stop for one second. Nothing else.

---

## Speaker 1 — Opening and the problem
*Slide 1 · about 60 seconds*

> Good morning. We're **NexGen Devs**, and we're presenting problem statement
> **SIH25066** — an AI-driven chatbot for INGRES.
>
> Punjab is draining its groundwater faster than it refills. The Central Ground
> Water Board assesses **twenty-three** districts in Punjab. **Twenty of those
> twenty-three are classified over-exploited.** **[beat]** That is not a
> forecast. That is the current, measured position.
>
> And the strange part is that all of this is already known. Decades of
> monitoring readings, block-level assessments, published reports — **the data
> exists.** But it sits inside PDFs and departmental portals that a farmer
> cannot query. Neither can a panchayat officer. Neither can a journalist.
>
> So the problem we chose is not measurement. **It's access.**
>
> **[handover]** The data is there. The hard part is getting an answer out of it
> that you can actually trust. `[NAME]` will show you what we built.

---

## Speaker 2 — The solution, and why it is different
*Slide 2 · about 90 seconds — the most important slot*

> Thank you. Here's what it does.
>
> You ask a question in plain English — *"what's the groundwater status in
> Bathinda?"* — and you get back an answer with a chart, a map, and **a citation
> for every single figure.**
>
> But here's the part that matters. Every number in that answer comes from SQL,
> running over **almost thirty-seven thousand** real CGWB station readings. The
> language model **never supplies a number.** It writes the sentence *around*
> figures we hand it. **[beat]**
>
> We use two sources, and we choose between them by question type. The database
> knows *how much* water there is. The CGWB report knows about quality and
> causes. A question about drinking safety goes to the report. A question about
> a water level goes to SQL.
>
> Now — why go to that trouble? Because we tried the obvious thing first.
> **[beat]** During testing, our model produced an answer that cited **Kot
> Shamir** — a monitoring station in **Bathinda** — as the source for a figure
> about **Ludhiana**. Wrong district. And when we asked a second model to check
> it, **that model approved it.**
>
> So verification is not left to a model. **Eight plain-Python checks** test
> every citation, every figure, every district, year and unit before an answer
> is ever shown. Code cannot hallucinate, because code does not generate
> anything.
>
> And all of this runs **fully offline**, on a free local model. No internet. No
> API key. No cost per question.
>
> **[handover]** That's what it does. `[NAME]` will show you how it's built.

---

## Speaker 3 — Technical approach
*Slide 3 · about 80 seconds — give this to your most technical speaker*

> Thanks. This is the pipeline, and it's five stages.
>
> **Query understanding** turns your question into structured intent.
> **Retrieval** maps that intent to either SQL or a search over the report.
> **Calculation** does the projection maths. **Response** writes the prose. And
> **verification** checks it.
>
> Now look at the colours. **[beat]** **Three of those five stages involve no
> language model at all.** Retrieval is a dictionary lookup. Calculation is
> numpy. Verification is plain Python. The model understands the question and
> writes the sentence — and that is the whole of its job.
>
> The stack is FastAPI, PostgreSQL and NumPy on the backend, React on the front,
> and **Ollama running qwen2.5-7b locally** for inference.
>
> One thing worth calling out: **there is no vector database.** Our semantic
> search is a hundred and seventy-eight passages. That's a NumPy dot product, in
> microseconds. An approximate index would be overhead — and it would be *less*
> accurate at this scale.
>
> And underneath it all: CGWB's CSV exports become thirty-six thousand readings
> in Postgres. The CGWB report becomes a hundred and seventy-eight indexed
> passages.
>
> **[handover]** It's built, and it runs. `[NAME]` will tell you what that cost,
> and what could still go wrong.

---

## Speaker 4 — Feasibility, risks and mitigations
*Slide 4 · about 80 seconds*

> Thank you. Feasibility first.
>
> This is **a working prototype, not a concept.** It runs end to end on real
> CGWB data, today. It runs on one machine with no network dependency at
> runtime — so zero recurring cost, and nothing that can fail on venue wifi. And
> the deterministic core is covered by **a hundred and thirty-three automated
> tests.**
>
> Now the risks. Honestly. **[beat]**
>
> The biggest is the one we've been talking about — a language model inventing a
> plausible figure. Our answer is the eight blocking checks, plus a model
> reviewer that is **advisory only.**
>
> Second: we are **single-user.** One local model, no request queue. Two
> questions at once and it slows badly. A queue fixes that; we didn't need one
> for a single-user demo.
>
> Third: our semantic corpus is **one report**, and the database is CGWB's
> published data through twenty twenty-four. **It is not live.**
>
> And fourth: we have not deployed it, because the network we developed on
> blocked every database port. Nothing in the architecture prevents it — deploy
> inside the cloud network and the restriction disappears.
>
> One last thing. **[beat]** When verification fails, the system does not go
> quiet, and it does not guess. **It shows you the raw retrieved data, marked
> unverified.**
>
> **[handover]** That's what it costs. `[NAME]` will tell you what it's worth.

---

## Speaker 5 — Impact and benefits
*Slide 5 · about 75 seconds*

> Thanks. So — who is this for?
>
> Farmers and panchayats deciding where to drill, and how deep. District and
> block officials. CGWB's own field staff. And researchers, students,
> journalists.
>
> **Socially**, the change is simple: groundwater status becomes answerable by
> anyone who can type a question. And because every answer carries its citation,
> **a decision made from it can be audited afterwards.** For public policy, that
> matters.
>
> **Economically** — better borewell decisions, better cropping decisions, and
> no drilling into a water table that is already falling. There's no licensing
> cost and no per-query cost, so a department can deploy this **without a budget
> line.**
>
> **Environmentally** — look at the map. **[beat]** **Twenty of twenty-three
> districts in red.** That is a slow crisis, and slow crises stay invisible
> until somebody draws them. Our trend and projection views turn depletion into
> something a non-specialist can actually see.
>
> **[handover]** And none of that means anything unless the data underneath is
> real. `[NAME]`.

---

## Speaker 6 — Sources, close, and questions
*Slide 6 · about 60 seconds, then you lead Q&A*

> Thank you. Everything you've seen traces back to two published CGWB sources —
> the **Ground Water Resources of Punjab** report for twenty twenty-four, and
> the **National Water Data Portal** for the station readings. We follow the
> **GEC-2015** assessment methodology, and **BIS** drinking-water limits for the
> quality figures.
>
> One methodology note, because it's the kind of thing that usually gets glossed
> over. **[beat]** CGWB classifies assessment **blocks**. It never classifies
> districts. So the district-level categories our system shows are **derived** —
> and we store the block counts alongside them as the evidence. When we
> cross-checked our extraction against a second table in the same report, it
> **caught four categories we had wrong.**
>
> That's the standard we've tried to hold throughout. **[beat]**
>
> Anyone can put a chatbot on a dataset. **We built the part that checks it.**
>
> We'd be glad to take your questions.

---

## The one line everybody rehearses

It will be asked. Whoever gets it should not look around the room.

> **"How do you know it isn't hallucinating?"**
>
> During testing, our model cited **Kot Shamir** — a Bathinda station — as the
> source for a **Ludhiana** figure. A second model, asked to check it, approved
> it. That's why verification isn't left to a model. **Eight plain-Python
> checks** test every citation, figure, district, year and unit against the
> retrieved data before anything is shown.

---

## Numbers, spoken

Say these the easy way. The precise figure is in brackets if a judge presses.

| Say | Precisely |
|---|---|
| "almost thirty-seven thousand readings" | 36,879 |
| "sixteen hundred monitoring stations" | 1,607 |
| "a hundred and seventy-eight passages" | 178 |
| "twenty of twenty-three districts" | 20 of 23 |
| "a hundred and thirty-three tests" | 133 |
| "twenty twenty-four" | 2024 — never "two thousand and twenty-four" |

---

## If the slot is five minutes

Cut in this order, and nothing else:

1. **Speaker 3** — drop the stack list and the provenance paragraph. Keep the
   five stages and "three of five".
2. **Speaker 5** — drop the Economic paragraph.
3. **Speaker 1** — open straight on "Twenty of twenty-three", skip the
   introduction.

**Never cut:** the Kot Shamir story, "three of five stages use no model", or
Speaker 4's honest limits. Those three are the presentation.
