# Handoff — state, and what to fix next

Read [ARCHITECTURE.md](ARCHITECTURE.md) first for how the system works. This
file is only about what is *weak* and what to do about it.

## Where it stands

Phases 1–6 of the spec are done. Data loaded, six tool endpoints, five agents,
hybrid retrieval, React frontend. 10 of 11 test questions answer cleanly.

Branch `feat/answer-visuals`, ahead of `main`, **no remote**. The work on it:
the projection is drawn, ranked and compared answers get charts, three
verification holes are closed, the RAG index is rebuilt with real metadata and
correct page citations, follow-ups are tested and one broken shape fixed, every
answer says what it was checked against, the pipeline reports each step as it
runs, and there is a 127-test suite.

That is a working system. It is not yet a *good* one, for the reasons below.

---

## The honest problems, worst first

### 1. Only one person can ask at a time

Nothing queues requests in front of Ollama, and two at once degrade far worse
than linearly. A question that answers in 13 seconds on its own took **183**
with a second request in flight — 78 of those seconds on intent extraction
alone. There is no timeout either, so the second asker simply waits.

That is survivable for a demo one person drives, and not survivable if two
judges type at the same time. The cheap fix is a lock and a queued-position
message; the honest one is to say the machine runs one model.

**Streaming is done.** `/chat/stream` reports each step as it reaches it —
first event about 7 ms after asking, against 3–15 seconds of bouncing dots
before. The draft is deliberately not streamed token by token: it would mean
showing figures the checks may be about to reject, and this model intermittently
rambles to 21,000 characters before failing.

### 2. The prose is stilted

Correct, cited, robotic. Every answer follows the same shape because a 7B model
is doing the writing. That is the part that remains.

The field-name citations are gone. *"falling at 1.205 meters per year
(depletion_rate)"* was not a model quirk but a gap: the prompt demanded a source
in parentheses after every number and a derived rate had none to give. Handed
the sentence it should quote, it quotes it.

Switching `LLM_PROVIDER=anthropic` would cost about $0.02 a question and fix
most of this without touching any code. **That has been decided against** — the
system is meant to hold up on a free local model, and "correct answers on a 7B"
is a stronger claim than "we used a good model".

The stilted shape is what that decision costs, and there is no cheap fix for
it. Both leaks that did have one — the field names here, `projected_year`
before — turned out to be the same lesson: the model reaches for a label when
nothing citable is in front of it, so put the right thing in front of it rather
than instructing it not to.

### 3. Follow-up questions work, with one shape now guarded

Tested at last. Five of six shapes already resolved: *"and what about Moga?"*,
*"how fast is it falling there?"*, *"is that getting worse?"*, *"how many years
until it hits critical depth?"*, *"how does it compare to Moga?"*.

The sixth did not. After Bathinda and Moga, *"which of those two is worse?"* was
ranked against all 23 districts and answered **Barnala** — never mentioned, and
verified, because Barnala really is in the ranking data. Fixed in the prompt and
guarded deterministically.

What is still untested: four or more turns deep, a follow-up that changes topic
between the database and the report, and a follow-up after an out-of-scope
refusal. The window is four turns, so anything relying on the fifth is gone.

### 4. The RAG corpus is still one document

Metadata, reranking and citations are done — see below for what changed. What
is left is breadth: it is one report, and any question outside it has no source.
Adding CGWB's annual Year Book, the Punjab Water Regulation Act, or state policy
would widen coverage, and the groundwork for doing that safely now exists.

Two things to know before expanding:

- **The chunker is a fixed 900-character window per page.** A table spanning a
  page break is still sliced mid-row. Table-shaped chunks are dropped rather
  than parsed, which is honest but loses their content entirely.
- **Scope is chunk-level; attribution is sentence-level.** A page carrying a
  Punjab-wide figure and naming a district lower down is one chunk, marked
  district-scoped. Check 7 catches the resulting misattribution at output; the
  metadata cannot express the split. Sentence-level scoping is the real fix and
  matters more as the corpus grows.

**What was done.** The index was rebuilt from printed pages 1–78 rather than PDF
9–114: the old range included twelve pages of government notifications and
fourteen of plates and figures, so a quarter of the corpus was chart axis labels
competing for retrieval. 254 chunks became 178, with 34 table chunks dropped.
Every chunk now carries its chapter, section, the districts it names, and
whether it is district-scoped or statewide, and search reranks on that.

And the citations were simply wrong. The report's printed page runs nine behind
the PDF's, and chunks cited the PDF index — so a fluoride passage was cited as
page 67, which is the **Iron** section. Plausible-looking, wrong contaminant.

### 5. The map is thinner than the pitch

The trend chart, the ranked bars and the message bubble are done. The map is
not: 23 district polygons for a system that advertises 1,607 stations and
36,879 readings. None of that density is visible anywhere, on the one surface
where it would land hardest.

### 6. Nothing produces an unverified answer any more

*"Why is groundwater falling in Punjab?"* used to be rejected by grounding and
fall back to a data dump. It now routes to the report and verifies, three runs
out of three — fixed as a side effect of rebuilding the index, since the
question was always answerable from the narrative chapters and a quarter of the
corpus was chart-axis noise competing with them.

