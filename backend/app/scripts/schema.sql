-- Schema for the INGRES groundwater assistant (spec Section 4).
-- Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS stations (
    station_id   SERIAL PRIMARY KEY,
    station_name TEXT NOT NULL,
    district     TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'Punjab',
    latitude     DOUBLE PRECISION,
    longitude    DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS readings (
    reading_id    SERIAL PRIMARY KEY,
    station_id    INTEGER REFERENCES stations(station_id),
    reading_date  DATE NOT NULL,
    water_level_m DOUBLE PRECISION NOT NULL,  -- depth to water, metres below ground
    source        TEXT DEFAULT 'CGWB'
);

CREATE INDEX IF NOT EXISTS idx_readings_station_date ON readings(station_id, reading_date);

-- CGWB's official categories — do not invent thresholds.
CREATE TABLE IF NOT EXISTS risk_categories (
    district        TEXT PRIMARY KEY,
    category        TEXT NOT NULL CHECK (category IN ('safe', 'semi-critical', 'critical', 'over-exploited')),
    assessment_year INTEGER
);

-- CGWB categorises assessment units (blocks), never districts. This table holds
-- the block-level truth from the published assessment; risk_categories.category
-- is derived from it, so an answer can cite the actual distribution rather than
-- assert a bare label.
CREATE TABLE IF NOT EXISTS assessment_blocks (
    block_id        SERIAL PRIMARY KEY,
    district        TEXT NOT NULL,
    block           TEXT NOT NULL,
    stage_pct       DOUBLE PRECISION,  -- stage of ground water extraction, %
    category        TEXT NOT NULL CHECK (category IN ('safe', 'semi-critical', 'critical', 'over-exploited')),
    assessment_year INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_blocks_district_block
    ON assessment_blocks(district, block);

-- Supporting evidence for the derived district category.
ALTER TABLE risk_categories ADD COLUMN IF NOT EXISTS blocks_assessed       INTEGER;
ALTER TABLE risk_categories ADD COLUMN IF NOT EXISTS blocks_safe           INTEGER;
ALTER TABLE risk_categories ADD COLUMN IF NOT EXISTS blocks_semi_critical  INTEGER;
ALTER TABLE risk_categories ADD COLUMN IF NOT EXISTS blocks_critical       INTEGER;
ALTER TABLE risk_categories ADD COLUMN IF NOT EXISTS blocks_over_exploited INTEGER;

-- --------------------------------------------------------------------------
-- Additions beyond the Section 4 schema, both to make ingestion re-runnable.
-- Without these, running ingest_data.py twice silently doubles every row.
-- --------------------------------------------------------------------------

-- A station is identified by its name within a district.
CREATE UNIQUE INDEX IF NOT EXISTS uq_stations_name_district
    ON stations(station_name, district);

-- One reading per station per date.
CREATE UNIQUE INDEX IF NOT EXISTS uq_readings_station_date
    ON readings(station_id, reading_date);
