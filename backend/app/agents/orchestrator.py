"""Agent 7.6 - Orchestrator.

Wires the five agents together and decides what the user finally sees.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agents.calculation import calculation_agent
from app.agents.grounding import grounding_issues
from app.agents.query_understanding import QueryIntent, query_understanding_agent
from app.agents.response import response_agent
from app.agents.retrieval import retrieval_agent
from app.agents.verification import verification_agent
from app.scripts.districts import CANONICAL_DISTRICTS
from app.services import groundwater_service as gw
from app.services.llm_client import LLMGarbledResponse, LLMUnavailable

log = logging.getLogger(__name__)

OUT_OF_SCOPE = (
    "I can only answer questions about groundwater in Punjab, using CGWB "
    "monitoring data for its 23 districts. I do not have data for other states "
    "or other topics.\n\nTry asking about a Punjab district - for example "
    '"What is the groundwater status in Bathinda?"'
)

# Answering a drinking-safety question with an extraction category would be
# actively misleading, so it gets its own refusal that explains the difference.
NO_QUALITY_DATA = (
    "I cannot answer that. This dataset covers how much groundwater there is - "
    "water levels and CGWB's extraction categories - and contains no water "
    "quality measurements at all.\n\n"
    "In particular, \"over-exploited\" describes extraction outstripping "
    "recharge. It says nothing about whether water is safe to drink. Treating "
    "the two as the same would be misleading, so I will not.\n\n"
    "For contamination data, see CGWB's Ground Water Year Book, which reports "
    "uranium, nitrate and salinity separately."
)

OUT_OF_SCOPE_MESSAGES = {"no_quality_data": NO_QUALITY_DATA}


def handle_chat(db: Session, message: str, history: list[dict] | None = None) -> dict:
    """Run the pipeline. Always returns a usable response, never raises."""
    try:
        intent = query_understanding_agent(message, history)
    except LLMUnavailable as exc:
        return _error(str(exc))

    if intent.intent == "out_of_scope":
        return {
            "answer": OUT_OF_SCOPE_MESSAGES.get(
                intent.out_of_scope_reason or "", OUT_OF_SCOPE
            ),
            "citations": [],
            "chart_data": None,
            "map_data": None,
            "intent": intent.intent,
        }

    try:
        raw_data = retrieval_agent(db, intent)
    except gw.DistrictNotFound:
        return {
            "answer": OUT_OF_SCOPE,
            "citations": [],
            "chart_data": None,
            "map_data": None,
            "intent": "out_of_scope",
        }

    if intent.intent == "years_to_critical":
        raw_data = calculation_agent(raw_data)

    _name_the_sources(raw_data)

    try:
        try:
            draft = response_agent(raw_data, message)
        except LLMGarbledResponse as exc:
            # The model answered, just never in a form we could parse - it fell
            # into a repetition loop and ran to its token cap mid-string. The
            # retrieved data is untouched by that, and showing it beats telling
            # someone their question failed when we hold the answer to it.
            log.error("No usable draft (%s) - showing the retrieved data", exc)
            return {
                "answer": _data_dump(raw_data, [f"the model produced no usable answer ({exc})"]),
                "citations": _citations(raw_data),
                "chart_data": _chart(db, intent, raw_data) if _wants_chart(intent) else None,
                "map_data": _map(db, intent, raw_data) if _wants_map(intent, raw_data) else None,
                "intent": intent.intent,
                "verified": False,
                "source": "report" if raw_data.get("passages") else "database",
            }

        hard, soft = _check(draft.answer, raw_data)

        if hard or soft:
            log.warning("Rejected draft - hard=%s soft=%s", hard, soft)
            first = (draft, hard, soft)
            try:
                draft = response_agent(raw_data, message, issues=hard + soft)
                hard, soft = _check(draft.answer, raw_data)
            except LLMUnavailable as exc:
                # The rewrite is a second chance, not a dependency. Asked to fix
                # three objections at once, a 7B model rambled past its token
                # budget and returned truncated JSON - and because both calls
                # sat under one `try`, that error replaced an answer we already
                # had with a bare failure message. Fall back to the first draft
                # and let the checks below decide what it is worth.
                log.warning("Rewrite failed (%s) - falling back to first draft", exc)
                draft, hard, soft = first

            if hard and not first[1]:
                # The first draft was properly grounded and only the advisory
                # reviewer objected. Told to address its notes, the rewrite
                # introduced a real grounding failure the original never had -
                # asked to mention the pumping limit, it credited the 30 m
                # figure to CGWB. Falling through would replace a correct
                # answer with a data dump on the strength of a nitpick, which
                # is the veto this reviewer is explicitly not meant to have.
                log.info("Rewrite introduced %s - keeping first draft", hard)
                draft, hard, soft = first

            if hard:
                # A fabricated citation, figure or district survived the retry.
                # Show the data rather than an answer we cannot stand behind.
                log.error("Grounding still failed after retry: %s", hard)
                return {
                    "answer": _data_dump(raw_data, hard),
                    "citations": [],
                    "chart_data": _chart(db, intent, raw_data),
                    "map_data": _map(db, intent, raw_data),
                    "intent": intent.intent,
                    "verified": False,
                }
            if soft:
                # Grounding is clean; only the LLM reviewer still objects, and
                # it has already been observed objecting to figures that are
                # present in the data. Ship the answer, flag the caveat.
                log.info("Accepting draft over soft objections: %s", soft)
    except LLMUnavailable as exc:
        return _error(str(exc))

    return {
        "answer": draft.answer,
        # Built from the retrieved data, not from the model. Small models
        # reliably write citations inline in the prose but leave the structured
        # field empty, and the data already knows exactly what backed the answer.
        "citations": _citations(raw_data),
        # Decided from the intent, not from a model-set boolean. The model was
        # observed leaving both flags false on questions that plainly wanted a
        # visual, and this is a rule, not a judgement call.
        "chart_data": _chart(db, intent, raw_data) if _wants_chart(intent) else None,
        "map_data": _map(db, intent, raw_data) if _wants_map(intent, raw_data) else None,
        "intent": intent.intent,
        "verified": True,
        "review_notes": soft,
        # Which of the two sources answered, so the interface can show it.
        "source": "report" if raw_data.get("passages") else "database",
    }


def _check(draft: str, raw_data: dict) -> tuple[list[str], list[str]]:
    """Return (hard, soft) issues.

    `hard` comes from deterministic checks over the retrieved data and cannot
    hallucinate - an invented citation, an unsupported figure, the wrong
    district. These block an answer.

    `soft` comes from the LLM reviewer, which catches nuance the rules cannot
    (a dropped caveat, a projection stated as fact) but also produces false
    positives on smaller models. These trigger one rewrite, not a block.
    """
    hard = grounding_issues(draft, raw_data)
    verdict = verification_agent(draft, raw_data)
    soft = [] if verdict.approved else list(verdict.issues)
    return hard, soft


def _name_the_sources(raw_data: dict) -> None:
    """Give every derived figure a source the answer can actually cite.

    The prompt requires a source in parentheses after every number. A single
    reading has one - a station and a date. A depletion rate does not: it is the
    median of dozens of station trends. Given nothing citable, the model reached
    for the nearest label to hand and wrote "falling at 1.205 meters per year
    (depletion_rate)", quoting the field name as though it were a source.

    So the figure is handed the sentence it should quote. Written into the data
    rather than the prompt on purpose: the grounding check recognises a citation
    by finding it in the retrieved data, so a string the model may quote has to
    live there.
    """
    rate = raw_data.get("depletion_rate")
    if rate and not rate.get("source"):
        rate["source"] = (
            f"Median trend across {len(rate['stations_used'])} stations, "
            f"{rate['district']}, last {rate['years_analyzed']} years"
        )

    projection = raw_data.get("projection")
    if projection and projection.get("stations_used") and not projection.get("source"):
        district = raw_data.get("district") or ""
        projection["source"] = (
            f"Projected from {projection['stations_used']} station trends"
            + (f", {district}" if district else "")
        )


def _citations(raw_data: dict) -> list[dict]:
    """Every source that actually fed the answer, straight from the data."""
    out: list[dict] = []

    level = raw_data.get("current_level")
    if level:
        out.append(
            {
                "station": f"{level['station']} ({level['district']})",
                "date": str(level["date"]),
            }
        )

    rate = raw_data.get("depletion_rate")
    if rate:
        out.append(
            {
                "station": (
                    f"Median trend across {len(rate['stations_used'])} stations, "
                    f"{rate['district']}"
                ),
                "date": f"last {rate['years_analyzed']} years",
            }
        )

    risk = raw_data.get("risk_category")
    if risk:
        out.append(
            {
                "station": (
                    f"CGWB assessment, {risk['district']} "
                    f"({risk['blocks_over_exploited']}/{risk['blocks_assessed']} "
                    f"blocks over-exploited)"
                ),
                "date": str(risk["assessment_year"]),
            }
        )

    listing = raw_data.get("category_listing")
    if listing:
        out.append(
            {
                "station": (
                    f"CGWB assessment, {len(listing)} districts categorised "
                    f"{raw_data.get('category', '')}".strip()
                ),
                "date": str(listing[0].get("assessment_year", "")),
            }
        )

    for passage in raw_data.get("passages", []) or []:
        # The citation already carries the page. A relevance score here read
        # like debug output next to a real source line.
        out.append({"station": passage["citation"], "date": ""})

    ranking = raw_data.get("ranking")
    if ranking:
        out.append(
            {
                "station": (
                    f"{raw_data.get('districts_ranked')} districts ranked by "
                    f"{'depletion rate' if raw_data.get('ranked_by') == 'depletion' else 'mean depth'}"
                ),
                "date": "CGWB, latest readings",
            }
        )

    comparison = raw_data.get("comparison")
    if comparison:
        for row in comparison.get("districts", []):
            if row.get("date"):
                out.append(
                    {"station": row["district"], "date": str(row["date"])}
                )

    # Two chunks retrieved from one page cite that page twice. Listing it twice
    # says nothing except that the retrieval happened to split it there.
    seen, unique = set(), []
    for citation in out:
        key = (citation["station"], citation["date"])
        if key not in seen:
            seen.add(key)
            unique.append(citation)
    return unique


def _wants_chart(intent: QueryIntent) -> bool:
    """One district over time, or several against each other.

    Ranking and comparison were absent here, so "which district has the worst
    water table?" returned eight districts with real figures and drew none of
    them - the map showed *where* they were and nothing showed *how bad*, which
    is the entire question. A category listing is still excluded: every bar
    would be the same length and the same colour, and the map already says it.
    """
    return intent.intent in (
        "current_status",
        "depletion_trend",
        "years_to_critical",
        "ranking",
        "comparison",
    )


def _wants_map(intent: QueryIntent, raw_data: dict) -> bool:
    """Several districts at once are worth putting on a map."""
    return (
        bool(raw_data.get("category_listing"))
        or bool(raw_data.get("ranking"))
        or len(intent.districts) >= 2
    )


def _chart(db: Session, intent: QueryIntent, raw_data: dict) -> dict | None:
    """Bars when the answer is about several districts, a line when it is one."""
    return _bars(db, raw_data) or _line(db, intent, raw_data)


def _bars(db: Session, raw_data: dict) -> dict | None:
    """Districts side by side, worst first.

    Ranked and compared answers are about relative magnitude, and a list of
    numbers in prose makes the reader do the comparing. Bars do it for them.
    """
    ranking = raw_data.get("ranking")
    comparison = (raw_data.get("comparison") or {}).get("districts")

    if ranking:
        rows = [
            {"label": r["district"], "value": r["value"], "stations": r.get("stations")}
            for r in ranking
        ]
        unit = ranking[0].get("unit", "")
        # The winner is named so the chart agrees with the sentence above it,
        # which states it outright for reasons documented in the Retrieval agent.
        answer = (raw_data.get("answer_is") or {}).get("district")
        by = raw_data.get("ranked_by")
        title = (
            "Rate of fall by district"
            if by == "depletion"
            else "Depth to water by district"
        )
        counted = raw_data.get("districts_ranked")
        note = f"Worst first. {len(rows)} of {counted} districts shown." if counted else ""
    elif comparison:
        rows = [
            {"label": r["district"], "value": r["value_m"], "category": r["category"]}
            for r in comparison
        ]
        unit = "m below ground"
        answer = None
        title = "Depth to water"
        note = "Latest reading in each district."
    else:
        return None

    # A district CGWB assessed but the network does not reach has no bar to
    # draw. It is named rather than silently missing - Malerkotla is the case.
    unavailable = [r["label"] for r in rows if r["value"] is None]
    bars = [r for r in rows if r["value"] is not None]
    if not bars:
        return None

    categories = gw.categories_for(db, [b["label"] for b in bars])
    for bar in bars:
        bar.setdefault("category", categories.get(bar["label"]))

    return {
        "type": "bars",
        "title": title,
        "unit": unit,
        "note": note,
        "bars": bars,
        "highlight": answer,
        "unavailable": unavailable,
    }


def _line(db: Session, intent: QueryIntent, raw_data: dict) -> dict | None:
    district = intent.district or (intent.districts[0] if intent.districts else None)
    if not district:
        return None
    series = gw.district_series(db, district)
    if len(series) < 2:
        return None
    chart = {
        "type": "line",
        "district": district,
        "y_label": "Depth to water (m below ground)",
        "note": "Larger values mean a deeper water table.",
        "series": series,
    }
    forward = _projection_line(series, raw_data.get("projection"))
    if forward:
        chart["projection"] = forward
    return chart


def _projection_line(series: list[dict], projection: dict | None) -> dict | None:
    """The forward line for a years-to-depth answer, as its two endpoints.

    The projection is a straight line by construction, so two points describe it
    exactly - there is nothing to gain from interpolating more.

    Anchored on the district mean the Calculation Agent actually used, which is
    the mean across stations on the latest *reading date*. The history line
    plots an annual mean, so the two rarely coincide exactly. The anchor is
    drawn where the calculation put it rather than snapped onto the history
    line: the projection must show the number the answer quotes.
    """
    if not projection:
        return None

    years = projection.get("years_to_reference_depth")
    depth = projection.get("current_depth_m")
    reference = projection.get("reference_depth_m")
    if reference is None:
        return None

    line = {
        "series": [],
        "reference_depth_m": reference,
        "rate_m_per_year": projection.get("current_rate_m_per_year"),
        "years": years,
        "reaches_year": None,
        # Restated on the chart because a dashed line crossing a labelled
        # threshold reads as an official forecast unless it says otherwise.
        "caveat": projection.get("threshold_caveat", ""),
    }

    # `years` is None when the table is not falling, and 0.0 when it is already
    # at or past the reference depth. Neither describes a line going forward, so
    # only the reference depth is drawn - the caption carries the reason.
    if years:
        start = series[-1]["year"]
        line["series"] = [
            {"year": start, "projected_depth_m": round(depth, 2)},
            {"year": round(start + years, 1), "projected_depth_m": reference},
        ]
        line["reaches_year"] = round(start + years, 1)

    return line


def _map(db: Session, intent: QueryIntent, raw_data: dict) -> dict | None:
    districts = list(intent.districts)
    if intent.district and intent.district not in districts:
        districts.append(intent.district)
    if raw_data.get("category_listing"):
        districts = [r["district"] for r in raw_data["category_listing"]]
    elif raw_data.get("ranking"):
        districts = [r["district"] for r in raw_data["ranking"]]
    if len(districts) < 2:
        return None
    points = gw.district_points(db, districts)
    if not points:
        return None
    # A district can be categorised but unmappable - Malerkotla has a CGWB
    # category and no monitoring stations. Report it instead of quietly
    # showing 19 pins for 20 districts.
    plotted = {p["district"] for p in points}
    return {
        "points": points,
        "not_plotted": [d for d in districts if d not in plotted],
    }


def _data_dump(raw_data: dict, issues: list[str]) -> str:
    """Last-resort answer: the retrieved figures, plainly, with the reason."""
    lines = [
        "I could not produce an answer I was able to verify against the source "
        "data, so here is the data itself rather than a claim I cannot stand "
        "behind.",
        "",
    ]
    level = raw_data.get("current_level")
    if level:
        lines.append(
            f"Latest reading: {level['value_m']} m below ground at "
            f"{level['station']} on {level['date']} "
            f"(district mean {level['district_mean_m']} m across "
            f"{level['stations_reporting']} stations)."
        )
    rate = raw_data.get("depletion_rate")
    if rate:
        lines.append(
            f"Depletion rate: {rate['rate_m_per_year']} m/year "
            f"({rate['confidence_note']})"
        )
    risk = raw_data.get("risk_category")
    if risk:
        lines.append(
            f"CGWB category: {risk['category']} ({risk['assessment_year']}), "
            f"{risk['blocks_over_exploited']} of {risk['blocks_assessed']} blocks "
            f"over-exploited."
        )
    # A report-backed answer has none of the fields above, so without this the
    # dump was a preamble and nothing else. The passages are the data here, and
    # quoting them verbatim is exactly what "here is the data itself" means.
    for passage in raw_data.get("passages") or []:
        text = " ".join(passage["text"].split())
        lines.append(f"From {passage['citation']}:")
        lines.append(f"  “{text[:400]}…”" if len(text) > 400 else f"  “{text}”")
        lines.append("")

    if raw_data.get("unavailable"):
        lines.append(raw_data["unavailable"])
    lines += ["", f"Verification flagged: {'; '.join(issues)}"]
    return "\n".join(lines)


def _error(detail: str) -> dict:
    return {
        "answer": (
            "I could not produce an answer for that question right now. "
            f"({detail})\n\nThe data itself is unaffected - try rephrasing, or "
            "ask a more specific question."
        ),
        "citations": [],
        "chart_data": None,
        "map_data": None,
        "intent": "error",
        "verified": False,
    }
