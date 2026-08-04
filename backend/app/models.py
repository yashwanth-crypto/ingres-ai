"""SQLAlchemy ORM models mirroring app/scripts/schema.sql."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("station_name", "district", name="uq_stations_name_district"),
    )

    station_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_name: Mapped[str] = mapped_column(Text, nullable=False)
    district: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="Punjab")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    readings: Mapped[list["Reading"]] = relationship(back_populates="station")


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        UniqueConstraint("station_id", "reading_date", name="uq_readings_station_date"),
    )

    reading_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.station_id"))
    reading_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    # Depth to water, metres below ground level. Larger = deeper = worse.
    water_level_m: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(Text, default="CGWB")

    station: Mapped[Station] = relationship(back_populates="readings")


class RiskCategory(Base):
    __tablename__ = "risk_categories"

    district: Mapped[str] = mapped_column(Text, primary_key=True)
    # Derived from the block categories below: the category held by most of the
    # district's blocks, ties broken toward the worse category. CGWB itself
    # publishes no district-level category.
    category: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_year: Mapped[int | None] = mapped_column(Integer)

    blocks_assessed: Mapped[int | None] = mapped_column(Integer)
    blocks_safe: Mapped[int | None] = mapped_column(Integer)
    blocks_semi_critical: Mapped[int | None] = mapped_column(Integer)
    blocks_critical: Mapped[int | None] = mapped_column(Integer)
    blocks_over_exploited: Mapped[int | None] = mapped_column(Integer)


class AssessmentBlock(Base):
    __tablename__ = "assessment_blocks"
    __table_args__ = (
        UniqueConstraint("district", "block", name="uq_blocks_district_block"),
    )

    block_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    district: Mapped[str] = mapped_column(Text, nullable=False)
    block: Mapped[str] = mapped_column(Text, nullable=False)
    # Stage of ground water extraction, percent. >100 means extraction exceeds
    # annual recharge.
    stage_pct: Mapped[float | None] = mapped_column(Float)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_year: Mapped[int | None] = mapped_column(Integer)
