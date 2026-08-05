# Handoff — state, and what to fix next

Read [ARCHITECTURE.md](ARCHITECTURE.md) first for how the system works. This
file is only about what is *weak* and what to do about it.

## Where it stands

Phases 1–6 of the spec are done and committed (11 commits, branch
`feat/full-stack-app`, **no remote**). Data loaded, six tool endpoints, five
agents, hybrid retrieval, React frontend. 10 of 11 test questions answer
cleanly.

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

### 2. The prose is stilted

> "The groundwater level in Bathinda is 15.91 m below ground (Kot Shamir,
> 2024-01-01), and the district is categorized as over-exploited (CGWB, 2024)."

Correct, cited, and robotic. Every answer follows the same shape because a 7B
model is doing the writing.

Switching `LLM_PROVIDER=anthropic` costs about $0.02 a question and fixes most
of this without touching any code. Worth doing for the demo regardless of what
else changes.

### 3. Follow-up questions are untested

`history` is passed to the Query Understanding agent and truncated to four
turns, but nobody has tested whether *"and what about Moga?"* or *"is that
getting worse?"* actually resolves. It may well not. A judge will try it —
conversation is the entire premise of a chat interface.

### 4. There is no test suite

Every check in this project was an ad-hoc script run once and thrown away.
Nothing in the repo runs today to prove the pipeline still works. The
grounding checks in particular deserve real tests — they are the credibility
mechanism, and a refactor could silently weaken them.

Start with `pytest`: the grounding cases, the district canonicalisation, the
ranking order, and the ingestion cleaning rules. All of those are pure functions
with no model or network involved.

### 5. "Why is groundwater falling in Punjab?" still fails

Grounding rejects the draft and falls back to a data dump. It fails safely, but
it is a natural question and it does not work. Worth diagnosing rather than
avoiding.

### 6. Not deployed

Spec §10 wants Railway and Vercel. Skipped deliberately: this network blocks
every database port, so Railway was unusable for development. A local demo is
lower-risk, but a live URL is worth more to judges, and the deployed backend
would reach Postgres over Railway's internal network without touching the
firewall.

---

## Smaller things

- **Map tiles need internet.** Everything else runs offline. Consider bundling a
  static Punjab outline as a fallback.
- **Bundle is 696 KB** (203 KB gzipped), mostly Recharts and Leaflet. Only
  matters if deployed.
- **A persona injection wrapped around a real question** is refused entirely,
  losing the legitimate question. Fails safe, but is over-strict.
- **Document answers can misattribute.** A Punjab-wide salinity figure was once
  attributed to Bathinda specifically. Inherent to RAG; the grounding checks
  cannot catch it.

---

## What I would do first, in order

1. **Streaming.** Biggest perceived win, and the verification-visible variant is
   genuinely novel rather than cosmetic.
2. **Test the follow-up path**, then fix it. Cheap, and it is table stakes for a
   chat product.
3. **A real `pytest` suite** over the deterministic pieces.
4. **Switch to Claude for the demo.** One line, ten cents, better prose.
5. Deploy, if time remains.

---

## Two lessons from this session worth keeping

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
