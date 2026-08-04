"""Load CGWB Punjab groundwater data into Postgres (spec Section 5).

Usage
-----
    # Inspect and validate without touching the database:
    python -m app.scripts.ingest_data --csv data/raw/punjab_gw.csv --dry-run

    # Load for real (requires DATABASE_URL):
    python -m app.scripts.ingest_data --csv data/raw/punjab_gw.csv \
        --risk-csv data/risk_categories.csv

Run from the `backend/` directory.

Design notes
------------
CGWB and IndiaWRIS exports differ between years and download routes, so this
script does not assume a fixed column layout. It resolves each role it needs
(station / district / date / level) against a table of known header spellings
and *aborts with the actual header list* if a role cannot be resolved, rather
than guessing and producing plausible-looking wrong numbers. The same principle
applies to district names and out-of-range levels: anything unrecognised is
dropped and counted in the summary, never silently coerced.

Deliberately stdlib-only (csv, not pandas) so that ingestion runs on a machine
with no compiled-extension toolchain and no wheel-signing restrictions.

The script is idempotent — re-running it inserts nothing new — thanks to the
unique indexes in schema.sql.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.scripts.districts import CANONICAL_DISTRICTS, canonical_district, is_punjab

# --------------------------------------------------------------------------
# Column resolution
# --------------------------------------------------------------------------

# Role -> header spellings seen across CGWB / IndiaWRIS / data.gov.in exports.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "station": (
        "station_name", "site_name", "sitename", "well_name", "station",
        "site", "location", "site_code", "well_id", "well_no",
        "name_of_site", "observation_well",
    ),
    "district": ("district", "district_name", "districtname", "dist", "distt"),
    "state": ("state", "state_name", "statename"),
    "latitude": ("latitude", "lat", "latitude_degrees", "lat_deg"),
    "longitude": ("longitude", "long", "lon", "longitude_degrees", "lon_deg"),
    "date": (
        "date", "reading_date", "observation_date", "date_of_observation",
        "monitoring_date", "obs_date", "measurement_date", "date_of_measurement",
        "data_acquisition_time",
    ),
    "level": (
        "water_level_m", "water_level", "water_level_mbgl", "waterlevel",
        "depth_to_water_level", "depth_to_water_level_m_bgl", "dtwl", "dtw",
        "wl", "level", "groundwater_level", "gw_level", "data_value",
        "water_level_meters_below_ground_level",
        "groundwater_level_quarterly_manual_meter",
    ),
}

# Last-resort substring matches, tried only when no exact alias hits. CGWB names
# these columns differently in every export ("Groundwater Level Quarterly Manual
# (meter)"), so enumerating every spelling is hopeless. The chosen column is
# always printed in "Resolved columns:" so the operator can check it.
FALLBACK_PATTERNS: dict[str, tuple[str, ...]] = {
    "date": ("acquisition_time", "_time", "date"),
    "level": ("groundwater_level", "water_level", "_level_"),
}

REQUIRED_ROLES = ("station", "district")

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# Nominal sampling months for CGWB's seasonal monitoring rounds. Seasonal
# columns carry no day-level precision, so a representative month is assigned
# and reported in the summary as an explicit assumption.
_SEASON_MONTHS = {"pre_monsoon": 5, "monsoon": 8, "post_monsoon": 11}

# Date formats seen in CGWB exports, tried in order. Day-first variants come
# first because Indian exports are DD/MM/YYYY; an unambiguous ISO string is
# matched by the first pattern regardless.
_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d",
    "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y",
    "%b-%Y", "%B %Y", "%Y-%m",
)

# Plausible depth-to-water range for Punjab, in metres below ground.
# Values outside this are data errors (sentinels like -9999, unit mix-ups).
LEVEL_MIN_M = -5.0
LEVEL_MAX_M = 200.0

# Punjab's bounding box, used to blank obviously wrong coordinates.
LAT_RANGE = (29.0, 33.0)
LON_RANGE = (73.0, 77.0)


def normalise_col(col: str) -> str:
    """Fold a header into a comparable key: lowercase, alnum + single underscores."""
    key = re.sub(r"[^a-z0-9]+", "_", str(col).strip().lower())
    return key.strip("_")


def resolve_columns(fieldnames: list[str]) -> dict[str, str]:
    """Map each role to an actual column name.

    Exits with the real header list if a required role is missing — an
    unresolvable header is an operator problem, not something to guess past.
    """
    lookup = {normalise_col(c): c for c in fieldnames}
    resolved: dict[str, str] = {}

    for role, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                resolved[role] = lookup[alias]
                break

    for role, patterns in FALLBACK_PATTERNS.items():
        if role in resolved:
            continue
        for pattern in patterns:
            hit = next((key for key in lookup if pattern in key), None)
            if hit:
                resolved[role] = lookup[hit]
                break

    missing = [r for r in REQUIRED_ROLES if r not in resolved]
    if missing:
        sys.exit(
            f"ERROR: could not find a column for: {', '.join(missing)}.\n"
            f"Headers in the file: {fieldnames}\n"
            f"Add the correct spelling to COLUMN_ALIASES in "
            f"{Path(__file__).name} and re-run."
        )
    return resolved


def parse_period_column(col: str) -> dt.date | None:
    """Interpret a wide-format measurement header as a date, or None.

    Handles the shapes CGWB uses for per-period columns, e.g.
    "Pre-monsoon_2015", "post_monsoon_2018", "May-2015", "2015_11".
    """
    key = normalise_col(col)
    year_match = re.search(r"(19|20)\d{2}", key)
    if not year_match:
        return None
    year = int(year_match.group(0))

    if "pre" in key and "monsoon" in key:
        month = _SEASON_MONTHS["pre_monsoon"]
    elif "post" in key and "monsoon" in key:
        month = _SEASON_MONTHS["post_monsoon"]
    elif "monsoon" in key:
        month = _SEASON_MONTHS["monsoon"]
    else:
        month = None
        for token in key.split("_"):
            if token in _MONTHS:
                month = _MONTHS[token]
                break
        if month is None:
            return None

    return dt.date(year, month, 1)


def parse_date(value: object) -> dt.date | None:
    """Parse a cell into a date, or None if it is not a usable date."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    # Try the whole string first, then again with a trailing clock time removed
    # ("20-05-2022 06:00", "2022-05-20T06:00:00Z"). Stripping only on the retry
    # keeps formats that legitimately contain spaces, like "15 May 2015".
    candidates = [text]
    without_time = re.sub(
        r"[T\s]+\d{1,2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$", "", text
    )
    if without_time != text:
        candidates.append(without_time)

    for candidate in candidates:
        for fmt in _DATE_FORMATS:
            try:
                return dt.datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def parse_float(value: object) -> float | None:
    """Parse a cell into a float, or None. Tolerates thousands separators."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.upper() in {"NA", "N/A", "NIL", "-", "--", "NULL"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


@dataclass
class Report:
    files: list[tuple[str, int]] = field(default_factory=list)
    rows_read: int = 0
    dropped: Counter = field(default_factory=Counter)
    unknown_districts: Counter = field(default_factory=Counter)
    duplicates_collapsed: int = 0
    coords_blanked: int = 0
    seasonal_dates_assumed: bool = False
    stations_inserted: int = 0
    readings_inserted: int = 0
    stations_total: int = 0
    readings_total: int = 0
    risk_rows_loaded: int = 0
    block_rows_loaded: int = 0
    wrote_to_db: bool = False

    def drop(self, reason: str, n: int = 1) -> None:
        if n:
            self.dropped[reason] += n


# --------------------------------------------------------------------------
# Load & clean
# --------------------------------------------------------------------------


def load_csv(path: Path) -> tuple[list[dict], list[str]]:
    """Read a CSV into dict rows, trying the encodings CGWB actually emits."""
    if not path.exists():
        sys.exit(f"ERROR: no such file: {path}")
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with path.open(newline="", encoding=encoding) as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None:
                    sys.exit(f"ERROR: {path} appears to be empty.")
                return list(reader), list(reader.fieldnames)
        except UnicodeDecodeError:
            continue
    sys.exit(f"ERROR: could not decode {path} as utf-8, cp1252 or latin-1.")


def reshape_to_long(
    rows: list[dict], fieldnames: list[str], cols: dict[str, str], report: Report
) -> list[dict]:
    """Return records with station/district/date/level (+ optional lat/lon).

    If the file already has date + level columns it is used as-is. Otherwise we
    look for wide per-period measurement columns and unpivot them.
    """
    identity = {k: v for k, v in cols.items() if k not in ("date", "level")}

    def identity_of(row: dict) -> dict:
        return {role: row.get(col) for role, col in identity.items()}

    if "date" in cols and "level" in cols:
        return [
            {**identity_of(row), "date": row.get(cols["date"]), "level": row.get(cols["level"])}
            for row in rows
        ]

    period_cols = {c: d for c in fieldnames if (d := parse_period_column(c))}
    if not period_cols:
        sys.exit(
            "ERROR: the file has neither a date+level column pair nor recognisable\n"
            "per-period columns (e.g. 'Pre-monsoon_2015').\n"
            f"Headers in the file: {fieldnames}\n"
            "Resolved so far: " + ", ".join(f"{k}={v!r}" for k, v in cols.items())
        )

    if any("monsoon" in normalise_col(c) for c in period_cols):
        report.seasonal_dates_assumed = True

    out: list[dict] = []
    for row in rows:
        base = identity_of(row)
        for col, when in period_cols.items():
            out.append({**base, "date": when, "level": row.get(col)})
    return out


def clean(records: list[dict], report: Report) -> list[dict]:
    """Apply the Section 5 cleaning rules, counting every dropped row."""
    report.rows_read = len(records)
    kept: list[dict] = []

    for rec in records:
        # Punjab only, when the file tells us the state at all.
        if "state" in rec and rec["state"] is not None:
            if not is_punjab(rec["state"]):
                report.drop("not in Punjab (state column)")
                continue

        district = canonical_district(rec.get("district"))
        if district is None:
            raw = rec.get("district")
            if raw is not None and str(raw).strip():
                report.unknown_districts[str(raw).strip()] += 1
                report.drop("unrecognised district")
            else:
                report.drop("missing district")
            continue

        station = str(rec.get("station") or "").strip()
        if not station:
            report.drop("missing station name")
            continue

        when = rec["date"] if isinstance(rec.get("date"), dt.date) else parse_date(rec.get("date"))
        if when is None:
            report.drop("missing or unparseable date")
            continue

        level = parse_float(rec.get("level"))
        if level is None:
            report.drop("missing or non-numeric water level")
            continue
        if not (LEVEL_MIN_M <= level <= LEVEL_MAX_M):
            report.drop(
                f"water level outside {LEVEL_MIN_M}-{LEVEL_MAX_M} m (sentinel/unit error)"
            )
            continue

        lat = parse_float(rec.get("latitude"))
        lon = parse_float(rec.get("longitude"))
        # A coordinate outside Punjab is a bad coordinate; blank it rather than
        # put the station in the wrong place on the map.
        if lat is not None and not (LAT_RANGE[0] <= lat <= LAT_RANGE[1]):
            lat, report.coords_blanked = None, report.coords_blanked + 1
        if lon is not None and not (LON_RANGE[0] <= lon <= LON_RANGE[1]):
            lon, report.coords_blanked = None, report.coords_blanked + 1

        kept.append(
            {
                "station": station,
                "district": district,
                "date": when,
                "level": level,
                "latitude": lat,
                "longitude": lon,
            }
        )

    return deduplicate(kept, report)


def deduplicate(records: list[dict], report: Report) -> list[dict]:
    """Collapse to one reading per station per date, averaging genuine duplicates.

    Multiple wells can share a site name; averaging is the honest summary and
    the collapsed count is reported so the operator can see it happened.
    """
    grouped: dict[tuple[str, str, dt.date], list[dict]] = defaultdict(list)
    for rec in records:
        grouped[(rec["station"], rec["district"], rec["date"])].append(rec)

    out: list[dict] = []
    for (station, district, when), group in grouped.items():
        out.append(
            {
                "station": station,
                "district": district,
                "date": when,
                "level": sum(r["level"] for r in group) / len(group),
                "latitude": next((r["latitude"] for r in group if r["latitude"] is not None), None),
                "longitude": next((r["longitude"] for r in group if r["longitude"] is not None), None),
            }
        )
    report.duplicates_collapsed = len(records) - len(out)
    out.sort(key=lambda r: (r["district"], r["station"], r["date"]))
    return out


def load_risk_csv(path: Path) -> list[dict]:
    """Read the operator-supplied district -> CGWB category table.

    Expected headers: district, category, assessment_year
    """
    rows, fieldnames = load_csv(path)
    lookup = {normalise_col(c): c for c in fieldnames}
    for required in ("district", "category"):
        if required not in lookup:
            sys.exit(f"ERROR: {path} needs a '{required}' column. Found: {fieldnames}")

    valid = {"safe", "semi-critical", "critical", "over-exploited"}
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        raw_district = row[lookup["district"]]
        if not str(raw_district or "").strip():
            continue
        district = canonical_district(raw_district)
        if district is None:
            sys.exit(
                f"ERROR: {path} has an unrecognised district: {raw_district!r}. "
                f"Fix the spelling or add it to districts.py."
            )
        if district in seen:
            sys.exit(f"ERROR: {path} lists {district} more than once.")
        seen.add(district)

        category = str(row[lookup["category"]] or "").strip().lower()
        if not category:
            sys.exit(
                f"ERROR: {path} has no category for {district}. Fill in every row "
                f"from the CGWB assessment before loading - a blank is not a 'safe'."
            )
        if category not in valid:
            sys.exit(
                f"ERROR: {path} has an invalid category for {district}: "
                f"{category!r}. Must be one of {sorted(valid)}."
            )
        year = None
        if "assessment_year" in lookup:
            parsed = parse_float(row.get(lookup["assessment_year"]))
            year = int(parsed) if parsed is not None else None

        entry = {"district": district, "category": category, "assessment_year": year}
        # Optional supporting evidence for the derived district category.
        for col in (
            "blocks_assessed", "blocks_safe", "blocks_semi_critical",
            "blocks_critical", "blocks_over_exploited",
        ):
            value = parse_float(row.get(lookup[col])) if col in lookup else None
            entry[col] = int(value) if value is not None else None
        out.append(entry)
    return out


def load_blocks_csv(path: Path) -> list[dict]:
    """Read the block-level CGWB assessment (district, block, stage_pct, category)."""
    rows, fieldnames = load_csv(path)
    lookup = {normalise_col(c): c for c in fieldnames}
    for required in ("district", "block", "category"):
        if required not in lookup:
            sys.exit(f"ERROR: {path} needs a '{required}' column. Found: {fieldnames}")

    valid = {"safe", "semi-critical", "critical", "over-exploited"}
    year = None
    m = re.search(r"(19|20)\d{2}", path.name)
    if m:
        year = int(m.group(0))

    out: list[dict] = []
    for row in rows:
        district = canonical_district(row[lookup["district"]])
        if district is None:
            sys.exit(
                f"ERROR: {path} has an unrecognised district: "
                f"{row[lookup['district']]!r}."
            )
        category = str(row[lookup["category"]] or "").strip().lower()
        if category not in valid:
            sys.exit(f"ERROR: {path} has an invalid category: {category!r}.")
        out.append(
            {
                "district": district,
                "block": str(row[lookup["block"]]).strip(),
                "stage_pct": parse_float(row.get(lookup.get("stage_pct", ""))),
                "category": category,
                "assessment_year": year,
            }
        )
    return out


# --------------------------------------------------------------------------
# Database writes
# --------------------------------------------------------------------------


def write_to_db(
    records: list[dict],
    risk_rows: list[dict],
    report: Report,
    block_rows: list[dict] | None = None,
) -> None:
    """Create the schema if needed and upsert stations, readings, risk rows."""
    # Imported here so that --dry-run works without DATABASE_URL being set.
    from sqlalchemy import select, text
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.database import SessionLocal, engine
    from app.models import AssessmentBlock, Reading, RiskCategory, Station

    schema_sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(schema_sql))

    # One row per station, taking the first coordinates we saw for it.
    stations: dict[tuple[str, str], dict] = {}
    for rec in records:
        key = (rec["station"], rec["district"])
        existing = stations.setdefault(
            key,
            {
                "station_name": rec["station"],
                "district": rec["district"],
                "state": "Punjab",
                "latitude": None,
                "longitude": None,
            },
        )
        if existing["latitude"] is None:
            existing["latitude"] = rec["latitude"]
        if existing["longitude"] is None:
            existing["longitude"] = rec["longitude"]

    with SessionLocal() as session:
        # ON CONFLICT DO NOTHING makes rowcount unreliable (psycopg reports -1),
        # so measure the tables before and after instead of trusting it.
        def count(table: str) -> int:
            return session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()

        stations_before = count("stations")
        readings_before = count("readings")

        stmt = pg_insert(Station).values(list(stations.values()))
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["station_name", "district"]
        )
        session.execute(stmt)

        id_map = {
            (name, district): sid
            for sid, name, district in session.execute(
                select(Station.station_id, Station.station_name, Station.district)
            )
        }

        reading_payload = [
            {
                "station_id": id_map[(r["station"], r["district"])],
                "reading_date": r["date"],
                "water_level_m": r["level"],
                "source": "CGWB",
            }
            for r in records
        ]
        CHUNK = 5000
        for i in range(0, len(reading_payload), CHUNK):
            stmt = pg_insert(Reading).values(reading_payload[i : i + CHUNK])
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["station_id", "reading_date"]
            )
            session.execute(stmt)

        report.stations_inserted = count("stations") - stations_before
        report.readings_inserted = count("readings") - readings_before
        report.stations_total = count("stations")
        report.readings_total = count("readings")

        if block_rows:
            stmt = pg_insert(AssessmentBlock).values(block_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["district", "block"],
                set_={
                    "stage_pct": stmt.excluded.stage_pct,
                    "category": stmt.excluded.category,
                    "assessment_year": stmt.excluded.assessment_year,
                },
            )
            session.execute(stmt)
            report.block_rows_loaded = len(block_rows)

        if risk_rows:
            stmt = pg_insert(RiskCategory).values(risk_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["district"],
                set_={
                    c: getattr(stmt.excluded, c)
                    for c in (
                        "category", "assessment_year", "blocks_assessed",
                        "blocks_safe", "blocks_semi_critical",
                        "blocks_critical", "blocks_over_exploited",
                    )
                },
            )
            session.execute(stmt)
            report.risk_rows_loaded = len(risk_rows)

        session.commit()


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


def print_summary(records: list[dict], risk_rows: list[dict], report: Report) -> None:
    line = "=" * 76
    print(f"\n{line}\nINGESTION SUMMARY\n{line}")

    if len(report.files) > 1:
        print("\nSource files:")
        for name, n in report.files:
            print(f"  {n:>8,}  {name}")
    print(f"\nRows read from file(s):     {report.rows_read:,}")
    if report.dropped:
        print("\nRows dropped:")
        for reason, n in report.dropped.most_common():
            print(f"  {n:>8,}  {reason}")
    if report.duplicates_collapsed:
        print(
            f"  {report.duplicates_collapsed:>8,}  duplicate station/date "
            f"(averaged into one reading)"
        )
    if report.coords_blanked:
        print(f"  {report.coords_blanked:>8,}  coordinates outside Punjab (blanked, row kept)")

    by_district: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_district[rec["district"]].append(rec)

    stations = {(r["station"], r["district"]) for r in records}
    print(f"\nClean readings:             {len(records):,}")
    print(f"Distinct stations:          {len(stations):,}")
    if records:
        print(
            f"Date range:                 {min(r['date'] for r in records)} "
            f"to {max(r['date'] for r in records)}"
        )

    covered = sorted(by_district)
    print(f"\nDistricts covered:          {len(covered)} of {len(CANONICAL_DISTRICTS)}")
    missing = [d for d in CANONICAL_DISTRICTS if d not in by_district]
    if missing:
        print(f"  NOT in the data:          {', '.join(missing)}")

    print(f"\n{'District':<30}{'Stations':>10}{'Readings':>12}{'First':>13}{'Last':>13}")
    print("-" * 78)
    for district in covered:
        group = by_district[district]
        print(
            f"{district:<30}"
            f"{len({r['station'] for r in group}):>10,}"
            f"{len(group):>12,}"
            f"{str(min(r['date'] for r in group)):>13}"
            f"{str(max(r['date'] for r in group)):>13}"
        )

    if report.unknown_districts:
        print("\nUNRECOGNISED district names (dropped - check for new spellings):")
        for name, n in report.unknown_districts.most_common(20):
            print(f"  {n:>8,}  {name!r}")

    if report.seasonal_dates_assumed:
        print(
            "\nNOTE: the file used seasonal columns, which carry no exact date.\n"
            "      Pre-monsoon readings were dated 1 May, monsoon 1 Aug,\n"
            "      post-monsoon 1 Nov. Trend slopes are therefore accurate to\n"
            "      the season, not the day."
        )

    if risk_rows:
        counts = Counter(r["category"] for r in risk_rows)
        print(f"\nRisk categories supplied:   {len(risk_rows)} districts")
        for category in ("safe", "semi-critical", "critical", "over-exploited"):
            if counts.get(category):
                print(f"    {counts[category]:>3}  {category}")
        uncategorised = [d for d in covered if d not in {r["district"] for r in risk_rows}]
        if uncategorised:
            print(
                f"  WARNING: no category for districts present in the data: "
                f"{', '.join(uncategorised)}"
            )
    else:
        print("\nRisk categories:            none supplied (--risk-csv not given)")

    if report.wrote_to_db:
        print(
            f"\nInserted this run:          {report.stations_inserted:,} stations, "
            f"{report.readings_inserted:,} readings"
        )
        print(
            f"Now in database:            {report.stations_total:,} stations, "
            f"{report.readings_total:,} readings"
        )
        if report.risk_rows_loaded:
            print(f"Risk rows loaded:           {report.risk_rows_loaded}")
        if report.block_rows_loaded:
            print(f"Assessment blocks loaded:   {report.block_rows_loaded}")
        if report.stations_inserted == 0 and report.readings_inserted == 0:
            print("  (nothing new - the database already held this data)")

    print(f"\n{line}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest CGWB Punjab groundwater data.")
    parser.add_argument(
        "--csv",
        required=True,
        type=Path,
        nargs="+",
        help="raw CGWB CSV(s); pass several to load them as one dataset",
    )
    parser.add_argument(
        "--risk-csv", type=Path, help="district,category,assessment_year CSV"
    )
    parser.add_argument(
        "--blocks-csv",
        type=Path,
        help="district,block,stage_pct,category CSV from the CGWB assessment",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="clean and report without writing to the database",
    )
    args = parser.parse_args()

    report = Report()
    records: list[dict] = []
    # Each file is resolved on its own headers — different CGWB vintages name
    # the same column differently, and they still merge into one dataset.
    for path in args.csv:
        rows, fieldnames = load_csv(path)
        cols = resolve_columns(fieldnames)
        print(f"\n{path.name}: {len(rows):,} rows")
        print("  resolved " + ", ".join(f"{k}={v!r}" for k, v in cols.items()))
        report.files.append((path.name, len(rows)))
        records += reshape_to_long(rows, fieldnames, cols, report)

    records = clean(records, report)

    risk_rows = load_risk_csv(args.risk_csv) if args.risk_csv else []
    block_rows = load_blocks_csv(args.blocks_csv) if args.blocks_csv else []

    if not records:
        print_summary(records, risk_rows, report)
        sys.exit("ERROR: no rows survived cleaning - nothing to load.")

    if args.dry_run:
        print("\n[dry run] database not touched.")
    else:
        write_to_db(records, risk_rows, report, block_rows)
        report.wrote_to_db = True

    print_summary(records, risk_rows, report)


if __name__ == "__main__":
    main()
