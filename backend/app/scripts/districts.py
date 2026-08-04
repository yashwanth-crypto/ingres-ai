"""Canonical Punjab district names and the spelling variants CGWB exports use.

CGWB / IndiaWRIS files are inconsistent about district spelling across years —
"Ferozepur", "Firozpur" and "Ferozpur" all appear for the same district, and the
renamed districts (Nawanshahr -> Shahid Bhagat Singh Nagar, Mohali -> Sahibzada
Ajit Singh Nagar) show up under both names depending on the vintage of the file.
Ingestion collapses all of them onto the canonical name so that a district lookup
later in the pipeline can be an exact match instead of a fuzzy one.
"""

from __future__ import annotations

import re

# Punjab has 23 districts as of the 2021 creation of Malerkotla.
CANONICAL_DISTRICTS: tuple[str, ...] = (
    "Amritsar",
    "Barnala",
    "Bathinda",
    "Faridkot",
    "Fatehgarh Sahib",
    "Fazilka",
    "Ferozepur",
    "Gurdaspur",
    "Hoshiarpur",
    "Jalandhar",
    "Kapurthala",
    "Ludhiana",
    "Malerkotla",
    "Mansa",
    "Moga",
    "Muktsar",
    "Pathankot",
    "Patiala",
    "Rupnagar",
    "Sahibzada Ajit Singh Nagar",
    "Sangrur",
    "Shahid Bhagat Singh Nagar",
    "Tarn Taran",
)

# Normalised variant -> canonical name. Keys are run through _normalise() below,
# so case, punctuation and spacing here are only for readability.
_VARIANTS: dict[str, str] = {
    "amritsar": "Amritsar",
    "barnala": "Barnala",
    "bathinda": "Bathinda",
    "bhatinda": "Bathinda",
    "faridkot": "Faridkot",
    "fatehgarh sahib": "Fatehgarh Sahib",
    "fatehgarhsahib": "Fatehgarh Sahib",
    "fazilka": "Fazilka",
    "ferozepur": "Ferozepur",
    "ferozpur": "Ferozepur",
    "firozpur": "Ferozepur",
    "firozepur": "Ferozepur",
    "ferozepore": "Ferozepur",
    "gurdaspur": "Gurdaspur",
    "hoshiarpur": "Hoshiarpur",
    "jalandhar": "Jalandhar",
    "jullundur": "Jalandhar",
    "kapurthala": "Kapurthala",
    "ludhiana": "Ludhiana",
    "malerkotla": "Malerkotla",
    "maler kotla": "Malerkotla",
    "mansa": "Mansa",
    "moga": "Moga",
    "muktsar": "Muktsar",
    "mukatsar": "Muktsar",  # spelling used in the NWDP quarterly export
    "sri muktsar sahib": "Muktsar",
    "shri muktsar sahib": "Muktsar",
    "muktsar sahib": "Muktsar",
    "pathankot": "Pathankot",
    "patiala": "Patiala",
    "rupnagar": "Rupnagar",
    "roopnagar": "Rupnagar",
    "ropar": "Rupnagar",
    "sahibzada ajit singh nagar": "Sahibzada Ajit Singh Nagar",
    "s a s nagar": "Sahibzada Ajit Singh Nagar",
    "sas nagar": "Sahibzada Ajit Singh Nagar",
    "mohali": "Sahibzada Ajit Singh Nagar",
    "sangrur": "Sangrur",
    "shahid bhagat singh nagar": "Shahid Bhagat Singh Nagar",
    "shaheed bhagat singh nagar": "Shahid Bhagat Singh Nagar",
    "s b s nagar": "Shahid Bhagat Singh Nagar",
    "sbs nagar": "Shahid Bhagat Singh Nagar",
    "nawanshahr": "Shahid Bhagat Singh Nagar",
    "nawan shahr": "Shahid Bhagat Singh Nagar",
    "nawanshahar": "Shahid Bhagat Singh Nagar",
    "tarn taran": "Tarn Taran",
    "tarntaran": "Tarn Taran",
    "taran taran": "Tarn Taran",
}


def _normalise(value: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.strip().lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def canonical_district(value: str | None) -> str | None:
    """Return the canonical Punjab district name, or None if unrecognised.

    Returning None rather than guessing is deliberate: an unrecognised district
    is either a non-Punjab row or a spelling we have not seen, and both should be
    reported to the operator instead of silently folded into a neighbour.
    """
    if value is None:
        return None
    key = _normalise(str(value))
    if not key:
        return None
    if key in _VARIANTS:
        return _VARIANTS[key]
    # Tolerate a trailing "district" / "distt" suffix.
    key = re.sub(r"\s+(district|distt|dist)$", "", key).strip()
    return _VARIANTS.get(key)


def variants_of(district: str) -> set[str]:
    """Every spelling that maps to this district, lowercased.

    CGWB's own report spells Bathinda "Bhatinda" in places, so a check that
    looks for the canonical name alone reports a district as missing from text
    that plainly discusses it.
    """
    return {v for v, canonical in _VARIANTS.items() if canonical == district}


def is_punjab(value: str | None) -> bool:
    """True if a state column value refers to Punjab."""
    if value is None:
        return False
    return _normalise(str(value)) == "punjab"
