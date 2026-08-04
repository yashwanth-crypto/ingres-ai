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


def handle_chat(db: Session, message: str, history: list[dict] | None = None) -> dict:
    """Run the pipeline. Always returns a usable response, never raises."""
    try:
        intent = query_understanding_agent(message, history)
    except LLMUnavailable as exc:
        return _error(str(exc))

    if intent.intent == "out_of_scope":
        return {
            "answer": OUT_OF_SCOPE,
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
        "citations": [c.model_dump() for c in draft.citations],
        "chart_data": _chart(db, intent, raw_data) if draft.needs_chart else None,
        "map_data": _map(db, intent, raw_data) if draft.needs_map else None,
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
    if len(districts) < 2:
        return None
    points = gw.district_points(db, districts)
    return {"points": points} if points else None


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
