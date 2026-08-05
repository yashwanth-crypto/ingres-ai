"""Chunk metadata and the reranking pass.

The first index stored `{page, text}` and cited the PDF's page index as though
it were the report's own. Both are pinned here: a fluoride passage was cited as
page 67, which is the Iron section - a citation that looks right and lands on
the wrong contaminant.

Pure functions - no model, no index, no network.
"""

from __future__ import annotations

import pytest

from app.scripts.build_rag_index import (
    BROAD_DISTRICT_COUNT,
    LAST_PRINTED_PAGE,
    PAGE_OFFSET,
    chapter_of,
    districts_in,
    section_of,
    wordiness,
)
from app.services.rag_service import rerank


# --------------------------------------------------------------------------
# Pages and sections
# --------------------------------------------------------------------------


def test_the_page_offset_is_the_one_the_report_uses():
    """PDF page 10 prints as page 1, and it holds to the end of the body."""
    assert PAGE_OFFSET == 9
    assert LAST_PRINTED_PAGE + PAGE_OFFSET == 87


@pytest.mark.parametrize(
    "printed, expected",
    [
        (1, "Chapter 1 - Introduction"),
        (11, "Chapter 2 - Hydrogeological conditions of Punjab"),
        (38, "Chapter 3 - Ground water resources estimation methodology"),
        (78, "Chapter 7 - Conclusions"),
    ],
)
def test_chapters_cover_their_page_ranges(printed, expected):
    assert chapter_of(printed) == expected


@pytest.mark.parametrize(
    "printed, expected",
    [
        (53, "Nitrate"),
        (56, "Nitrate"),
        (57, "Fluoride"),
        (58, "Fluoride"),
        (62, "Arsenic"),
        (67, "Iron"),
        (70, "Uranium"),
        (74, "Quality summary"),
    ],
)
def test_quality_subsections_are_resolved(printed, expected):
    """The section a page belongs to, not merely its chapter. Fluoride and
    Iron are nine pages apart and were confusable by exactly that margin."""
    assert section_of(printed) == expected


def test_sections_outside_the_quality_chapter_fall_back_to_the_chapter():
    assert section_of(20) == chapter_of(20)


# --------------------------------------------------------------------------
# What a chunk says about itself
# --------------------------------------------------------------------------


def test_districts_are_found_under_the_reports_own_spellings():
    """CGWB writes "Bhatinda"; a check looking only for the canonical name
    reports a passage as covering nothing."""
    assert "Bathinda" in districts_in("high fluoride is found in Bhatinda district")


def test_districts_are_matched_whole():
    assert districts_in("the Mogambo canal") == []


def test_prose_is_wordy_and_a_table_is_not():
    prose = "Fluoride content in ground water ranges from 0.01 to 22 mg/L in the state."
    table = "15 Muktsar 33 10(30%) 13(39%) 8(24%) 33 1(3%) 1(3%) 17(52%)"
    assert wordiness(prose) > 0.45
    assert wordiness(table) < 0.45


# --------------------------------------------------------------------------
# Reranking
# --------------------------------------------------------------------------


def hit(score, scope, districts, page=1):
    return {"score": score, "scope": scope, "districts": districts, "page": page}


def test_a_passage_about_the_district_outranks_a_closer_statewide_one():
    hits = [
        hit(0.72, "statewide", [], page=46),
        hit(0.69, "district", ["Bathinda", "Mansa"], page=58),
    ]
    assert [h["page"] for h in rerank(hits, "Bathinda")] == [58, 46]


def test_a_passage_about_somewhere_else_is_demoted():
    """The misattribution this exists to stop: quoting a passage scoped to
    Amritsar in an answer about Bathinda."""
    hits = [
        hit(0.70, "district", ["Amritsar"], page=30),
        hit(0.64, "statewide", [], page=46),
    ]
    assert [h["page"] for h in rerank(hits, "Bathinda")] == [46, 30]


def test_a_statewide_survey_is_left_where_similarity_put_it():
    """One chunk names seventeen of the twenty-three districts. Naming
    Bathinda among them does not make it a passage about Bathinda."""
    many = [f"D{i}" for i in range(BROAD_DISTRICT_COUNT + 3)] + ["Bathinda"]
    hits = [
        hit(0.60, "statewide", many, page=11),
        hit(0.62, "statewide", [], page=46),
    ]
    assert [h["page"] for h in rerank(hits, "Bathinda")] == [46, 11]


def test_without_a_district_ranking_is_similarity_alone():
    hits = [
        hit(0.60, "district", ["Amritsar"], page=30),
        hit(0.70, "statewide", [], page=46),
    ]
    assert [h["page"] for h in rerank(hits, None)] == [46, 30]


def test_reranking_never_drops_a_candidate():
    hits = [
        hit(0.70, "district", ["Amritsar"], page=30),
        hit(0.69, "district", ["Bathinda"], page=58),
        hit(0.60, "statewide", [], page=46),
    ]
    assert len(rerank(hits, "Bathinda")) == 3
