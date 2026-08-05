"""Resolving a question that points back at the conversation.

`history` was passed to the Query Understanding agent from the start and never
tested. Five of six follow-up shapes worked. The sixth did not: after Bathinda
and Moga, "which of those two is worse?" was ranked against all 23 districts and
answered "Barnala" - a district nobody had mentioned, and verified, because
Barnala really is in the ranking data.

Pure functions - no model, no database, no network.
"""

from __future__ import annotations

import pytest

from app.agents.query_understanding import MAX_REFERENTS, _referents
from app.scripts.districts import districts_mentioned


def turns(*contents: str) -> list[dict]:
    """Alternating user/assistant turns, as the frontend sends them."""
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": c}
        for i, c in enumerate(contents)
    ]


BATHINDA_AND_MOGA = turns(
    "What is the groundwater status in Bathinda?",
    "The groundwater level in Bathinda is 15.91 m below ground (Kot Shamir, "
    "2024-01-01), and the district is categorized as over-exploited.",
    "And what about Moga?",
    "Moga is over-exploited (31.42 m (2024-01-01))",
)


# --------------------------------------------------------------------------
# Finding districts in text
# --------------------------------------------------------------------------


def test_districts_are_found_in_order_of_appearance():
    assert districts_mentioned("Moga is deeper than Bathinda") == ["Moga", "Bathinda"]


def test_each_district_is_reported_once():
    assert districts_mentioned("Moga, and Moga again") == ["Moga"]


def test_the_reports_spellings_resolve():
    assert districts_mentioned("levels in Bhatinda and Ropar") == [
        "Bathinda",
        "Rupnagar",
    ]


def test_a_longer_name_is_not_shadowed_by_a_shorter_one():
    assert districts_mentioned("Tarn Taran") == ["Tarn Taran"]


def test_a_word_containing_a_district_name_is_not_a_mention():
    assert districts_mentioned("the Mogambo canal") == []


def test_empty_text_mentions_nothing():
    assert districts_mentioned("") == []
    assert districts_mentioned(None) == []


# --------------------------------------------------------------------------
# Resolving "those two"
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Which of those two is worse?",
        "Which of them is worst?",
        "Is either of them safe?",
        "Which of these has the deeper water table?",
    ],
)
def test_a_backward_pointing_superlative_resolves_to_the_conversation(question):
    assert _referents(question, BATHINDA_AND_MOGA) == ["Bathinda", "Moga"]


def test_a_superlative_about_punjab_is_left_alone():
    """"Which district has the worst water table?" is a real ranking question,
    even mid-conversation."""
    assert _referents("Which district has the worst water table?", BATHINDA_AND_MOGA) == []


def test_pointing_back_with_nothing_to_point_at():
    """First message of a conversation. Falls through to a global ranking,
    which is the best available reading."""
    assert _referents("Which of those two is worse?", []) == []


def test_a_question_that_names_its_own_district_is_not_referring_back():
    assert _referents("How does Bathinda compare to those?", BATHINDA_AND_MOGA) == []


def test_one_district_is_not_a_comparison():
    only_bathinda = turns("Status in Bathinda?", "Bathinda is over-exploited.")
    assert _referents("Which of those is worse?", only_bathinda) == []


def test_too_many_districts_is_too_vague_to_resolve():
    """An answer listing twenty over-exploited districts must not turn the next
    question into a twenty-way comparison."""
    many = turns(
        "Which districts are over-exploited?",
        "20 of Punjab's 23 districts are over-exploited: Ludhiana, Jalandhar, "
        "Amritsar, Patiala, Sangrur, Gurdaspur, Tarn Taran, Hoshiarpur.",
    )
    assert len(districts_mentioned(many[1]["content"])) > MAX_REFERENTS
    assert _referents("Which of those is worst?", many) == []


def test_only_recent_turns_are_considered():
    """Four turns back, matching the window the agent sends to the model."""
    stale = turns(
        "Status in Amritsar?", "Amritsar is over-exploited.",
        "Status in Bathinda?", "Bathinda is over-exploited.",
        "Status in Moga?", "Moga is over-exploited.",
    )
    assert _referents("Which of those two is worse?", stale) == ["Bathinda", "Moga"]
