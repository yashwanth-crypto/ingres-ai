"""Agent 7.2 - Retrieval.

Deterministic Python, not an LLM call: maps a structured intent to the right
service calls. Calls the service layer directly rather than looping back
through HTTP.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.query_understanding import QueryIntent
from app.models import RiskCategory
from app.services import groundwater_service as gw
from app.services import rag_service


def retrieval_agent(db: Session, intent: QueryIntent) -> dict:
    """Return the raw data an answer to `intent` must be grounded in.

    Every branch either returns real rows or an explicit `unavailable` marker.
    Nothing here invents a value for a district we have no data for.
    """
    data: dict = {"intent": intent.intent, "district": intent.district}

    try:
        if intent.intent == "current_status":
            data["current_level"] = gw.current_level(db, intent.district)
            data["risk_category"] = _safe_risk(db, intent.district)

        elif intent.intent == "depletion_trend":
            data["depletion_rate"] = gw.depletion_rate(
                db, intent.district, intent.years or 10
            )
            data["current_level"] = gw.current_level(db, intent.district)

        elif intent.intent == "risk_category":
            if intent.category:
                data["category_listing"] = _districts_in_category(db, intent.category)
                data["category"] = intent.category
                # Without the denominator the answer says "all districts listed
                # are over-exploited", which reads as if all 23 are.
                data["category_totals"] = _category_totals(db)
            else:
                data["risk_category"] = gw.risk_category(db, intent.district)
                data["blocks"] = gw.blocks_for_district(db, intent.district)

        elif intent.intent == "comparison":
            data["comparison"] = gw.compare(db, intent.districts)
            data["districts"] = intent.districts

        elif intent.intent == "document_question":
            query = intent.question or ""
            if intent.district:
                query = f"{query} {intent.district}"
            # Three passages, not four: a 7B model given four long extracts
            # rambled past its output budget and had to be retried, which
            # doubled latency. Three is enough to answer and stay fast.
            #
            # The district is also passed separately, not only glued onto the
            # query. Embedding similarity treats it as one more word; the
            # reranker uses it to demote a passage that is scoped to some other
            # district, which is how a figure ends up attributed to the wrong
            # place.
            passages = rag_service.search(
                query.strip(), k=3, district=intent.district
            )
            data["passages"] = passages
            if not passages:
                data["unavailable"] = (
                    "The CGWB report has no passage relevant to this question."
                )
            # The extraction category is deliberately NOT retrieved here. Asked
            # "is the water safe to drink?", the model led with "Bathinda is
            # over-exploited" even though the prompt forbids it - so the
            # category is simply withheld from questions it cannot answer.
            # Withholding beats instructing.

        elif intent.intent == "ranking":
            ranked = gw.rank_districts(db, intent.rank_by, intent.rank_order)
            # The winner is stated outright. Handed a sorted list, the model
            # picked the wrong row - "Hoshiarpur, 8.94 m" from a list whose
            # top entry was Barnala at 43.22 m. Both values were real, so the
            # grounding checks could not catch it.
            data["answer_is"] = ranked[0] if ranked else None
            data["ranking"] = ranked[:8]
            data["ranked_by"] = intent.rank_by
            data["ranked_order"] = intent.rank_order
            data["districts_ranked"] = len(ranked)

        elif intent.intent == "years_to_critical":
            # Feeds the Calculation Agent (7.3).
            data["depletion_rate"] = gw.depletion_rate(
                db, intent.district, intent.years or 15
            )
            data["current_level"] = gw.current_level(db, intent.district)
            data["risk_category"] = _safe_risk(db, intent.district)

    except gw.NoDataForDistrict as exc:
        # A real Punjab district with no readings - Malerkotla is the live case.
        # Its risk category still exists, so return that rather than nothing.
        data["unavailable"] = str(exc)
        data["risk_category"] = _safe_risk(db, intent.district)

    return data


def _safe_risk(db: Session, district: str | None) -> dict | None:
    if not district:
        return None
    try:
        return gw.risk_category(db, district)
    except (gw.DistrictNotFound, gw.NoDataForDistrict):
        return None


def _category_totals(db: Session) -> dict:
    """How many districts sit in each category, and how many exist overall."""
    rows = db.query(RiskCategory).all()
    totals: dict[str, int] = {}
    for row in rows:
        totals[row.category] = totals.get(row.category, 0) + 1
    return {"districts_assessed": len(rows), "by_category": totals}


def _districts_in_category(db: Session, category: str) -> list[dict]:
    rows = (
        db.query(RiskCategory)
        .filter(RiskCategory.category == category)
        .order_by(RiskCategory.blocks_over_exploited.desc())
        .all()
    )
    return [
        {
            "district": r.district,
            "category": r.category,
            "assessment_year": r.assessment_year,
            "blocks_assessed": r.blocks_assessed,
            "blocks_over_exploited": r.blocks_over_exploited,
        }
        for r in rows
    ]
