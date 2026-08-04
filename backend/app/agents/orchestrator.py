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
from app.services.llm_client import LLMUnavailable

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

    try:
        draft = response_agent(raw_data, message)
        hard, soft = _check(draft.answer, raw_data)

        if hard or soft:
            log.warning("Rejected draft - hard=%s soft=%s", hard, soft)
            draft = response_agent(raw_data, message, issues=hard + soft)
            hard, soft = _check(draft.answer, raw_data)

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

    return out


def _wants_chart(intent: QueryIntent) -> bool:
    """A single district's history over time is worth plotting."""
    return intent.intent in ("current_status", "depletion_trend", "years_to_critical")


def _wants_map(intent: QueryIntent, raw_data: dict) -> bool:
    """Several districts at once are worth putting on a map."""
    return (
        bool(raw_data.get("category_listing"))
        or bool(raw_data.get("ranking"))
        or len(intent.districts) >= 2
    )


def _chart(db: Session, intent: QueryIntent, raw_data: dict) -> dict | None:
    district = intent.district or (intent.districts[0] if intent.districts else None)
    if not district:
        return None
    series = gw.district_series(db, district)
    if len(series) < 2:
        return None
    return {
        "type": "line",
        "district": district,
        "y_label": "Depth to water (m below ground)",
        "note": "Larger values mean a deeper water table.",
        "series": series,
    }


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
    if raw_data.get("unavailable"):
        lines.append(raw_data["unavailable"])
    lines += ["", f"Verification flagged: {'; '.join(issues)}"]
    return "\n".join(lines)


def _error(detail: str) -> dict:
    return {
        "answer": (
            "The assistant is not fully configured, so I cannot answer in "
            f"natural language right now. ({detail}) The underlying data is "
            "still available through the /tools endpoints."
        ),
        "citations": [],
        "chart_data": None,
        "map_data": None,
        "intent": "error",
        "verified": False,
    }
