"""The progress events, and the contract between the two endpoints.

`/chat` and `/chat/stream` run the same generator, so the thing most worth
pinning is that they cannot drift: whatever the stream ends with is exactly
what the plain endpoint returns.

The stage details are read off real data. A line claiming 75 stations has to
mean 75 rows came back — a progress indicator reporting invented work is worse
than a spinner, because it looks like evidence.

The agents are stubbed; no model, database or network.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.agents import orchestrator as orch
from app.agents.query_understanding import QueryIntent
from app.agents.response import DraftAnswer
from app.agents.verification import Verdict


@pytest.fixture
def pipeline(monkeypatch):
    """A pipeline that answers a current-status question about Bathinda."""
    raw = {
        "intent": "current_status",
        "district": "Bathinda",
        "current_level": {
            "district": "Bathinda",
            "value_m": 15.91,
            "station": "Kot Shamir",
            "date": dt.date(2024, 1, 1),
            "stations_reporting": 9,
            "district_mean_m": 16.2,
        },
    }
    monkeypatch.setattr(
        orch, "query_understanding_agent",
        lambda m, h=None: QueryIntent(intent="current_status", district="Bathinda"),
    )
    monkeypatch.setattr(orch, "retrieval_agent", lambda db, i: dict(raw))
    monkeypatch.setattr(
        orch, "response_agent",
        lambda data, msg, issues=None: DraftAnswer(
            answer="Bathinda is 15.91 m below ground (Kot Shamir, 2024-01-01)."
        ),
    )
    monkeypatch.setattr(orch, "verification_agent", lambda d, r: Verdict(approved=True))
    monkeypatch.setattr(orch, "_chart", lambda db, i, r: None)
    monkeypatch.setattr(orch, "_map", lambda db, i, r: None)
    return raw


def stages(events):
    return [e["stage"] for e in events]


# --------------------------------------------------------------------------
# The two endpoints cannot drift
# --------------------------------------------------------------------------


def test_the_stream_ends_with_what_the_plain_endpoint_returns(pipeline):
    events = list(orch.run_chat(None, "What is the status in Bathinda?"))
    assert events[-1]["stage"] == "done"
    assert events[-1]["result"] == orch.handle_chat(None, "What is the status in Bathinda?")


def test_exactly_one_done_event(pipeline):
    events = list(orch.run_chat(None, "What is the status in Bathinda?"))
    assert stages(events).count("done") == 1


def test_every_event_names_its_stage(pipeline):
    for event in orch.run_chat(None, "What is the status in Bathinda?"):
        assert event["stage"]
        if event["stage"] != "done":
            assert event["label"]


# --------------------------------------------------------------------------
# The order of the work
# --------------------------------------------------------------------------


def test_the_pipeline_reports_its_steps_in_order(pipeline):
    order = stages(orch.run_chat(None, "What is the status in Bathinda?"))
    for earlier, later in [
        ("understanding", "understood"),
        ("understood", "retrieving"),
        ("retrieving", "retrieved"),
        ("retrieved", "drafting"),
        ("drafting", "checking"),
        ("checking", "verified"),
        ("verified", "done"),
    ]:
        assert order.index(earlier) < order.index(later), f"{earlier} after {later}"


def test_a_projection_announces_the_calculation(monkeypatch, pipeline):
    monkeypatch.setattr(
        orch, "query_understanding_agent",
        lambda m, h=None: QueryIntent(intent="years_to_critical", district="Ludhiana"),
    )
    monkeypatch.setattr(
        orch, "retrieval_agent",
        lambda db, i: {
            "intent": "years_to_critical",
            "district": "Ludhiana",
            "current_level": {
                "district": "Ludhiana", "value_m": 18.15, "station": "S",
                "date": dt.date(2024, 1, 1), "stations_reporting": 22,
                "district_mean_m": 19.88,
            },
            "depletion_rate": {
                "district": "Ludhiana", "rate_m_per_year": 0.504,
                "stations_used": ["a"] * 75, "years_analyzed": 15,
                "confidence_note": "note",
            },
        },
    )
    events = list(orch.run_chat(None, "How many years until Ludhiana hits 30 m?"))
    calculated = next(e for e in events if e["stage"] == "calculated")
    assert "20.1 years" in calculated["detail"]
    assert "0.504 m/year" in calculated["detail"]


def test_an_out_of_scope_question_stops_after_understanding(monkeypatch, pipeline):
    monkeypatch.setattr(
        orch, "query_understanding_agent",
        lambda m, h=None: QueryIntent(intent="out_of_scope", out_of_scope_reason="not_punjab"),
    )
    order = stages(orch.run_chat(None, "What is the weather in Delhi?"))
    assert order == ["understanding", "done"]


# --------------------------------------------------------------------------
# The details are real
# --------------------------------------------------------------------------


def test_retrieval_reports_the_rows_that_came_back(pipeline):
    events = list(orch.run_chat(None, "What is the status in Bathinda?"))
    detail = next(e for e in events if e["stage"] == "retrieved")["detail"]
    assert "9 stations reporting" in detail


def test_a_report_answer_reports_its_pages():
    data = {
        "passages": [
            {"page": 58, "citation": "c", "text": "t"},
            {"page": 11, "citation": "c", "text": "t"},
            {"page": 11, "citation": "c", "text": "t"},
        ]
    }
    # Three passages over two distinct pages, and the pages are named.
    assert orch._retrieved_summary(data) == "3 passages, p. 11, p. 58"


def test_nothing_retrieved_says_so():
    assert orch._retrieved_summary({}) == "nothing matching"


def test_a_district_without_readings_is_named_in_the_detail():
    detail = orch._retrieved_summary({"unavailable": "No readings for Malerkotla."})
    assert "Malerkotla" in detail


def test_the_checking_line_counts_the_figures_in_the_draft():
    assert "2 figures" in orch._checking_summary("15.91 m in 2024 terms")
    assert "1 figure" in orch._checking_summary("about 20 years")


def test_the_intent_summary_names_the_district():
    summary = orch._intent_summary(QueryIntent(intent="years_to_critical", district="Ludhiana"))
    assert "projection" in summary and "Ludhiana" in summary


def test_the_intent_summary_survives_a_question_naming_no_district():
    assert orch._intent_summary(QueryIntent(intent="ranking")) == "ranking across Punjab"
