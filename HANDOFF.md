# Handoff — state, and what to fix next

Read [ARCHITECTURE.md](ARCHITECTURE.md) first for how the system works. This
file is only about what is *weak* and what to do about it.

## Where it stands

Phases 1–6 of the spec are done. Data loaded, six tool endpoints, five agents,
hybrid retrieval, React frontend. 10 of 11 test questions answer cleanly.

Branch `feat/answer-visuals`, six commits ahead of `main`, **no remote**. The
work on it: the projection is drawn, ranked and compared answers get charts,
two verification holes are closed, and there is a test suite.

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

Switching `LLM_PROVIDER=anthropic` costs about $0.02 a question and fixes most
of this without touching any code. Worth doing for the demo regardless of what
else changes.

### 3. Follow-up questions are untested

`history` is passed to the Query Understanding agent and truncated to four
turns, but nobody has tested whether *"and what about Moga?"* or *"is that
getting worse?"* actually resolves. It may well not. A judge will try it —
conversation is the entire premise of a chat interface.

### 4. The RAG corpus is one document

254 chunks from one 106-page report, and each chunk carries only `{page, text}`
— no section title, no district, no scope marker. That thin metadata is why a
Punjab-wide salinity figure was once attributed to Bathinda: the model received
a passage with nothing saying what it was scoped to.

"Too small" points at the wrong lever. In order:

1. **Section-aware chunking and real metadata.** Attacks the known
   misattribution directly, and is the cheapest of the three.
2. **A reranking pass.** At k=3 against a flat 0.55 floor, first-stage
   precision is doing all the work.
3. **Then** more documents. Expanding the corpus before 1 and 2 scales the
   failure mode rather than the coverage.

Also worth knowing: the chunker is a fixed 900-character window per page, so a
table spanning a page break is sliced mid-row.

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
- **Document answers can misattribute** — see problem 4.
- **Tests cover the deterministic core only.** Nothing exercises the SQL layer,
  the ingestion cleaning rules, or an end-to-end `/chat` call. The ingestion
  rules in particular are pure functions and would be easy to add.

---

## What I would do first, in order

1. **Streaming.** Biggest perceived win, and the verification-visible variant is
   genuinely novel rather than cosmetic.
2. **Switch to Claude for the demo.** One line, ten cents, and it takes most of
   problem 2 with it.
3. **Test the follow-up path**, then fix it. Cheap, and table stakes for a chat
   product.
4. **Style the message bubble and citations.** The last plain surface.
5. **RAG metadata and reranking**, before any corpus expansion.
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

**Being in the data is not the same as measuring the right thing.** The two
checks added since — the projected year, and units — both exist because a wrong
figure passed a check that only asked whether the number appeared *somewhere*.
In a projection answer every number does. `20.1` is real; it is the number of
years, and the sentence called it a depth.

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
