"""Agent 7.3 - Calculation.

Deterministic Python. Projects a district's water level forward at its measured
depletion rate and reports how long until it reaches a reference depth.

A NOTE ON "CRITICAL"
--------------------
CGWB's categories (safe / semi-critical / critical / over-exploited) classify
*stage of ground water extraction* - annual extraction as a percentage of annual
recharge. They are NOT depth thresholds, and CGWB publishes no "critical depth"
in metres for a district.

So "years until Ludhiana hits critical depth" cannot be answered against an
official threshold, because no such threshold exists. What this agent computes
instead is years until the water table reaches an explicit reference depth,
stated in the output so the answer can never be mistaken for a CGWB forecast.
The default is a practical pumping limit, not a regulatory one.
"""

from __future__ import annotations

# Depth below ground at which a typical Punjab shallow tubewell / centrifugal
# pump can no longer lift water, forcing a costly deeper submersible. A
# practical irrigation limit, not a CGWB threshold - see the module docstring.
DEFAULT_REFERENCE_DEPTH_M = 30.0


def calculation_agent(
    raw_data: dict, reference_depth_m: float = DEFAULT_REFERENCE_DEPTH_M
) -> dict:
    """Add a projection to the retrieved data.

    Returns the input dict with a `projection` key. Honest about every way the
    projection can fail to be meaningful.
    """
    level = raw_data.get("current_level")
    rate_block = raw_data.get("depletion_rate")

    if not level or not rate_block:
        raw_data["projection"] = {
            "years_to_reference_depth": None,
            "current_rate_m_per_year": None,
            "reference_depth_m": reference_depth_m,
            "confidence_note": (
                "Not enough data to project: this district has no usable water "
                "level history."
            ),
        }
        return raw_data

    # District mean is a better basis than one well's reading.
    current_depth = level["district_mean_m"]
    rate = rate_block["rate_m_per_year"]
    stations = len(rate_block["stations_used"])
    years_window = rate_block["years_analyzed"]

    remaining = reference_depth_m - current_depth

    if remaining <= 0:
        years = 0.0
        note = (
            f"The water table already averages {current_depth:.1f} m, at or below "
            f"the {reference_depth_m:.0f} m reference depth."
        )
    elif rate <= 0:
        years = None
        note = (
            f"The water table is not falling in this district "
            f"({rate:+.2f} m/year across {stations} stations), so it is not "
            f"projected to reach {reference_depth_m:.0f} m."
        )
    else:
        years = remaining / rate
        note = (
            f"Straight-line projection from a district mean of "
            f"{current_depth:.1f} m at {rate:.2f} m/year, the median trend across "
            f"{stations} stations over the last {years_window} years. "
            f"It assumes the current rate holds and ignores policy change, "
            f"rainfall variation and aquifer behaviour, so treat it as an order "
            f"of magnitude, not a date."
        )

    if stations < 5:
        note += f" Based on only {stations} stations - weak evidence."

    raw_data["projection"] = {
        "years_to_reference_depth": round(years, 1) if years is not None else None,
        "current_rate_m_per_year": rate,
        "current_depth_m": round(current_depth, 2),
        "reference_depth_m": reference_depth_m,
        "stations_used": stations,
        "confidence_note": note,
        "threshold_caveat": (
            "CGWB's 'critical' category measures extraction versus recharge, not "
            f"depth. {reference_depth_m:.0f} m is a practical pumping limit used "
            "for this projection, not an official CGWB threshold."
        ),
    }
    return raw_data
