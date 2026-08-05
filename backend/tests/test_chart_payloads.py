"""What the Orchestrator hands the interface to draw.

Which visual an answer gets is decided from the intent and the retrieved data,
never from a model-set flag - the model was observed leaving both flags false
on questions that plainly wanted one. That decision is a rule, so it is tested
like one.

The only database call is the category lookup, which is stubbed.
"""

from __future__ import annotations

import pytest

from app.agents.orchestrator import _bars, _wants_chart, _wants_map
from app.agents.query_understanding import QueryIntent
from app.services import groundwater_service as gw


@pytest.fixture(autouse=True)
def stub_categories(monkeypatch):
    monkeypatch.setattr(
        gw,
        "categories_for",
        lambda db, districts: {d: "over-exploited" for d in districts},
    )


RANKING = {
    "ranking": [
        {"district": "Barnala", "value": 43.22, "unit": "m below ground", "stations": 6},
        {"district": "Sangrur", "value": 40.52, "unit": "m below ground", "stations": 14},
        {"district": "Moga", "value": 34.6, "unit": "m below ground", "stations": 7},
    ],
    "answer_is": {"district": "Barnala", "value": 43.22},
    "ranked_by": "depth",
    "districts_ranked": 22,
}


# --------------------------------------------------------------------------
# Which visual an answer gets
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent",
    ["current_status", "depletion_trend", "years_to_critical", "ranking", "comparison"],
)
def test_intents_that_earn_a_chart(intent):
    assert _wants_chart(QueryIntent(intent=intent, district="Ludhiana"))


def test_a_category_listing_gets_no_chart():
    """Every bar would be the same length and colour; the map already says it."""
    assert not _wants_chart(QueryIntent(intent="risk_category", category="over-exploited"))


def test_a_document_answer_gets_no_chart():
    assert not _wants_chart(QueryIntent(intent="document_question"))


def test_several_districts_earn_a_map():
    assert _wants_map(QueryIntent(intent="comparison", districts=["Moga", "Barnala"]), {})
    assert _wants_map(QueryIntent(intent="ranking"), RANKING)


# --------------------------------------------------------------------------
# Ranked bars
# --------------------------------------------------------------------------


def test_ranked_bars_keep_the_order_and_name_the_answer():
    bars = _bars(None, RANKING)
    assert [b["label"] for b in bars["bars"]] == ["Barnala", "Sangrur", "Moga"]
    assert bars["highlight"] == "Barnala"
    assert bars["type"] == "bars"


def test_ranked_bars_say_how_many_districts_exist():
    """Without the denominator "8 shown" reads as if that were all of them."""
    assert "22" in _bars(None, RANKING)["note"]


def test_ranking_by_rate_changes_the_unit_and_the_title():
    data = {
        "ranking": [
            {"district": "Barnala", "value": 1.36, "unit": "m/year", "stations": 17}
        ],
        "ranked_by": "depletion",
        "districts_ranked": 22,
    }
    bars = _bars(None, data)
    assert bars["unit"] == "m/year"
    assert "Rate of fall" in bars["title"]


# --------------------------------------------------------------------------
# Compared bars
# --------------------------------------------------------------------------


def test_compared_bars_carry_each_districts_category():
    data = {
        "comparison": {
            "districts": [
                {"district": "Ludhiana", "value_m": 18.15, "category": "over-exploited"},
                {"district": "Sangrur", "value_m": 40.1, "category": "over-exploited"},
            ]
        }
    }
    bars = _bars(None, data)
    assert [b["label"] for b in bars["bars"]] == ["Ludhiana", "Sangrur"]
    assert all(b["category"] == "over-exploited" for b in bars["bars"])
    assert bars["highlight"] is None


def test_a_district_with_no_readings_is_named_not_dropped():
    """Malerkotla has a CGWB category and no monitoring stations. Showing two
    bars for three districts without saying so would be a quiet lie."""
    data = {
        "comparison": {
            "districts": [
                {"district": "Ludhiana", "value_m": 18.15, "category": "over-exploited"},
                {"district": "Malerkotla", "value_m": None, "category": "over-exploited"},
            ]
        }
    }
    bars = _bars(None, data)
    assert [b["label"] for b in bars["bars"]] == ["Ludhiana"]
    assert bars["unavailable"] == ["Malerkotla"]


def test_nothing_plottable_draws_nothing():
    data = {
        "comparison": {
            "districts": [{"district": "Malerkotla", "value_m": None, "category": None}]
        }
    }
    assert _bars(None, data) is None


def test_a_single_district_answer_has_no_bars():
    """It gets the trend line instead."""
    assert _bars(None, {"current_level": {"district_mean_m": 19.88}}) is None
