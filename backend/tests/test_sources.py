"""Naming the source of a derived figure, and surviving a garbled draft.

The prompt requires a source in parentheses after every number. A single
reading has one - a station and a date. A depletion rate does not: it is the
median of dozens of station trends. Given nothing citable, the model quoted the
field name: "falling at 1.205 meters per year (depletion_rate)".

Pure functions - no model, no database, no network.
"""

from __future__ import annotations

import pytest

from app.agents.grounding import grounding_issues
from app.agents.orchestrator import _citations, _data_dump, _name_the_sources
from app.services.llm_client import LLMGarbledResponse, LLMUnavailable, slim_for_prompt


@pytest.fixture
def trend_data() -> dict:
    return {
        "intent": "depletion_trend",
        "district": "Sangrur",
        "depletion_rate": {
            "district": "Sangrur",
            "rate_m_per_year": 1.205,
            "stations_used": [f"S{i}" for i in range(37)],
            "years_analyzed": 10,
            "confidence_note": "Median of 37 station trends.",
        },
    }


# --------------------------------------------------------------------------
# Naming the source
# --------------------------------------------------------------------------


def test_a_derived_rate_is_given_something_citable(trend_data):
    _name_the_sources(trend_data)
    assert (
        trend_data["depletion_rate"]["source"]
        == "Median trend across 37 stations, Sangrur, last 10 years"
    )


def test_the_source_survives_slimming(trend_data):
    """stations_used collapses to "[37 stations]" for the prompt; the source
    string must not go with it, or the model has nothing to quote."""
    _name_the_sources(trend_data)
    slimmed = slim_for_prompt(trend_data)
    assert "source" in slimmed["depletion_rate"]
    assert slimmed["depletion_rate"]["stations_used"] == "[37 stations]"


def test_quoting_the_source_grounds_cleanly(trend_data):
    """Written into the data, not the prompt, precisely so check 1 finds it."""
    _name_the_sources(trend_data)
    draft = (
        "The water table is falling at 1.205 m/year "
        "(Median trend across 37 stations, Sangrur, last 10 years)."
    )
    assert grounding_issues(draft, trend_data) == []


def test_quoting_the_field_name_does_not_ground(trend_data):
    """The behaviour being replaced. "(depletion_rate)" is a label from the
    data structure and means nothing to a reader - but note that check 1 only
    inspects capitalised tokens, so this is caught by supplying a real source
    rather than by rejecting the fake one."""
    _name_the_sources(trend_data)
    assert "depletion_rate" not in trend_data["depletion_rate"]["source"]


def test_a_projection_is_given_a_source():
    data = {
        "district": "Ludhiana",
        "projection": {
            "years_to_reference_depth": 20.1,
            "stations_used": 75,
            "reference_depth_m": 30.0,
        },
    }
    _name_the_sources(data)
    assert data["projection"]["source"] == "Projected from 75 station trends, Ludhiana"


def test_an_existing_source_is_not_overwritten(trend_data):
    trend_data["depletion_rate"]["source"] = "already set"
    _name_the_sources(trend_data)
    assert trend_data["depletion_rate"]["source"] == "already set"


def test_blocks_with_a_station_of_their_own_are_left_alone():
    data = {
        "current_level": {
            "district": "Bathinda",
            "value_m": 15.91,
            "station": "Kot Shamir",
            "date": "2024-01-01",
        }
    }
    _name_the_sources(data)
    assert "source" not in data["current_level"]


# --------------------------------------------------------------------------
# Surviving a model that rambles
# --------------------------------------------------------------------------


def test_a_garbled_response_is_a_kind_of_unavailable():
    """Callers that only care whether they got an object keep working; the
    orchestrator distinguishes the two to decide what to show."""
    assert issubclass(LLMGarbledResponse, LLMUnavailable)


def test_the_dump_quotes_the_passages_for_a_report_question():
    """Without this the fallback was a preamble and nothing else - none of the
    level/rate/category fields exist on a document answer."""
    data = {
        "intent": "document_question",
        "passages": [
            {
                "citation": "CGWB, Ground Water Resources of Punjab 2024, p. 58",
                "page": 58,
                "text": "Fluoride content in ground water ranges from 0.01 to 22 mg/L.",
            }
        ],
    }
    dump = _data_dump(data, ["the model produced no usable answer"])
    assert "p. 58" in dump
    assert "0.01 to 22 mg/L" in dump


def test_one_page_cited_twice_is_listed_once():
    """Retrieval returning two chunks from page 11 listed page 11 twice, which
    tells the reader nothing except where the chunker happened to split."""
    data = {
        "passages": [
            {"citation": "CGWB, Ground Water Resources of Punjab 2024, p. 58", "page": 58},
            {"citation": "CGWB, Ground Water Resources of Punjab 2024, p. 11", "page": 11},
            {"citation": "CGWB, Ground Water Resources of Punjab 2024, p. 11", "page": 11},
        ]
    }
    pages = [c["station"] for c in _citations(data)]
    assert pages == [
        "CGWB, Ground Water Resources of Punjab 2024, p. 58",
        "CGWB, Ground Water Resources of Punjab 2024, p. 11",
    ]


def test_distinct_sources_are_all_kept():
    data = {
        "current_level": {
            "district": "Ludhiana",
            "value_m": 18.15,
            "station": "Basian Bet M",
            "date": "2024-01-01",
        },
        "depletion_rate": {
            "district": "Ludhiana",
            "rate_m_per_year": 0.504,
            "stations_used": ["a", "b"],
            "years_analyzed": 15,
        },
    }
    assert len(_citations(data)) == 2


def test_the_dump_still_reports_database_figures():
    data = {
        "current_level": {
            "value_m": 15.91,
            "station": "Kot Shamir",
            "date": "2024-01-01",
            "district_mean_m": 16.2,
            "stations_reporting": 9,
        }
    }
    dump = _data_dump(data, ["unverifiable"])
    assert "15.91" in dump and "Kot Shamir" in dump
    assert "unverifiable" in dump
