"""Database queries behind the tool endpoints.

Deliberately free of FastAPI imports so the agents in Phase 3 can call these
directly rather than going back out over HTTP.

`water_level_m` throughout is depth to water in metres below ground: a larger
number means a deeper water table, so a POSITIVE trend is depletion.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AssessmentBlock, Reading, RiskCategory, Station
from app.scripts.districts import CANONICAL_DISTRICTS, canonical_district

# A station needs enough history before a straight line through its readings
# means anything. Roughly a quarter of Punjab's stations fail this - they rotate
# in and out of CGWB's network - so filtering matters.
MIN_READINGS = 8
MIN_SPAN_YEARS = 3.0

# Relaxed thresholds, used only when nothing qualifies, and always disclosed.
FALLBACK_READINGS = 4
FALLBACK_SPAN_YEARS = 2.0


class DistrictNotFound(Exception):
    """Raised when a district name is not one of Punjab's 23."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"{name!r} is not a Punjab district in this dataset.")


class NoDataForDistrict(Exception):
    """District is real, but holds no water-level readings."""

    def __init__(self, district: str):
        self.district = district
        super().__init__(f"No water level readings for {district}.")


@dataclass
class StationTrend:
    station: str
    slope_m_per_year: float
    n_readings: int
    span_years: float


def resolve_district(name: str) -> str:
    """Canonicalise a district name or raise DistrictNotFound."""
    resolved = canonical_district(name)
    if resolved is None or resolved not in CANONICAL_DISTRICTS:
        raise DistrictNotFound(name)
    return resolved


def current_level(db: Session, district: str) -> dict:
    """Most recent reading in the district, with same-day district context."""
    district = resolve_district(district)

    latest = db.execute(
        select(func.max(Reading.reading_date))
        .join(Station, Station.station_id == Reading.station_id)
        .where(Station.district == district)
    ).scalar_one_or_none()

    if latest is None:
        raise NoDataForDistrict(district)

    rows = db.execute(
        select(Station.station_name, Reading.water_level_m)
        .join(Reading, Reading.station_id == Station.station_id)
        .where(Station.district == district, Reading.reading_date == latest)
        .order_by(Station.station_name)
    ).all()

    levels = [r.water_level_m for r in rows]
    # Report the station nearest the district mean rather than an arbitrary one,
    # so the cited well is representative rather than an outlier.
    mean = statistics.fmean(levels)
    station, value = min(rows, key=lambda r: abs(r.water_level_m - mean))

    return {
        "district": district,
        "value_m": round(value, 2),
        "station": station,
        "date": latest,
        "source": "CGWB",
        "stations_reporting": len(rows),
        "district_mean_m": round(mean, 2),
    }


def _station_trends(
    db: Session, district: str, years: int
) -> tuple[list[StationTrend], dt.date, bool]:
    """Fit a slope per station over the last `years` of data.

    Returns the qualifying trends, the window start, and whether the relaxed
    thresholds had to be used.
    """
    latest = db.execute(
        select(func.max(Reading.reading_date))
        .join(Station, Station.station_id == Reading.station_id)
        .where(Station.district == district)
    ).scalar_one_or_none()
    if latest is None:
        raise NoDataForDistrict(district)

    start = latest - dt.timedelta(days=int(years * 365.25))
    rows = db.execute(
        select(Station.station_name, Reading.reading_date, Reading.water_level_m)
        .join(Reading, Reading.station_id == Station.station_id)
        .where(
            Station.district == district,
            Reading.reading_date >= start,
        )
    ).all()

    by_station: dict[str, list[tuple[dt.date, float]]] = {}
    for r in rows:
        by_station.setdefault(r.station_name, []).append(
            (r.reading_date, r.water_level_m)
        )

    def fit(min_n: int, min_span: float) -> list[StationTrend]:
        out: list[StationTrend] = []
        for station, series in by_station.items():
            if len(series) < min_n:
                continue
            series.sort()
            span = (series[-1][0] - series[0][0]).days / 365.25
            if span < min_span:
                continue
            x = np.array([d.toordinal() / 365.25 for d, _ in series])
            y = np.array([v for _, v in series])
            slope = float(np.polyfit(x, y, 1)[0])
            out.append(StationTrend(station, slope, len(series), span))
        return out

    trends = fit(MIN_READINGS, MIN_SPAN_YEARS)
    relaxed = False
    if not trends:
        trends = fit(FALLBACK_READINGS, FALLBACK_SPAN_YEARS)
        relaxed = True
    return trends, start, relaxed


