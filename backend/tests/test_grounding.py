"""The grounding checks are the credibility mechanism, so they get real tests.

Every case here is a draft that was actually produced by the pipeline, or a
close variant of one. The two that matter most are the ones that shipped:
a fabricated arrival year, and a number of years restated as a depth. Both
were *approved* by the checks as they stood, which is why they are pinned.

Pure functions - no model, no database, no network.
"""

from __future__ import annotations

import pytest

from app.agents.grounding import grounding_issues

REFERENCE_CAVEAT = (
    "CGWB's 'critical' category measures extraction versus recharge, not "
    "depth. 30 m is a practical pumping limit used for this projection, not "
    "an official CGWB threshold."
)


@pytest.fixture
def projection_data() -> dict:
    """Ludhiana, years_to_critical - the real retrieved figures."""
    return {
        "intent": "years_to_critical",
        "district": "Ludhiana",
        "current_level": {
            "district": "Ludhiana",
            "value_m": 18.15,
            "station": "Basian Bet M",
            "date": "2024-01-01",
            "stations_reporting": 22,
            "district_mean_m": 19.88,
        },
        "depletion_rate": {
            "district": "Ludhiana",
            "rate_m_per_year": 0.504,
            "stations_used": ["Ladhowal", "Basian Bet M"],
            "years_analyzed": 15,
            "confidence_note": "Median of 75 station trends.",
        },
        "projection": {
            "years_to_reference_depth": 20.1,
            "current_rate_m_per_year": 0.504,
            "current_depth_m": 19.88,
            "reference_depth_m": 30.0,
            "stations_used": 75,
            "from_year": 2024,
            "projected_year": 2044,
            "confidence_note": "Straight-line projection.",
            "threshold_caveat": REFERENCE_CAVEAT,
        },
    }


def only(issues: list[str], word: str) -> list[str]:
    return [i for i in issues if word in i]


# --------------------------------------------------------------------------
# Check 5 - the projected year
# --------------------------------------------------------------------------


def test_fabricated_arrival_year_is_caught(projection_data):
    """The bug that shipped: right span, invented year, approved as verified."""
    draft = (
        "Based on the current depletion rate of 0.504 meters per year and the "
        "reference depth of 30.0 meters, Ludhiana is projected to reach the "
        "critical depth in approximately 20 years (2034)."
    )
    assert only(grounding_issues(draft, projection_data), "2034")


def test_correct_arrival_year_passes(projection_data):
    draft = (
        "At 0.504 m/year Ludhiana reaches the 30.0 m reference depth in about "
        "20.1 years, around 2044."
    )
    assert grounding_issues(draft, projection_data) == []


def test_arrival_year_off_by_one_is_allowed(projection_data):
    """The projection lands mid-year; rounding either way is a fair reading."""
    draft = "Ludhiana reaches 30.0 m around 2045, about 20.1 years away."
    assert grounding_issues(draft, projection_data) == []


def test_past_year_citation_is_not_treated_as_a_projection(projection_data):
    """Citations legitimately carry years. Only years after the last reading
    can be the arrival year."""
    draft = (
        "The level is 19.88 m below ground (Basian Bet M, 2024-01-01), "
        "measured over 15 years."
    )
    assert grounding_issues(draft, projection_data) == []


def test_wildly_wrong_year_is_caught(projection_data):
    draft = "Ludhiana will reach 30.0 m by 2099, in 20.1 years."
    assert only(grounding_issues(draft, projection_data), "2099")


# --------------------------------------------------------------------------
# Check 6 - units
# --------------------------------------------------------------------------


def test_years_restated_as_a_depth_is_caught(projection_data):
    """The second bug that shipped. 20.1 is real - it is the number of years,
    not a depth - so checking membership alone approved it."""
    draft = (
        "Ludhiana is projected to reach a reference depth of 20.1 meters "
        "around 2044."
    )
    assert only(grounding_issues(draft, projection_data), "depth in metres")


def test_rate_is_not_confused_with_a_depth(projection_data):
    """0.504 is a rate. Written as a bare depth it is wrong."""
    draft = "The water table in Ludhiana stands at 0.504 m below ground."
    assert only(grounding_issues(draft, projection_data), "depth in metres")


def test_depth_stated_as_a_rate_is_caught(projection_data):
    draft = "Ludhiana's water table is falling at 19.88 m per year."
    assert only(grounding_issues(draft, projection_data), "metres per year")


def test_correct_units_pass(projection_data):
    draft = (
        "Ludhiana averages 19.88 m below ground and is falling at 0.504 m/year, "
        "reaching 30 m in about 20.1 years."
    )
    assert grounding_issues(draft, projection_data) == []


def test_rounded_units_pass(projection_data):
    """0.5 for 0.504 and 20 for 20.1 are sensible roundings, not fabrications."""
    draft = "Falling about 0.5 m/year, Ludhiana reaches 30 m in roughly 20 years."
    assert grounding_issues(draft, projection_data) == []


def test_report_answers_skip_the_unit_check():
    """Passages quote figures of every kind; there is no typed set to check
    them against, and flagging quotation would be a false positive."""
    data = {
        "intent": "document_question",
        "passages": [
            {
                "citation": "CGWB, Ground Water Resources of Punjab 2024, p. 47",
                "page": 47,
                "text": "Salinity exceeds 4 m in parts of the south-west.",
            }
        ],
    }
    assert grounding_issues("Salinity exceeds 4 m in the south-west.", data) == []


# --------------------------------------------------------------------------
# Checks 1-4, which had no tests at all
# --------------------------------------------------------------------------


def test_station_from_another_district_is_caught(projection_data):
    """The failure that motivated deterministic checks: the model reviewer
    approved Kot Shamir, a Bathinda station, as the source for Ludhiana."""
    draft = "Ludhiana is 19.88 m below ground (Kot Shamir, 2024-01-01)."
    assert only(grounding_issues(draft, projection_data), "Kot Shamir")


def test_real_station_in_the_data_passes(projection_data):
    draft = "Ludhiana is 18.15 m below ground (Basian Bet M, 2024-01-01)."
    assert grounding_issues(draft, projection_data) == []


def test_invented_figure_is_caught(projection_data):
    draft = "Ludhiana averages 27.44 m below ground."
    assert only(grounding_issues(draft, projection_data), "27.44")


def test_district_not_in_the_data_is_caught(projection_data):
    draft = "Bathinda averages 19.88 m below ground."
    assert only(grounding_issues(draft, projection_data), "Bathinda")


def test_reference_depth_credited_to_cgwb_is_caught(projection_data):
    """30 m is a pumping limit. Crediting it to CGWB invents a regulation."""
    draft = "Ludhiana will hit the 30 m threshold set by CGWB in 20.1 years."
    assert only(grounding_issues(draft, projection_data), "reference depth to")


def test_prose_parenthetical_is_not_read_as_a_citation(projection_data):
    """"(as projected by the median trend)" is prose, not an invented source."""
    draft = (
        "Ludhiana reaches 30 m in about 20.1 years (as projected by the median "
        "trend across 75 stations)."
    )
    assert grounding_issues(draft, projection_data) == []
