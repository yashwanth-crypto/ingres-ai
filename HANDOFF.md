# Handoff — state, and what to fix next

Read [ARCHITECTURE.md](ARCHITECTURE.md) first for how the system works. This
file is only about what is *weak* and what to do about it.

## Where it stands

Phases 1–6 of the spec are done. Data loaded, six tool endpoints, five agents,
hybrid retrieval, React frontend. 10 of 11 test questions answer cleanly.

Branch `feat/answer-visuals`, ahead of `main`, **no remote**. The work on it:
the projection is drawn, ranked and compared answers get charts, three
verification holes are closed, the RAG index is rebuilt with real metadata and
correct page citations, follow-ups are tested and one broken shape fixed, and
there is a 102-test suite.

That is a working system. It is not yet a *good* one, for the reasons below.

---

## The honest problems, worst first

### 1. It feels slow and dead while thinking

3–15 seconds of a bouncing-dot indicator with nothing else happening. Nothing
about the pipeline requires that silence — the answer is generated token by
token and simply is not shown until complete.

**This is the single biggest perceived-quality gap.** Streaming the response
would make the same 15 seconds feel responsive instead of broken. Ollama and the
Claude API both stream; `/chat` returns one JSON blob.

The obstacle is real, though: verification runs *after* generation, so streaming
an unverified draft risks showing a figure that the grounding checks then
reject. Two workable shapes:

- Stream the draft into a "checking…" state, then either confirm it in place or
  visibly replace it when grounding fails. Honest, and shows the verification
  working, which is the whole pitch.
- Stream only the retrieval and verification *stages* as status text ("found 27
  stations… checking 3 figures…") and keep the answer atomic. Less impressive,
  much simpler.

### 2. The prose is stilted, and leaks internals

Correct, cited, robotic. Every answer follows the same shape because a 7B model
is doing the writing. Worse, it cites field names as though they were sources:

> "falling at a rate of 1.205 meters per year (depletion_rate). **}**
> (Sangrur, depletion_rate)"

A stray brace and a key used as a citation. Grounding check 1 misses it because
only capitalised tokens are treated as citations — so this is cosmetic to the
checks and glaring to a reader.

Switching `LLM_PROVIDER=anthropic` would cost about $0.02 a question and fix
most of this without touching any code. **That has been decided against** — the
system is meant to hold up on a free local model, and "correct answers on a 7B"
is a stronger claim than "we used a good model".

So this needs its own fix. The field-name citations are the same class as the
`projected_year` leak, which was solved by withholding the field from the prompt
rather than by asking the model not to quote it; `slim_for_prompt()` is the
place to look. The stilted shape is harder and may simply be the cost of the
decision.

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

### 5. The interface is still plain in places

The trend chart and the ranked bars are done. The message bubble is not: prose,
a small badge, and citations as a grey `[1] [2] [3]` list. It is the last plain
surface a judge will look at.

The map is also thinner than the pitch. It shows 23 district polygons for a
system that advertises 1,607 stations and 36,879 readings; none of that density
is visible anywhere.

### 6. "Why is groundwater falling in Punjab?" still fails

Grounding rejects the draft and falls back to a data dump. It fails safely, but
it is a natural question and it does not work. Worth diagnosing rather than
avoiding.

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
- **Tests cover the deterministic core only.** 102 of them, but nothing
  exercises the SQL layer, the ingestion cleaning rules, or an end-to-end
  `/chat` call. The ingestion rules in particular are pure functions and would
  be easy to add.
- **Nobody has looked at the charts.** Every visual claim rests on geometry and
  computed styles; the browser pane never composited. Open the app and ask the
  Ludhiana projection and "worst water table" questions before trusting them.

---

## What I would do first, in order

1. **Streaming.** Biggest perceived win, and the verification-visible variant is
   genuinely novel rather than cosmetic.
2. **Fix the field-name citations** in the prose. This was filed under "switch
   to Claude and it goes away"; with the swap decided against it needs its own
   fix, and it is the same class as the `projected_year` leak already solved by
   withholding the field from the prompt.
3. **Style the message bubble and citations.** The last plain surface.
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