def depletion_rate(db: Session, district: str, years: int = 10) -> dict:
    """Median per-station depletion rate over the last `years`.

    The median across stations, rather than one line through all pooled
    readings, keeps a handful of deep or shallow wells from dominating.
    """
    district = resolve_district(district)
    trends, start, relaxed = _station_trends(db, district, years)

    if not trends:
        raise NoDataForDistrict(district)

    slopes = [t.slope_m_per_year for t in trends]
    rate = statistics.median(slopes)

    falling = sum(1 for s in slopes if s > 0)
    note = (
        f"Median of {len(trends)} station trends fitted over "
        f"{start.isoformat()} to present; {falling} of {len(trends)} stations "
        f"show a falling water table."
    )
    if relaxed:
        note += (
            f" No station met the usual bar of {MIN_READINGS}+ readings across "
            f"{MIN_SPAN_YEARS:.0f}+ years, so relaxed thresholds "
            f"({FALLBACK_READINGS}+ readings, {FALLBACK_SPAN_YEARS:.0f}+ years) "
            f"were used - treat this rate as indicative only."
        )
    elif len(trends) < 3:
        note += " Based on very few stations; treat with caution."

    return {
        "district": district,
        "rate_m_per_year": round(rate, 3),
        "stations_used": sorted(t.station for t in trends),
        "years_analyzed": years,
        "confidence_note": note,
    }


def risk_category(db: Session, district: str) -> dict:
    """CGWB assessment category for the district, with its block breakdown."""
    district = resolve_district(district)
    row = db.get(RiskCategory, district)
    if row is None:
        raise NoDataForDistrict(district)
    return {
        "district": row.district,
        "category": row.category,
        "assessment_year": row.assessment_year,
        "blocks_assessed": row.blocks_assessed,
        "blocks_safe": row.blocks_safe,
        "blocks_semi_critical": row.blocks_semi_critical,
        "blocks_critical": row.blocks_critical,
        "blocks_over_exploited": row.blocks_over_exploited,
    }


def blocks_for_district(db: Session, district: str) -> list[dict]:
    """Individual assessment units, worst first."""
    district = resolve_district(district)
    rows = db.execute(
        select(AssessmentBlock)
        .where(AssessmentBlock.district == district)
        .order_by(AssessmentBlock.stage_pct.desc())
    ).scalars()
    return [
        {
            "block": b.block,
            "stage_pct": b.stage_pct,
            "category": b.category,
            "assessment_year": b.assessment_year,
        }
        for b in rows
    ]


def rank_districts(db: Session, by: str = "depth", order: str = "highest") -> list[dict]:
    """Rank every district by latest mean depth or by depletion rate.

    Superlative questions ("which district has the deepest water table?") named
    no district, so the pipeline previously picked an arbitrary one and answered
    confidently about it. Answering them needs every district, not one.
    """
    rows: list[dict] = []
    for district in CANONICAL_DISTRICTS:
        try:
            if by == "depletion":
                rate = depletion_rate(db, district, 15)
                rows.append(
                    {
                        "district": district,
                        "value": rate["rate_m_per_year"],
                        "unit": "m/year",
                        "stations": len(rate["stations_used"]),
                    }
                )
            else:
                level = current_level(db, district)
                rows.append(
                    {
                        "district": district,
                        "value": level["district_mean_m"],
                        "unit": "m below ground",
                        "date": str(level["date"]),
                        "stations": level["stations_reporting"],
                    }
                )
        except (DistrictNotFound, NoDataForDistrict):
            continue  # Malerkotla has no readings; it simply cannot be ranked.

    rows.sort(key=lambda r: r["value"], reverse=(order == "highest"))
    return rows


def district_series(db: Session, district: str, years: int = 25) -> list[dict]:
    """Yearly mean depth for a district - the shape a trend chart needs."""
    district = resolve_district(district)
    latest = db.execute(
        select(func.max(Reading.reading_date))
        .join(Station, Station.station_id == Reading.station_id)
        .where(Station.district == district)
    ).scalar_one_or_none()
    if latest is None:
        return []

    cutoff = latest.year - years
    year = func.extract("year", Reading.reading_date).label("year")
    rows = db.execute(
        select(year, func.avg(Reading.water_level_m), func.count())
        .join(Station, Station.station_id == Reading.station_id)
        .where(Station.district == district, year >= cutoff)
        .group_by(year)
        .order_by(year)
    ).all()
    return [
        {"year": int(y), "mean_depth_m": round(float(avg), 2), "readings": n}
        for y, avg, n in rows
    ]


def district_points(db: Session, districts: list[str]) -> list[dict]:
    """One map point per district: mean station location plus its category."""
    out = []
    for raw in districts:
        name = resolve_district(raw)
        coords = db.execute(
            select(func.avg(Station.latitude), func.avg(Station.longitude))
            .where(Station.district == name, Station.latitude.isnot(None))
        ).one_or_none()
        row = db.get(RiskCategory, name)
        if coords and coords[0] is not None:
            out.append(
                {
                    "district": name,
                    "latitude": round(float(coords[0]), 4),
                    "longitude": round(float(coords[1]), 4),
                    "category": row.category if row else None,
                }
            )
    return out


def compare(db: Session, districts: list[str]) -> dict:
    """Current level and category side by side.

    A district with no readings still returns a row with nulls - saying "no data
    for Malerkotla" is a real answer, and dropping it silently is not.
    """
    out = []
    for raw in districts:
        name = resolve_district(raw)
        try:
            level = current_level(db, name)
            value, date = level["value_m"], level["date"]
        except NoDataForDistrict:
            value = date = None
        row = db.get(RiskCategory, name)
        out.append(
            {
                "district": name,
                "value_m": value,
                "date": date,
                "category": row.category if row else None,
            }
        )
    return {"districts": out}
