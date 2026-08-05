"""The projection, and the chart payload built from it.

The Calculation Agent is deterministic, so every way it can fail to be
meaningful is testable: no data, a rising water table, a district already past
the reference depth. Each must produce an honest answer rather than a number.

Pure functions - no model, no database, no network.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.agents.calculation import DEFAULT_REFERENCE_DEPTH_M, calculation_agent
from app.agents.orchestrator import _projection_line
from app.services.llm_client import slim_for_prompt


def retrieved(mean_depth: float, rate: float, year: int = 2024) -> dict:
    return {
        "current_level": {
            "district_mean_m": mean_depth,
            "value_m": mean_depth,
            "date": dt.date(year, 1, 1),
            "station": "Basian Bet M",
            "stations_reporting": 22,
        },
        "depletion_rate": {
            "rate_m_per_year": rate,
            "stations_used": [f"S{i}" for i in range(75)],
            "years_analyzed": 15,
            "confidence_note": "Median of 75 station trends.",
        },
    }


HISTORY = [{"year": y, "mean_depth_m": 10.0, "readings": 40} for y in range(2000, 2025)]


# --------------------------------------------------------------------------
# The projection
# --------------------------------------------------------------------------


def test_ludhianas_real_figures():
    """19.88 m falling at 0.504 m/year reaches 30 m in 20.1 years, in 2044."""
    p = calculation_agent(retrieved(19.88, 0.504))["projection"]
    assert p["years_to_reference_depth"] == 20.1
    assert p["projected_year"] == 2044
    assert p["from_year"] == 2024
    assert p["reference_depth_m"] == DEFAULT_REFERENCE_DEPTH_M


def test_the_year_is_stated_rather_than_left_as_arithmetic():
    """Nothing supplied the arrival year once, and the model invented 2034."""
    note = calculation_agent(retrieved(19.88, 0.504))["projection"]["confidence_note"]
    assert "2044" in note


def test_a_rising_water_table_is_not_projected():
    p = calculation_agent(retrieved(12.0, -0.2))["projection"]
    assert p["years_to_reference_depth"] is None
    assert p["projected_year"] is None
    assert "not falling" in p["confidence_note"]


def test_a_district_already_past_the_reference_depth():
    p = calculation_agent(retrieved(31.2, 0.4))["projection"]
    assert p["years_to_reference_depth"] == 0.0
    assert "already averages" in p["confidence_note"]


def test_no_data_projects_nothing():
    p = calculation_agent({"current_level": None, "depletion_rate": None})["projection"]
    assert p["years_to_reference_depth"] is None
    assert "Not enough data" in p["confidence_note"]


def test_thin_evidence_is_declared():
    data = retrieved(19.88, 0.504)
    data["depletion_rate"]["stations_used"] = ["A", "B"]
    note = calculation_agent(data)["projection"]["confidence_note"]
    assert "weak evidence" in note


def test_the_reference_depth_is_never_attributed_to_cgwb():
    caveat = calculation_agent(retrieved(19.88, 0.504))["projection"]["threshold_caveat"]
    assert "not an official CGWB threshold" in caveat


# --------------------------------------------------------------------------
# The line the chart draws from it
# --------------------------------------------------------------------------


def test_projection_line_runs_from_the_anchor_to_the_reference_depth():
    p = calculation_agent(retrieved(19.88, 0.504))["projection"]
    line = _projection_line(HISTORY, p)
    assert line["series"] == [
        {"year": 2024, "projected_depth_m": 19.88},
        {"year": 2044.1, "projected_depth_m": 30.0},
    ]
    assert line["reaches_year"] == 2044.1


def test_projection_line_anchors_on_the_figure_the_answer_quotes():
    """Not on the history line's last point. The chart must show the number in
    the prose, even where the annual mean differs from the latest-date mean."""
    p = calculation_agent(retrieved(21.5, 0.5))["projection"]
    assert _projection_line(HISTORY, p)["series"][0]["projected_depth_m"] == 21.5


@pytest.mark.parametrize("depth, rate", [(12.0, -0.2), (31.2, 0.4)])
def test_no_forward_line_when_none_applies(depth, rate):
    """A rising table and one already past the mark both draw the reference
    depth and no projection."""
    line = _projection_line(HISTORY, calculation_agent(retrieved(depth, rate))["projection"])
    assert line["series"] == []
    assert line["reaches_year"] is None
    assert line["reference_depth_m"] == 30.0


def test_no_projection_block_means_no_line():
    """Intents other than years_to_critical never run the Calculation Agent."""
    assert _projection_line(HISTORY, None) is None


# --------------------------------------------------------------------------
# What the model is allowed to see
# --------------------------------------------------------------------------


def test_grounding_only_fields_are_hidden_from_the_prompt():
    """Shown `projected_year`, a 7B model cited the field name as a source:
    "around 2044 (projected_year: 2044, citation: projection.confidence_note)".
    The checks need these fields; the model does not."""
    slimmed = slim_for_prompt(calculation_agent(retrieved(19.88, 0.504)))
    assert "projected_year" not in slimmed["projection"]
    assert "from_year" not in slimmed["projection"]


def test_the_year_survives_in_prose_for_the_model_to_use():
    """Hiding the field must not take the year away - it is why the model
    stopped having to work it out, and got it wrong."""
    slimmed = slim_for_prompt(calculation_agent(retrieved(19.88, 0.504)))
    assert "2044" in slimmed["projection"]["confidence_note"]
