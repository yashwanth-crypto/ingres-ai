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
            else:
                data["risk_category"] = gw.risk_category(db, intent.district)
                data["blocks"] = gw.blocks_for_district(db, intent.district)

        elif intent.intent == "comparison":
            data["comparison"] = gw.compare(db, intent.districts)
            data["districts"] = intent.districts

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
