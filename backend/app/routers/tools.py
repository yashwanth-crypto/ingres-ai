"""Tool endpoints (spec Section 6).

These are real REST endpoints so they can be tested standalone with curl, but
the Retrieval Agent calls the service layer directly rather than looping back
through HTTP.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import Comparison, CurrentLevel, DepletionRate, RiskCategory
from app.services import groundwater_service as gw

router = APIRouter(prefix="/tools", tags=["tools"])


def _handle(exc: Exception) -> HTTPException:
    """Turn a service error into an HTTP error that says what to do next."""
    if isinstance(exc, gw.DistrictNotFound):
        return HTTPException(
            status_code=404,
            detail={
                "error": "unknown_district",
                "message": str(exc),
                "valid_districts": list(gw.CANONICAL_DISTRICTS),
            },
        )
    if isinstance(exc, gw.NoDataForDistrict):
        return HTTPException(
            status_code=404,
            detail={"error": "no_data", "message": str(exc)},
        )
    raise exc


@router.get("/current_level", response_model=CurrentLevel)
def current_level(district: str = Query(...), db: Session = Depends(get_db)):
    try:
        return gw.current_level(db, district)
    except (gw.DistrictNotFound, gw.NoDataForDistrict) as exc:
        raise _handle(exc) from exc


@router.get("/depletion_rate", response_model=DepletionRate)
def depletion_rate(
    district: str = Query(...),
    years: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
):
    try:
        return gw.depletion_rate(db, district, years)
    except (gw.DistrictNotFound, gw.NoDataForDistrict) as exc:
        raise _handle(exc) from exc


@router.get("/risk_category", response_model=RiskCategory)
def risk_category(district: str = Query(...), db: Session = Depends(get_db)):
    try:
        return gw.risk_category(db, district)
    except (gw.DistrictNotFound, gw.NoDataForDistrict) as exc:
        raise _handle(exc) from exc


@router.get("/blocks")
def blocks(district: str = Query(...), db: Session = Depends(get_db)):
    """Assessment units behind a district's category - the citable evidence."""
    try:
        return {"district": district, "blocks": gw.blocks_for_district(db, district)}
    except gw.DistrictNotFound as exc:
        raise _handle(exc) from exc


@router.get("/compare", response_model=Comparison)
def compare(
    districts: str = Query(..., description="Comma-separated district names"),
    db: Session = Depends(get_db),
):
    names = [d.strip() for d in districts.split(",") if d.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="No districts given.")
    if len(names) > 10:
        raise HTTPException(status_code=400, detail="At most 10 districts.")
    try:
        return gw.compare(db, names)
    except gw.DistrictNotFound as exc:
        raise _handle(exc) from exc