That leaves a smaller problem. Every question tried now verifies, including
Malerkotla with no readings, a Malerkotla comparison, and a Barnala projection.
So the interface's "could not be verified" state has never been seen rendered.
Its styling is confirmed present in the compiled CSS and nothing more. If that
path matters, it needs a deliberate way to exercise it — a test fixture or a
debug flag — because natural questions no longer reach it.

### 7. Not deployed

Spec §10 wants Railway and Vercel. Skipped deliberately: this network blocks
every database port, so Railway was unusable for development. A local demo is
lower-risk, but a live URL is worth more to judges, and the deployed backend
would reach Postgres over Railway's internal network without touching the
firewall.

---

## Smaller things

- **`--reload` cannot be trusted here.** An edit to `llm_client.py` never
  triggered one, and the stale code was only caught because three answers came
  back byte-identical after a change that should have altered them. Restart the
  backend. It also watches `backend/tests/`, so writing a test bounces it.
- **Map tiles need internet.** Everything else runs offline. Consider bundling a
  static Punjab outline as a fallback.
- **Bundle is ~700 KB**, mostly Recharts and Leaflet. Only matters if deployed.
  The bar chart is plain CSS partly for this reason.
- **A persona injection wrapped around a real question** is refused entirely,
  losing the legitimate question. Fails safe, but is over-strict.
- **Document answers can still misattribute by juxtaposition.** Check 7 stops a
  statewide percentage being stated as a district's, so the answer now reads
  "13.9% of samples across Punjab" instead of "in Bathinda, 13.9%". It cannot
  stop a reader drawing the same conclusion from two adjacent sentences, and it
  covers percentages only.
- **Tests cover the deterministic core only.** 127 of them, but nothing
  exercises the SQL layer, the ingestion cleaning rules, or an end-to-end
  `/chat` call. The ingestion rules in particular are pure functions and would
  be easy to add.
- **Nobody has looked at the charts.** Every visual claim rests on geometry and
  computed styles; the browser pane never composited. Open the app and ask the
  Ludhiana projection and "worst water table" questions before trusting them.

---

## What I would do first, in order

1. **Look at the charts, the footer and the progress list.** Nobody has.
   Everything visual in this branch was verified by geometry and computed
   styles, never by eye.
2. **Serialise requests**, or accept that the demo is single-user and say so.
3. **Put the stations on the map**, or accept that the density stays invisible.
5. **More documents in the corpus** — the Year Book and state policy. Metadata
   and reranking are in place, so expansion no longer scales the failure mode.
6. Deploy, if time remains.

---

## Lessons worth keeping

**Counting elements is not verification.** The map was visibly broken — tiles
drawn outside their frame, Punjab rendering as Gujarat — while every DOM check
passed, because `.leaflet-container` and `.leaflet-tile-loaded` were all
present. Leaflet's stylesheet had never loaded. Computed styles caught it;
element counts never would have. Check the rendered result, not the tree.

**The guards only catch what they can see.** Two of the worst bugs found —
answering "deepest water table" with the shallowest district, and answering a
drinking-safety question with an extraction category — were *correctly grounded*
in the data they were given. The fault was upstream, in what got retrieved. No
amount of output verification catches a well-grounded answer to the wrong
question.

**Being in the data is not the same as measuring the right thing.** Three of the
seven checks exist because a wrong figure passed one that only asked whether the
number appeared *somewhere*. In a projection answer every number does. `20.1` is
real; it is the number of years, and the sentence called it a depth. `13.9%` is
real; it is Punjab's, and the sentence gave it to Bathinda.

**Measure the thing, not your instrument.** Two scares while building the
progress stream turned out to be the measuring apparatus. The first stage
appeared to take 962 ms in the browser and 7 ms over curl — the browser tab was
hidden, so `setInterval` was throttled to one second, which is why the numbers
came out as 962 and 1962. Then a request looked hung for three minutes; it was
real, but caused by a second request left in flight, not by the code under test.
Both would have sent someone hunting through the streaming path for a bug that
was not there.

**A single passing run proves very little here.** `temperature: 0` is not
determinism on this stack: the same prompt returned 91 tokens once and ran to
its token cap the next time, unparseable. The drinking-water question had been
failing intermittently for a while behind three consecutive clean runs. Run it
five times.

**Test the thing nobody has run.** `history` was wired in from the first day
and exercised for the first time today. Five of six shapes worked, which is why
it had never been noticed that the sixth answered with a district nobody had
mentioned. Code that has never been run is not working code; it is untested
code that happens to compile.

**Metadata describes a chunk; misattribution happens in a sentence.** Tagging
every chunk with its districts and scope was the right move and did not, on its
own, fix the bug it was aimed at — the offending page genuinely names Bathinda,
just not in the sentence carrying the figure. Structure helps retrieval; only a
check at the same granularity as the error catches the error.

**An advisory reviewer must not be able to veto.** A first draft that grounded
clean was being rewritten on a nuance objection, and when the rewrite introduced
a real grounding failure, the whole answer collapsed to a data dump. Advisory
has to mean advisory in the control flow, not just in the comments.

**The visuals were verified by geometry, never by eye.** The browser pane never
composited, so every claim about the charts rests on coordinates, computed
styles and collision boxes — the projection's endpoint sits on the reference
line at (606, 196), the bars' widths are 100% / 93.75% / 80.06%. That is
stronger than counting elements and weaker than looking. Nobody has yet
confirmed the redesigned trend chart and the bar chart *look* right.
