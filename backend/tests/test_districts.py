"""District canonicalisation.

CGWB's own spellings are inconsistent across its tables and its report, and a
near-miss reaching SQL means a real question silently returns nothing. Every
alias here is one the source data actually uses.

Pure functions - no model, no database, no network.
"""

from __future__ import annotations

import pytest

from app.scripts.districts import (
    CANONICAL_DISTRICTS,
    canonical_district,
    is_punjab,
    variants_of,
)


def test_punjab_has_twenty_three_districts():
    assert len(CANONICAL_DISTRICTS) == 23
    assert len(set(CANONICAL_DISTRICTS)) == 23


@pytest.mark.parametrize(
    "given, expected",
    [
        ("Ropar", "Rupnagar"),
        ("Firozpur", "Ferozepur"),
        ("Mukatsar", "Muktsar"),
        ("Mohali", "Sahibzada Ajit Singh Nagar"),
        ("SAS Nagar", "Sahibzada Ajit Singh Nagar"),
        ("Bhatinda", "Bathinda"),
    ],
)
def test_cgwb_spellings_resolve(given, expected):
    assert canonical_district(given) == expected


@pytest.mark.parametrize("given", ["ludhiana", "LUDHIANA", "  Ludhiana  "])
def test_case_and_whitespace_do_not_matter(given):
    assert canonical_district(given) == "Ludhiana"


def test_canonical_names_are_stable():
    """Every canonical name must resolve to itself, or repeated ingestion of
    already-clean data would drift."""
    for district in CANONICAL_DISTRICTS:
        assert canonical_district(district) == district


def test_unknown_district_is_none_not_a_guess():
    assert canonical_district("Gurgaon") is None
    assert canonical_district("") is None
    assert canonical_district(None) is None


def test_variants_include_the_spelling_the_report_uses():
    """grounding.py matches drafts against these, so Bathinda must answer to
    the report's "Bhatinda"."""
    assert "bhatinda" in {v.lower() for v in variants_of("Bathinda")}


def test_is_punjab_reads_a_state_column_not_a_district():
    """It filters ingestion rows by their state field. A district name is not
    a state, and must not pass - that would admit every Ludhiana in India."""
    assert is_punjab("Punjab")
    assert is_punjab("  PUNJAB  ")
    assert not is_punjab("Haryana")
    assert not is_punjab("Ludhiana")
    assert not is_punjab(None)
