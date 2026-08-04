"""Pydantic response models for the tool endpoints (spec Section 6)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

Category = str  # 'safe' | 'semi-critical' | 'critical' | 'over-exploited'


class CurrentLevel(BaseModel):
    district: str
    value_m: float = Field(description="Depth to water, metres below ground")
    station: str
    date: dt.date
    source: str = "CGWB"

    # Context beyond the spec's fields: a single well is a weak proxy for a
    # whole district, so callers can see how much company it had.
    stations_reporting: int = Field(
        description="Stations with a reading on this date in this district"
    )
    district_mean_m: float = Field(
        description="Mean depth across those stations on that date"
    )


class DepletionRate(BaseModel):
    district: str
    rate_m_per_year: float = Field(
        description="Positive means the water table is falling (getting deeper)"
    )
    stations_used: list[str]
    years_analyzed: int
    confidence_note: str


class RiskCategory(BaseModel):
    district: str
    category: Category
    assessment_year: int | None

    # Evidence for the derived district category. CGWB categorises blocks, not
    # districts, so the distribution matters.
    blocks_assessed: int | None = None
    blocks_safe: int | None = None
    blocks_semi_critical: int | None = None
    blocks_critical: int | None = None
    blocks_over_exploited: int | None = None


class ComparisonRow(BaseModel):
    district: str
    value_m: float | None
    date: dt.date | None
    category: Category | None


class Comparison(BaseModel):
    districts: list[ComparisonRow]


class Health(BaseModel):
    status: str
    db_connected: bool
    llm_reachable: bool
    llm_backend: str = Field(description="Active provider and model")
